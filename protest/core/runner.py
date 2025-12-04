import asyncio
import contextlib
import io
import time
from dataclasses import dataclass
from inspect import signature
from typing import Any

from protest.core.collector import (
    Collector,
    chunk_by_suite,
    get_last_chunk_index_per_suite,
)
from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.entities import (
    SessionResult,
    TestCounts,
    TestItem,
    TestOutcome,
    TestResult,
    TestStartInfo,
)
from protest.events.types import Event
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async
from protest.execution.capture import CaptureCurrentTest, GlobalCapturePatch
from protest.execution.context import TestExecutionContext
from protest.utils import get_callable_name


@dataclass
class _TestExecutionResult:
    """Internal result of test execution before outcome determination."""

    test_name: str
    node_id: str
    duration: float = 0
    output: str = ""
    error: Exception | None = None
    is_fixture_error: bool = False
    skip_reason: str | None = None
    xfail_reason: str | None = None


class TestRunner:
    """Executes tests with parallel support and fixture lifecycle management.

    Handles chunking by suite, concurrent execution within chunks,
    and proper teardown of SUITE-scoped fixtures between suites.
    """

    def __init__(self, session: ProTestSession) -> None:
        self._session = session

    def run(self) -> bool:
        """Run the test session synchronously. Returns True if all tests passed."""
        return asyncio.run(self._main_loop())

    async def _main_loop(self) -> bool:
        """The main async loop for running tests."""
        total_counts = TestCounts()
        session_start = time.perf_counter()

        collector = Collector()
        items = collector.collect(self._session)

        items = await self._session.events.emit_and_collect(
            Event.COLLECTION_FINISH, items
        )

        chunks = chunk_by_suite(items)
        last_chunk_per_suite = get_last_chunk_index_per_suite(chunks)

        await self._session.events.emit(Event.SESSION_START)

        with GlobalCapturePatch():
            async with self._session:
                await self._session.resolve_autouse()

                current_suite_path: str | None = None

                for chunk_idx, chunk in enumerate(chunks):
                    suite = chunk[0].suite
                    suite_path = suite.full_path if suite else None

                    if suite_path != current_suite_path:
                        if current_suite_path is not None:
                            await self._session.events.emit(
                                Event.SUITE_END, current_suite_path
                            )
                        current_suite_path = suite_path
                        if current_suite_path is not None:
                            await self._session.events.emit(
                                Event.SUITE_START, current_suite_path
                            )

                    concurrency = self._session.concurrency
                    if suite and suite.max_concurrency:
                        concurrency = min(concurrency, suite.max_concurrency)
                    semaphore = asyncio.Semaphore(concurrency)

                    chunk_counts = await self._run_chunk_parallel(chunk, semaphore)
                    total_counts = total_counts + chunk_counts

                    if self._session.exitfirst and (
                        chunk_counts.failed or chunk_counts.errored
                    ):
                        break

                    if (
                        suite_path is not None
                        and last_chunk_per_suite.get(suite_path) == chunk_idx
                    ):
                        await self._session.resolver.teardown_suite(suite_path)

                if current_suite_path is not None:
                    await self._session.events.emit(Event.SUITE_END, current_suite_path)

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=total_counts.passed,
            failed=total_counts.failed,
            errors=total_counts.errored,
            skipped=total_counts.skipped,
            xfailed=total_counts.xfailed,
            xpassed=total_counts.xpassed,
            duration=session_duration,
        )
        await self._session.events.emit(Event.SESSION_END, session_result)
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

    async def _run_chunk_parallel(
        self,
        chunk: list[TestItem],
        semaphore: asyncio.Semaphore,
    ) -> TestCounts:
        """Run a chunk of tests in parallel with concurrency control."""
        if not chunk:
            return TestCounts()

        async def run_one(item: TestItem) -> TestOutcome:
            test_name = get_callable_name(item.func)
            node_id = item.node_id
            start_info = TestStartInfo(name=test_name, node_id=node_id)
            await self._session.events.emit(Event.TEST_START, start_info)

            async with semaphore:
                with CaptureCurrentTest() as buffer:
                    async with TestExecutionContext(
                        self._session.resolver, item.suite_path
                    ) as ctx:
                        outcome = await self._run_test(item, ctx, buffer)

            await self._session.events.emit(outcome.event, outcome.result)
            return outcome

        tasks = [asyncio.create_task(run_one(item)) for item in chunk]

        if self._session.exitfirst:
            return await self._run_with_exitfirst(tasks)

        outcomes = await asyncio.gather(*tasks)
        total = TestCounts()
        for outcome in outcomes:
            total = total + outcome.counts
        return total

    async def _run_with_exitfirst(
        self, tasks: list[asyncio.Task[TestOutcome]]
    ) -> TestCounts:
        """Run tasks and cancel remaining on first failure."""
        total = TestCounts()
        pending = set(tasks)

        while pending:
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                outcome = task.result()
                total = total + outcome.counts

                if outcome.counts.failed or outcome.counts.errored:
                    for remaining in pending:
                        remaining.cancel()
                    for remaining in pending:
                        with contextlib.suppress(asyncio.CancelledError):
                            await remaining
                    return total

        return total

    async def _resolve_test_kwargs(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
    ) -> dict[str, Any]:
        """Resolve fixture dependencies for a test."""
        func_signature = signature(item.func)
        kwargs: dict[str, Any] = dict(item.case_kwargs)

        for param_name, param in func_signature.parameters.items():
            if param_name in kwargs:
                continue
            if dependency := Resolver._extract_dependency_from_parameter(param):
                kwargs[param_name] = await ctx.resolve(dependency)

        return kwargs

    def _build_outcome(self, exec_result: _TestExecutionResult) -> TestOutcome:
        """Build TestOutcome based on test execution results."""
        if exec_result.skip_reason:
            result = TestResult(
                name=exec_result.test_name,
                node_id=exec_result.node_id,
                skip_reason=exec_result.skip_reason,
            )
            return TestOutcome(result, TestCounts(skipped=1), Event.TEST_SKIP)

        if exec_result.error is None:
            if exec_result.xfail_reason:
                result = TestResult(
                    name=exec_result.test_name,
                    node_id=exec_result.node_id,
                    duration=exec_result.duration,
                    output=exec_result.output,
                    xfail_reason=exec_result.xfail_reason,
                )
                return TestOutcome(result, TestCounts(xpassed=1), Event.TEST_XPASS)
            result = TestResult(
                name=exec_result.test_name,
                node_id=exec_result.node_id,
                duration=exec_result.duration,
                output=exec_result.output,
            )
            return TestOutcome(result, TestCounts(passed=1), Event.TEST_PASS)

        if exec_result.is_fixture_error:
            result = TestResult(
                name=exec_result.test_name,
                node_id=exec_result.node_id,
                error=exec_result.error,
                duration=exec_result.duration,
                output=exec_result.output,
                is_fixture_error=True,
            )
            return TestOutcome(result, TestCounts(errored=1), Event.TEST_FAIL)

        if exec_result.xfail_reason:
            result = TestResult(
                name=exec_result.test_name,
                node_id=exec_result.node_id,
                error=exec_result.error,
                duration=exec_result.duration,
                output=exec_result.output,
                xfail_reason=exec_result.xfail_reason,
            )
            return TestOutcome(result, TestCounts(xfailed=1), Event.TEST_XFAIL)

        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            error=exec_result.error,
            duration=exec_result.duration,
            output=exec_result.output,
        )
        return TestOutcome(result, TestCounts(failed=1), Event.TEST_FAIL)

    async def _run_test(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
        buffer: io.StringIO,
    ) -> TestOutcome:
        """Run a single test and return outcome (event emitted by caller)."""
        test_name = get_callable_name(item.func)
        node_id = item.node_id

        if item.skip_reason:
            return self._build_outcome(
                _TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    skip_reason=item.skip_reason,
                )
            )

        start_info = TestStartInfo(name=test_name, node_id=node_id)
        await self._session.events.emit(Event.TEST_START, start_info)

        start = time.perf_counter()

        try:
            kwargs = await self._resolve_test_kwargs(item, ctx)
        except Exception as exc:
            return self._build_outcome(
                _TestExecutionResult(
                    test_name=test_name,
                    node_id=node_id,
                    duration=time.perf_counter() - start,
                    output=buffer.getvalue(),
                    error=exc,
                    is_fixture_error=True,
                )
            )

        await self._session.events.emit(Event.TEST_SETUP_DONE, start_info)

        error: Exception | None = None
        is_fixture_error = False

        try:
            await ensure_async(item.func, **kwargs)
        except FixtureError as exc:
            error = exc.original
            is_fixture_error = True
        except Exception as exc:
            error = exc

        return self._build_outcome(
            _TestExecutionResult(
                test_name=test_name,
                node_id=node_id,
                duration=time.perf_counter() - start,
                output=buffer.getvalue(),
                error=error,
                is_fixture_error=is_fixture_error,
                xfail_reason=item.xfail_reason if not is_fixture_error else None,
            )
        )
