import asyncio
import io
import time
from inspect import signature
from typing import Any, get_type_hints

from protest.core.collector import Collector
from protest.core.outcome import OutcomeBuilder, TestExecutionResult
from protest.core.session import ProTestSession
from protest.core.tracker import SuiteTracker
from protest.di.resolver import Resolver
from protest.entities import (
    RunResult,
    SessionResult,
    TestCounts,
    TestItem,
    TestOutcome,
    TestRetryInfo,
    TestStartInfo,
    TestTeardownInfo,
)
from protest.events.types import Event
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async
from protest.execution.capture import (
    CaptureCurrentTest,
    GlobalCapturePatch,
    reset_current_node_id,
    set_current_node_id,
    set_session_setup_capture,
    set_session_teardown_capture,
)
from protest.execution.context import TestExecutionContext, cancellation_event
from protest.execution.interrupt import InterruptHandler
from protest.utils import get_callable_name


class TestRunner:
    """Executes tests with parallel support and fixture lifecycle management.

    Runs all tests in parallel (cross-suite) and automatically triggers
    suite fixture teardown when all tests of a suite complete.
    """

    def __init__(self, session: ProTestSession) -> None:
        self._session = session
        self._outcome_builder = OutcomeBuilder()
        self._started_suites: set[str] = set()
        self._suite_start_lock: asyncio.Lock | None = None
        self._interrupt_handler = InterruptHandler()
        self._interrupted = False
        self._force_interrupt_emitted = False

    def run(self) -> RunResult:
        """Run the test session synchronously. Returns RunResult with success and interrupted status."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._interrupt_handler.install(loop)
        try:
            success = loop.run_until_complete(self._main_loop())
            return RunResult(success=success, interrupted=self._interrupted)
        except KeyboardInterrupt:
            return RunResult(success=False, interrupted=True)
        finally:
            self._interrupt_handler.uninstall()
            loop.close()

    async def _main_loop(self) -> bool:
        """The main async loop for running tests."""
        session_start = time.perf_counter()

        collector = Collector()
        items = collector.collect(self._session)

        items = await self._session.events.emit_and_collect(
            Event.COLLECTION_FINISH, items
        )

        await self._session.events.emit(Event.SESSION_START)

        tracker = SuiteTracker.from_items(items)
        suite_semaphores = self._build_suite_semaphores(items)

        total_counts = TestCounts()
        # Inject cancellation event into context for teardown awareness
        cancel_token = cancellation_event.set(
            self._interrupt_handler.force_teardown_event
        )
        try:
            with GlobalCapturePatch(show_output=not self._session.capture):
                async with self._session:
                    await self._session.events.emit(Event.SESSION_SETUP_START)
                    setup_start = time.perf_counter()
                    set_session_setup_capture(True)
                    try:
                        await self._session.resolve_autouse()
                    finally:
                        set_session_setup_capture(False)
                    setup_duration = time.perf_counter() - setup_start
                    await self._session.events.emit(
                        Event.SESSION_SETUP_DONE, setup_duration
                    )

                    self._started_suites = set()
                    self._suite_start_lock = asyncio.Lock()

                    total_counts = await self._run_all_parallel(
                        items,
                        suite_semaphores,
                        tracker,
                    )

                    for suite_path in reversed(list(self._started_suites)):
                        await self._session.events.emit(Event.SUITE_END, suite_path)
        finally:
            # Emit SESSION_INTERRUPTED if force_teardown was triggered during teardown
            # (only if not already emitted during test execution)
            if (
                self._interrupt_handler.force_teardown_event.is_set()
                and not self._force_interrupt_emitted
            ):
                await self._session.events.emit(Event.SESSION_INTERRUPTED, True)
                self._force_interrupt_emitted = True
            cancellation_event.reset(cancel_token)

        if self._interrupt_handler.should_stop_new_tests:
            self._interrupted = True

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=total_counts.passed,
            failed=total_counts.failed,
            errors=total_counts.errored,
            skipped=total_counts.skipped,
            xfailed=total_counts.xfailed,
            xpassed=total_counts.xpassed,
            duration=session_duration,
            interrupted=self._interrupted,
        )
        await self._session.events.emit(Event.SESSION_END, session_result)

        if not self._interrupt_handler.should_skip_wait_pending:
            if self._session.events.pending_count > 0:
                await self._session.events.emit(
                    Event.WAITING_HANDLERS, self._session.events.pending_count
                )
            await self._session.events.wait_pending()

        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return (
            total_counts.failed == 0
            and total_counts.errored == 0
            and total_counts.xpassed == 0
        )

    def _build_suite_semaphores(
        self, items: list[TestItem]
    ) -> dict[str | None, asyncio.Semaphore]:
        """Build per-suite semaphores for max_concurrency."""
        semaphores: dict[str | None, asyncio.Semaphore] = {}
        seen_suites: set[str | None] = set()

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

    async def _ensure_suite_hierarchy_started(self, suite_path: str) -> None:
        """Ensure suite and all parent suites are started with autouse resolved."""
        assert self._suite_start_lock is not None
        parts = suite_path.split("::")
        for idx in range(len(parts)):
            parent_path = "::".join(parts[: idx + 1])
            if parent_path in self._started_suites:
                continue
            async with self._suite_start_lock:
                if parent_path in self._started_suites:
                    continue
                await self._session.events.emit(Event.SUITE_START, parent_path)
                set_session_setup_capture(True)
                try:
                    await self._session.resolver.resolve_suite_autouse(parent_path)
                finally:
                    set_session_setup_capture(False)
                self._started_suites.add(parent_path)

    async def _run_all_parallel(
        self,
        items: list[TestItem],
        suite_semaphores: dict[str | None, asyncio.Semaphore],
        tracker: SuiteTracker,
    ) -> TestCounts:
        """Run all tests in parallel using a worker pool (FIFO order).

        Uses a Queue + Workers pattern instead of creating all tasks at once.
        This provides O(concurrency) memory usage instead of O(N) tasks,
        and guarantees FIFO execution order.
        """
        if not items:
            return TestCounts()

        # Create work queue (FIFO)
        work_queue: asyncio.Queue[TestItem | None] = asyncio.Queue()
        for item in items:
            await work_queue.put(item)

        # Add sentinel values to stop workers
        for _ in range(self._session.concurrency):
            await work_queue.put(None)

        # Shared state
        stop_flag = asyncio.Event() if self._session.exitfirst else None
        results: list[TestOutcome] = []
        results_lock = asyncio.Lock()
        handler = self._interrupt_handler

        async def worker() -> None:
            """Worker that processes tests from the queue in FIFO order."""
            while True:
                # Early exit checks before getting next item
                if handler.soft_stop_event.is_set():
                    return
                if stop_flag and stop_flag.is_set():
                    return

                # Get next item (FIFO)
                item = await work_queue.get()
                if item is None:  # Sentinel - no more work
                    work_queue.task_done()
                    return

                try:
                    outcome = await self._process_test_item(
                        item, suite_semaphores, tracker, stop_flag
                    )
                    if outcome:
                        async with results_lock:
                            results.append(outcome)

                        # exitfirst: signal stop on failure
                        if stop_flag and (
                            outcome.counts.failed or outcome.counts.errored
                        ):
                            stop_flag.set()
                finally:
                    work_queue.task_done()

        # Launch workers (number of workers = concurrency limit)
        worker_tasks = [
            asyncio.create_task(worker()) for _ in range(self._session.concurrency)
        ]

        # Wait for completion with interrupt support
        await self._wait_with_interrupt(worker_tasks, stop_flag)

        # Aggregate results
        return self._aggregate_results(results)

    def _should_stop(self, stop_flag: asyncio.Event | None) -> bool:
        """Check if execution should stop (interrupt or exitfirst)."""
        return self._interrupt_handler.soft_stop_event.is_set() or bool(
            stop_flag and stop_flag.is_set()
        )

    async def _process_test_item(
        self,
        item: TestItem,
        suite_semaphores: dict[str | None, asyncio.Semaphore],
        tracker: SuiteTracker,
        stop_flag: asyncio.Event | None,
    ) -> TestOutcome | None:
        """Process a single test item. Returns None if interrupted."""
        # Re-check flags (another worker may have set them)
        if self._should_stop(stop_flag):
            return None

        suite_path = item.suite.full_path if item.suite else None
        suite_sem = suite_semaphores.get(suite_path)

        # Ensure suite hierarchy is started (with autouse fixtures)
        if suite_path:
            await self._ensure_suite_hierarchy_started(suite_path)

        # Emit TEST_START before execution (preserves current behavior)
        test_name = get_callable_name(item.func)
        node_id = item.node_id
        start_info = TestStartInfo(name=test_name, node_id=node_id)
        await self._session.events.emit(Event.TEST_START, start_info)

        # Check flags again after potential await
        if self._should_stop(stop_flag):
            return None

        # Execute with suite semaphore if applicable
        if suite_sem:
            async with suite_sem:
                if self._should_stop(stop_flag):
                    return None
                outcome = await self._execute_test(item, start_info)
        else:
            outcome = await self._execute_test(item, start_info)

        # Emit result event
        await self._session.events.emit(outcome.event, outcome.result)

        # Track suite completion and trigger teardown if last test
        if suite_path and await tracker.mark_completed(suite_path):
            await self._teardown_suite(suite_path)
        elif suite_path is None:
            await tracker.mark_completed(None)

        return outcome

    async def _wait_with_interrupt(
        self,
        worker_tasks: list[asyncio.Task[None]],
        stop_flag: asyncio.Event | None = None,
    ) -> None:
        """Wait for workers to complete with interrupt and exitfirst support."""
        handler = self._interrupt_handler

        async def wait_workers() -> None:
            await asyncio.gather(*worker_tasks, return_exceptions=True)

        async def wait_force_teardown() -> bool:
            await handler.force_teardown_event.wait()
            return True

        async def wait_stop_flag() -> bool:
            if stop_flag:
                await stop_flag.wait()
            return True

        workers_done = asyncio.create_task(wait_workers())
        force_teardown = asyncio.create_task(wait_force_teardown())

        wait_tasks: set[asyncio.Task[None] | asyncio.Task[bool]] = {
            workers_done,
            force_teardown,
        }

        # Add exitfirst monitor if enabled
        exitfirst_task: asyncio.Task[bool] | None = None
        if stop_flag:
            exitfirst_task = asyncio.create_task(wait_stop_flag())
            wait_tasks.add(exitfirst_task)

        done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

        if force_teardown in done:
            # Force teardown triggered - cancel all workers
            await self._session.events.emit(Event.SESSION_INTERRUPTED, True)
            self._force_interrupt_emitted = True
            for task in worker_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            if exitfirst_task:
                exitfirst_task.cancel()
        elif exitfirst_task and exitfirst_task in done:
            # Exitfirst triggered - cancel workers running slow tests
            for task in worker_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            force_teardown.cancel()
        else:
            # Workers completed normally
            force_teardown.cancel()
            if exitfirst_task:
                exitfirst_task.cancel()
            if handler.soft_stop_event.is_set():
                await self._session.events.emit(Event.SESSION_INTERRUPTED, False)

    def _aggregate_results(self, results: list[TestOutcome]) -> TestCounts:
        """Aggregate test outcomes into total counts."""
        total = TestCounts()
        for outcome in results:
            total = total + outcome.counts
        return total

    async def _execute_test(
        self, item: TestItem, start_info: TestStartInfo
    ) -> TestOutcome:
        """Execute a single test with capture and context."""
        await self._session.events.emit(Event.TEST_ACQUIRED, start_info)
        node_id_token = set_current_node_id(start_info.node_id)
        try:
            with CaptureCurrentTest() as buffer:
                async with TestExecutionContext(
                    self._session.resolver, item.suite_path
                ) as ctx:
                    outcome = await self._run_test(item, ctx, buffer, start_info)
                    teardown_info = TestTeardownInfo(
                        name=start_info.name,
                        node_id=start_info.node_id,
                        outcome=outcome.event,
                    )
                    await self._session.events.emit(
                        Event.TEST_TEARDOWN_START, teardown_info
                    )
            return outcome  # pyright: ignore[reportPossiblyUnboundVariable]
        finally:
            reset_current_node_id(node_id_token)

    async def _teardown_suite(self, suite_path: str) -> None:
        """Teardown suite fixtures after all its tests complete."""
        await self._session.events.emit(Event.SUITE_TEARDOWN_START, suite_path)
        set_session_teardown_capture(True)
        try:
            await self._session.resolver.teardown_suite(suite_path)
        finally:
            set_session_teardown_capture(False)
        await self._session.events.emit(Event.SUITE_TEARDOWN_DONE, suite_path)

    async def _resolve_test_kwargs(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
    ) -> dict[str, Any]:
        """Resolve fixture dependencies for a test."""
        func_signature = signature(item.func)
        kwargs: dict[str, Any] = dict(item.case_kwargs)

        try:
            type_hints = get_type_hints(item.func, include_extras=True)
        except Exception:
            type_hints = {}

        for param_name, param in func_signature.parameters.items():
            if param_name in kwargs:
                continue
            resolved_annotation = type_hints.get(param_name, param.annotation)
            if dependency := Resolver._extract_dependency_from_annotation(
                resolved_annotation
            ):
                kwargs[param_name] = await ctx.resolve(dependency)

        return kwargs

    async def _run_test(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
        buffer: io.StringIO,
        start_info: TestStartInfo,
    ) -> TestOutcome:
        """Run a single test and return outcome (event emitted by caller)."""
        test_name = start_info.name
        node_id = start_info.node_id

        if item.skip:
            return self._outcome_builder.build(
                TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    skip_reason=item.skip.reason,
                )
            )

        start = time.perf_counter()

        try:
            kwargs = await self._resolve_test_kwargs(item, ctx)
        except Exception as exc:
            return self._outcome_builder.build(
                TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    duration=time.perf_counter() - start,
                    output=buffer.getvalue(),
                    error=exc,
                    is_fixture_error=True,
                )
            )

        await self._session.events.emit(Event.TEST_SETUP_DONE, start_info)

        max_attempts = 1 + (item.retry.times if item.retry else 0)
        previous_errors: list[Exception] = []
        error: Exception | None = None
        is_fixture_error = False

        for attempt in range(1, max_attempts + 1):
            error = None
            is_fixture_error = False

            try:
                if item.timeout is not None:
                    await asyncio.wait_for(
                        ensure_async(item.func, **kwargs),
                        timeout=item.timeout,
                    )
                else:
                    await ensure_async(item.func, **kwargs)
            except asyncio.TimeoutError:
                error = asyncio.TimeoutError(
                    f"Test exceeded timeout of {item.timeout}s"
                )
            except FixtureError as exc:
                error = exc.original
                is_fixture_error = True
            except Exception as exc:
                error = exc

            retry_on = item.retry.on if item.retry else None
            retry_delay = item.retry.delay if item.retry else 0
            should_retry = (
                error is not None
                and not is_fixture_error
                and attempt < max_attempts
                and self._should_retry(error, retry_on)
            )
            if should_retry and error is not None:
                previous_errors.append(error)
                retry_info = TestRetryInfo(
                    name=test_name,
                    node_id=node_id,
                    suite_path=item.suite_path,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=error,
                    delay=retry_delay,
                )
                await self._session.events.emit(Event.TEST_RETRY, retry_info)
                if retry_delay > 0:
                    await asyncio.sleep(retry_delay)
                continue
            break

        return self._outcome_builder.build(
            TestExecutionResult(
                test_name=test_name,
                node_id=node_id,
                suite_path=item.suite_path,
                duration=time.perf_counter() - start,
                output=buffer.getvalue(),
                error=error,
                is_fixture_error=is_fixture_error,
                xfail_reason=item.xfail.reason
                if item.xfail and not is_fixture_error
                else None,
                timeout=item.timeout,
                attempt=attempt,
                max_attempts=max_attempts,
                previous_errors=tuple(previous_errors),
            )
        )

    def _should_retry(
        self,
        error: Exception,
        retry_on: type[Exception] | tuple[type[Exception], ...] | None,
    ) -> bool:
        return retry_on is None or isinstance(error, retry_on)
