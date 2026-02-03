"""Parallel test execution with worker pool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from protest.entities import SuitePath, TestCounts, TestItem, TestOutcome, TestStartInfo
from protest.events.types import Event
from protest.utils import get_callable_name

if TYPE_CHECKING:
    from protest.core.execution.suite_manager import SuiteManager
    from protest.core.execution.test_executor import TestExecutor
    from protest.core.session import ProTestSession
    from protest.core.tracker import SuiteTracker
    from protest.execution.interrupt import InterruptHandler


@dataclass
class _WorkerContext:
    """Shared state for worker coroutines during a single run."""

    queue: asyncio.Queue[TestItem | None]
    semaphores: dict[SuitePath | None, asyncio.Semaphore]
    tracker: SuiteTracker
    exitfirst_flag: asyncio.Event | None
    results: list[TestOutcome] = field(default_factory=list)
    results_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ParallelExecutor:
    """Runs tests in parallel using a worker pool with FIFO order."""

    def __init__(
        self,
        session: ProTestSession,
        test_executor: TestExecutor,
        suite_manager: SuiteManager,
        interrupt_handler: InterruptHandler,
    ) -> None:
        self._session = session
        self._test_executor = test_executor
        self._suite_manager = suite_manager
        self._interrupt_handler = interrupt_handler
        self._force_interrupt_emitted = False

    @property
    def force_interrupt_emitted(self) -> bool:
        """Whether a force interrupt event was already emitted."""
        return self._force_interrupt_emitted

    def build_suite_semaphores(
        self, items: list[TestItem]
    ) -> dict[SuitePath | None, asyncio.Semaphore]:
        """Build per-suite semaphores for max_concurrency."""
        semaphores: dict[SuitePath | None, asyncio.Semaphore] = {}
        seen_suites: set[SuitePath | None] = set()

        for item in items:
            suite_path = item.suite.full_path if item.suite else None
            if suite_path in seen_suites:
                continue
            seen_suites.add(suite_path)

            if item.suite and item.suite.effective_max_concurrency:
                max_conc = min(
                    item.suite.effective_max_concurrency, self._session.concurrency
                )
                semaphores[suite_path] = asyncio.Semaphore(max_conc)

        return semaphores

    async def run(
        self,
        items: list[TestItem],
        suite_semaphores: dict[SuitePath | None, asyncio.Semaphore],
        tracker: SuiteTracker,
    ) -> TestCounts:
        """Run all tests in parallel using a worker pool (FIFO order)."""
        if not items:
            return TestCounts()

        ctx = await self._create_context(items, suite_semaphores, tracker)
        worker_tasks = [
            asyncio.create_task(self._process_queue(ctx))
            for _ in range(self._session.concurrency)
        ]

        await self._wait_with_interrupt(worker_tasks, ctx.exitfirst_flag)
        return _aggregate_results(ctx.results)

    async def _create_context(
        self,
        items: list[TestItem],
        suite_semaphores: dict[SuitePath | None, asyncio.Semaphore],
        tracker: SuiteTracker,
    ) -> _WorkerContext:
        """Create and populate worker context with work queue."""
        queue: asyncio.Queue[TestItem | None] = asyncio.Queue()
        for item in items:
            await queue.put(item)
        for _ in range(self._session.concurrency):
            await queue.put(None)  # Sentinel values

        return _WorkerContext(
            queue=queue,
            semaphores=suite_semaphores,
            tracker=tracker,
            exitfirst_flag=asyncio.Event() if self._session.exitfirst else None,
        )

    async def _process_queue(self, ctx: _WorkerContext) -> None:
        """Process tests from the queue in FIFO order."""
        while True:
            if self._should_stop(ctx.exitfirst_flag):
                return

            test_item = await ctx.queue.get()
            if test_item is None:
                ctx.queue.task_done()
                return

            try:
                if outcome := await self._process_test_item(test_item, ctx):
                    async with ctx.results_lock:
                        ctx.results.append(outcome)
                    if ctx.exitfirst_flag and (
                        outcome.counts.failed or outcome.counts.errored
                    ):
                        ctx.exitfirst_flag.set()
            finally:
                ctx.queue.task_done()

    def _should_stop(self, exitfirst_flag: asyncio.Event | None) -> bool:
        """Check if execution should stop (interrupt or exitfirst)."""
        return (
            self._interrupt_handler.soft_stop_event.is_set()
            or (exitfirst_flag is not None and exitfirst_flag.is_set())
        )

    async def _process_test_item(
        self, item: TestItem, ctx: _WorkerContext
    ) -> TestOutcome | None:
        """Process a single test item. Returns None if interrupted."""
        if self._should_stop(ctx.exitfirst_flag):
            return None

        suite_path = item.suite.full_path if item.suite else None
        suite_sem = ctx.semaphores.get(suite_path)

        if suite_path:
            await self._suite_manager.ensure_hierarchy_started(suite_path)

        start_info = TestStartInfo(
            name=get_callable_name(item.func), node_id=item.node_id
        )
        await self._session.events.emit(Event.TEST_START, start_info)

        if self._should_stop(ctx.exitfirst_flag):
            return None

        outcome = await self._execute_with_semaphore(item, start_info, suite_sem, ctx)

        if suite_path and await ctx.tracker.mark_completed(suite_path):
            await self._suite_manager.teardown(suite_path)
        elif suite_path is None:
            await ctx.tracker.mark_completed(None)

        return outcome

    async def _execute_with_semaphore(
        self,
        item: TestItem,
        start_info: TestStartInfo,
        suite_sem: asyncio.Semaphore | None,
        ctx: _WorkerContext,
    ) -> TestOutcome:
        """Execute test, optionally within suite semaphore."""
        if suite_sem:
            async with suite_sem:
                if self._should_stop(ctx.exitfirst_flag):
                    return TestOutcome(
                        event=Event.TEST_SKIP,
                        result=None,  # type: ignore[arg-type]
                        counts=TestCounts(),
                    )
                return await self._test_executor.execute(item, start_info)
        return await self._test_executor.execute(item, start_info)

    async def _wait_with_interrupt(
        self,
        worker_tasks: list[asyncio.Task[None]],
        exitfirst_flag: asyncio.Event | None = None,
    ) -> None:
        """Wait for workers to complete with interrupt and exitfirst support."""

        async def gather_workers() -> None:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        workers_done = asyncio.create_task(gather_workers())
        force_teardown = asyncio.create_task(
            self._interrupt_handler.force_teardown_event.wait()
        )

        wait_tasks: set[asyncio.Task[Any]] = {workers_done, force_teardown}
        exitfirst_task: asyncio.Task[Any] | None = None

        if exitfirst_flag:
            exitfirst_task = asyncio.create_task(exitfirst_flag.wait())
            wait_tasks.add(exitfirst_task)

        done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

        if force_teardown in done:
            await self._handle_force_teardown(worker_tasks, exitfirst_task)
        elif exitfirst_task and exitfirst_task in done:
            _cancel_tasks(worker_tasks)
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            force_teardown.cancel()
        else:
            self._cleanup_wait_tasks(force_teardown, exitfirst_task)

    async def _handle_force_teardown(
        self,
        worker_tasks: list[asyncio.Task[None]],
        exitfirst_task: asyncio.Task[Any] | None,
    ) -> None:
        """Handle force teardown: cancel workers and emit interrupt event."""
        await self._session.events.emit(Event.SESSION_INTERRUPTED, True)
        self._force_interrupt_emitted = True
        _cancel_tasks(worker_tasks)
        await asyncio.gather(*worker_tasks, return_exceptions=True)
        if exitfirst_task:
            exitfirst_task.cancel()

    def _cleanup_wait_tasks(
        self,
        force_teardown: asyncio.Task[Any],
        exitfirst_task: asyncio.Task[Any] | None,
    ) -> None:
        """Clean up wait tasks after normal completion."""
        force_teardown.cancel()
        if exitfirst_task:
            exitfirst_task.cancel()
        if self._interrupt_handler.soft_stop_event.is_set():
            # Fire-and-forget: EventBus tracks pending tasks internally
            task = asyncio.create_task(
                self._session.events.emit(Event.SESSION_INTERRUPTED, False)
            )
            task.add_done_callback(lambda _: None)  # prevent GC before completion


def _cancel_tasks(tasks: list[asyncio.Task[None]]) -> None:
    """Cancel all non-completed tasks."""
    for task in tasks:
        if not task.done():
            task.cancel()


def _aggregate_results(results: list[TestOutcome]) -> TestCounts:
    """Aggregate test outcomes into total counts."""
    total = TestCounts()
    for outcome in results:
        total = total + outcome.counts
    return total
