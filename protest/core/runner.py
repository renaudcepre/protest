import asyncio
import time
from collections.abc import Callable
from inspect import signature
from typing import Any

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.di.suite_resolver import SuiteResolver
from protest.events.data import SessionResult, TestResult
from protest.events.types import Event
from protest.execution.async_bridge import ensure_async


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

        await self._session.events.emit(Event.SESSION_START)

        async with self._session:
            for test_func in self._session.tests:
                if await self._run_test(test_func, self._session.resolver):
                    passed += 1
                else:
                    failed += 1

            for suite in self._session.suites:
                await self._session.events.emit(Event.SUITE_START, suite.name)
                async with suite.resolver:
                    for test_func in suite.tests:
                        if await self._run_test(test_func, suite.resolver):
                            passed += 1
                        else:
                            failed += 1
                        suite.resolver.clear_cache(Scope.FUNCTION)
                await self._session.events.emit(Event.SUITE_END, suite.name)

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=passed, failed=failed, duration=session_duration
        )
        await self._session.events.emit(Event.SESSION_END, session_result)
        await self._session.events.wait_pending()
        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return failed == 0

    async def _run_test(
        self,
        test_func: Callable[..., Any],
        resolver: Resolver | SuiteResolver,
    ) -> bool:
        func_signature = signature(test_func)
        kwargs: dict[str, Any] = {}

        for param_name, param in func_signature.parameters.items():
            if dependency := Resolver._extract_dependency_from_parameter(param):
                kwargs[param_name] = await resolver.resolve(dependency)

        test_name = getattr(test_func, "__name__", "<unnamed>")
        start = time.perf_counter()
        try:
            await ensure_async(test_func, **kwargs)
            duration = time.perf_counter() - start
            result = TestResult(name=test_name, duration=duration)
            await self._session.events.emit(Event.TEST_PASS, result)
            return True
        except Exception as exc:
            duration = time.perf_counter() - start
            result = TestResult(name=test_name, error=exc, duration=duration)
            await self._session.events.emit(Event.TEST_FAIL, result)
            return False
