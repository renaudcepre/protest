import asyncio
import time
from collections.abc import Callable
from inspect import signature
from typing import Any

from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.events.data import SessionResult, TestResult
from protest.events.types import Event
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
        session_start = time.perf_counter()
        concurrency = self._session.concurrency

        await self._session.events.emit(Event.SESSION_START)

        semaphore = asyncio.Semaphore(concurrency)

        with GlobalCapturePatch():
            async with self._session:
                await self._session.resolve_autouse()

                session_passed, session_failed = await self._run_tests_parallel(
                    self._session.tests,
                    self._session.resolver,
                    semaphore,
                    suite_name=None,
                )
                passed += session_passed
                failed += session_failed

                for suite in self._session.suites:
                    await self._session.events.emit(Event.SUITE_START, suite.name)
                    suite_concurrency = suite.concurrency or concurrency
                    suite_semaphore = asyncio.Semaphore(suite_concurrency)

                    suite_passed, suite_failed = await self._run_tests_parallel(
                        suite.tests,
                        self._session.resolver,
                        suite_semaphore,
                        suite_name=suite.name,
                    )
                    passed += suite_passed
                    failed += suite_failed

                    await self._session.resolver.teardown_suite(suite.name)
                    await self._session.events.emit(Event.SUITE_END, suite.name)

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=passed, failed=failed, duration=session_duration
        )
        await self._session.events.emit(Event.SESSION_END, session_result)
        await self._session.events.wait_pending()
        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return failed == 0

    async def _run_tests_parallel(
        self,
        tests: list[Callable[..., Any]],
        resolver: Resolver,
        semaphore: asyncio.Semaphore,
        suite_name: str | None = None,
    ) -> tuple[int, int]:
        """Run tests with concurrency control. Returns (passed, failed)."""
        if not tests:
            return 0, 0

        async def run_one(test_func: Callable[..., Any]) -> bool:
            async with semaphore, TestExecutionContext(resolver, suite_name) as ctx:
                return await self._run_test(test_func, ctx)

        tasks = [asyncio.create_task(run_one(test)) for test in tests]
        results = await asyncio.gather(*tasks)

        passed = sum(results)
        failed = len(results) - passed
        return passed, failed

    async def _run_test(
        self,
        test_func: Callable[..., Any],
        ctx: TestExecutionContext,
    ) -> bool:
        func_signature = signature(test_func)
        kwargs: dict[str, Any] = {}

        for param_name, param in func_signature.parameters.items():
            if dependency := Resolver._extract_dependency_from_parameter(param):
                kwargs[param_name] = await ctx.resolve(dependency)

        test_name = getattr(test_func, "__name__", "<unnamed>")
        start = time.perf_counter()

        with CaptureCurrentTest() as buffer:
            try:
                await ensure_async(test_func, **kwargs)
                duration = time.perf_counter() - start
                result = TestResult(
                    name=test_name, duration=duration, output=buffer.getvalue()
                )
                await self._session.events.emit(Event.TEST_PASS, result)
                return True
            except Exception as exc:
                duration = time.perf_counter() - start
                result = TestResult(
                    name=test_name,
                    error=exc,
                    duration=duration,
                    output=buffer.getvalue(),
                )
                await self._session.events.emit(Event.TEST_FAIL, result)
                return False
