import asyncio
import io
import time
from inspect import signature
from typing import Any

from protest.core.collector import (
    Collector,
    TestItem,
    chunk_by_suite,
    get_last_chunk_index_per_suite,
)
from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.events.data import SessionResult, TestCounts, TestResult
from protest.events.types import Event
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async
from protest.execution.capture import CaptureCurrentTest, GlobalCapturePatch
from protest.execution.context import TestExecutionContext


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

                current_suite: str | None = None

                for chunk_idx, chunk in enumerate(chunks):
                    suite_name = chunk[0].suite_name

                    if suite_name != current_suite:
                        if current_suite is not None:
                            await self._session.events.emit(
                                Event.SUITE_END, current_suite
                            )
                        current_suite = suite_name
                        if current_suite is not None:
                            await self._session.events.emit(
                                Event.SUITE_START, current_suite
                            )

                    suite = self._get_suite_by_name(suite_name)
                    concurrency = (
                        suite.concurrency
                        if suite and suite.concurrency
                        else self._session.concurrency
                    )
                    semaphore = asyncio.Semaphore(concurrency)

                    chunk_counts = await self._run_chunk_parallel(chunk, semaphore)
                    total_counts = total_counts + chunk_counts

                    if (
                        suite_name is not None
                        and last_chunk_per_suite.get(suite_name) == chunk_idx
                    ):
                        await self._session.resolver.teardown_suite(suite_name)

                if current_suite is not None:
                    await self._session.events.emit(Event.SUITE_END, current_suite)

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=total_counts.passed,
            failed=total_counts.failed,
            errors=total_counts.errored,
            duration=session_duration,
        )
        await self._session.events.emit(Event.SESSION_END, session_result)
        await self._session.events.wait_pending()
        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return total_counts.failed == 0 and total_counts.errored == 0

    def _get_suite_by_name(self, suite_name: str | None) -> Any:
        """Get a suite by name from the session."""
        if suite_name is None:
            return None
        for suite in self._session.suites:
            if suite.name == suite_name:
                return suite
        return None

    async def _run_chunk_parallel(
        self,
        chunk: list[TestItem],
        semaphore: asyncio.Semaphore,
    ) -> TestCounts:
        """Run a chunk of tests in parallel with concurrency control."""
        if not chunk:
            return TestCounts()

        async def run_one(item: TestItem) -> TestCounts:
            async with semaphore:
                with CaptureCurrentTest() as buffer:
                    async with TestExecutionContext(
                        self._session.resolver, item.suite_name
                    ) as ctx:
                        return await self._run_test(item, ctx, buffer)

        tasks = [asyncio.create_task(run_one(item)) for item in chunk]
        results = await asyncio.gather(*tasks)

        total = TestCounts()
        for result in results:
            total = total + result
        return total

    async def _run_test(
        self,
        item: TestItem,
        ctx: TestExecutionContext,
        buffer: io.StringIO,
    ) -> TestCounts:
        """Run a single test."""
        test_func = item.func
        test_name = getattr(test_func, "__name__", "<unnamed>")
        node_id = item.node_id
        start = time.perf_counter()

        func_signature = signature(test_func)
        kwargs: dict[str, Any] = {}

        try:
            for param_name, param in func_signature.parameters.items():
                if dependency := Resolver._extract_dependency_from_parameter(param):
                    kwargs[param_name] = await ctx.resolve(dependency)
        except Exception as exc:
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                node_id=node_id,
                error=exc,
                duration=duration,
                output=buffer.getvalue(),
                is_fixture_error=True,
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return TestCounts(errored=1)

        try:
            await ensure_async(test_func, **kwargs)
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                node_id=node_id,
                duration=duration,
                output=buffer.getvalue(),
            )
            await self._session.events.emit(Event.TEST_PASS, result)
            return TestCounts(passed=1)
        except FixtureError as exc:
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                node_id=node_id,
                error=exc.original,
                duration=duration,
                output=buffer.getvalue(),
                is_fixture_error=True,
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return TestCounts(errored=1)
        except Exception as exc:
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                node_id=node_id,
                error=exc,
                duration=duration,
                output=buffer.getvalue(),
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return TestCounts(failed=1)
