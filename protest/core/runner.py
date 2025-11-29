import asyncio
from collections.abc import Callable
from inspect import signature
from typing import Any

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.di.suite_resolver import SuiteResolver
from protest.execution.async_bridge import ensure_async
from protest.reporting.console import ConsoleReporter
from protest.reporting.protocol import Reporter


class TestRunner:
    def __init__(
        self, session: ProTestSession, reporter: Reporter | None = None
    ) -> None:
        self._session = session
        self._reporter: Reporter = reporter or ConsoleReporter()

    def run(self) -> bool:
        """Synchronous entry point to run the test session."""
        return asyncio.run(self._main_loop())

    async def _main_loop(self) -> bool:
        """The main async loop for running tests."""
        passed = 0
        failed = 0

        await ensure_async(self._reporter.on_session_start)

        async with self._session:
            for test_func in self._session.tests:
                if await self._run_test(test_func, self._session.resolver):
                    passed += 1
                else:
                    failed += 1

            for suite in self._session.suites:
                await ensure_async(self._reporter.on_suite_start, suite.name)
                async with suite.resolver:
                    for test_func in suite.tests:
                        if await self._run_test(test_func, suite.resolver):
                            passed += 1
                        else:
                            failed += 1
                        suite.resolver.clear_cache(Scope.FUNCTION)
                await ensure_async(self._reporter.on_suite_end, suite.name)

        await ensure_async(self._reporter.on_session_end, passed, failed)
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
        try:
            await ensure_async(test_func, **kwargs)
            await ensure_async(self._reporter.on_test_pass, test_name)
            return True
        except Exception as exc:
            await ensure_async(self._reporter.on_test_fail, test_name, exc)
            return False
