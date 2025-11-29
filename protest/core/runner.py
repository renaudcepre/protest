import asyncio
from collections.abc import Callable
from inspect import signature
from typing import Any

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.di.resolver import Resolver
from protest.di.suite_resolver import SuiteResolver
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

        async with self._session:
            for test_func in self._session.tests:
                if await self._run_test(test_func, self._session.resolver):
                    passed += 1
                else:
                    failed += 1

            for suite in self._session.suites:
                print(f"[Suite: {suite.name}]")
                async with suite.resolver:
                    for test_func in suite.tests:
                        if await self._run_test(
                            test_func, suite.resolver, indent="  "
                        ):
                            passed += 1
                        else:
                            failed += 1
                        suite.resolver.clear_cache(Scope.FUNCTION)

        total = passed + failed
        print(f"\nResults: {passed}/{total} passed")
        return failed == 0

    async def _run_test(
        self,
        test_func: Callable[..., Any],
        resolver: Resolver | SuiteResolver,
        indent: str = "",
    ) -> bool:
        func_signature = signature(test_func)
        kwargs: dict[str, Any] = {}

        # Resolve test dependencies asynchronously
        for param_name, param in func_signature.parameters.items():
            if dependency := Resolver._extract_dependency_from_parameter(param):
                kwargs[param_name] = await resolver.resolve(dependency)

        try:
            # Execute the test, supporting both sync and async functions
            await ensure_async(test_func, **kwargs)
            print(f"{indent}✓ {test_func.__name__}")
            return True
        except Exception as exc:
            print(f"{indent}✗ {test_func.__name__}: {exc}")
            return False
