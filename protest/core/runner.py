import asyncio
import io
import time
from collections.abc import Callable
from inspect import signature
from typing import Any

from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.events.data import SessionResult, TestResult
from protest.events.types import Event
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async
from protest.execution.capture import CaptureCurrentTest, GlobalCapturePatch
from protest.execution.context import TestExecutionContext


class TestRunner:
    def __init__(self, session: ProTestSession) -> None:
        self._session = session

    def run(self) -> bool:
        """Synchronous entry point to run the test session."""
        return asyncio.run(self._main_loop())

    async def _main_loop(self) -> bool:
        """The main async loop for running tests."""
        passed = 0
        failed = 0
        errored = 0
        session_start = time.perf_counter()
        concurrency = self._session.concurrency

        await self._session.events.emit(Event.SESSION_START)

        semaphore = asyncio.Semaphore(concurrency)

        with GlobalCapturePatch():
            async with self._session:
                await self._session.resolve_autouse()

                counts = await self._run_tests_parallel(
                    self._session.tests,
                    self._session.resolver,
                    semaphore,
                    suite_name=None,
                )
                passed += counts[0]
                failed += counts[1]
                errored += counts[2]

                for suite in self._session.suites:
                    await self._session.events.emit(Event.SUITE_START, suite.name)
                    suite_concurrency = suite.concurrency or concurrency
                    suite_semaphore = asyncio.Semaphore(suite_concurrency)

                    counts = await self._run_tests_parallel(
                        suite.tests,
                        self._session.resolver,
                        suite_semaphore,
                        suite_name=suite.name,
                    )
                    passed += counts[0]
                    failed += counts[1]
                    errored += counts[2]

                    await self._session.resolver.teardown_suite(suite.name)
                    await self._session.events.emit(Event.SUITE_END, suite.name)

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=passed, failed=failed, errors=errored, duration=session_duration
        )
        await self._session.events.emit(Event.SESSION_END, session_result)
        await self._session.events.wait_pending()
        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return failed == 0 and errored == 0

    async def _run_tests_parallel(
        self,
        tests: list[Callable[..., Any]],
        resolver: Resolver,
        semaphore: asyncio.Semaphore,
        suite_name: str | None = None,
    ) -> tuple[int, int, int]:
        """Run tests with concurrency control. Returns (passed, failed, errored)."""
        if not tests:
            return 0, 0, 0

        async def run_one(test_func: Callable[..., Any]) -> tuple[int, int, int]:
            async with semaphore:
                with CaptureCurrentTest() as buffer:
                    async with TestExecutionContext(resolver, suite_name) as ctx:
                        return await self._run_test(test_func, ctx, buffer)

        tasks = [asyncio.create_task(run_one(test)) for test in tests]
        results = await asyncio.gather(*tasks)

        passed = sum(result[0] for result in results)
        failed = sum(result[1] for result in results)
        errored = sum(result[2] for result in results)
        return passed, failed, errored

    async def _run_test(
        self,
        test_func: Callable[..., Any],
        ctx: TestExecutionContext,
        buffer: io.StringIO,
    ) -> tuple[int, int, int]:
        """Run a single test. Returns (passed, failed, errored)."""
        test_name = getattr(test_func, "__name__", "<unnamed>")
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
                error=exc,
                duration=duration,
                output=buffer.getvalue(),
                is_fixture_error=True,
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return (0, 0, 1)

        try:
            await ensure_async(test_func, **kwargs)
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name, duration=duration, output=buffer.getvalue()
            )
            await self._session.events.emit(Event.TEST_PASS, result)
            return (1, 0, 0)
        except FixtureError as exc:
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                error=exc.original,
                duration=duration,
                output=buffer.getvalue(),
                is_fixture_error=True,
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return (0, 0, 1)
        except Exception as exc:
            duration = time.perf_counter() - start
            result = TestResult(
                name=test_name,
                error=exc,
                duration=duration,
                output=buffer.getvalue(),
            )
            await self._session.events.emit(Event.TEST_FAIL, result)
            return (0, 1, 0)
