"""Per-test execution context for isolated FUNCTION-scoped fixtures."""

import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import TracebackType
from typing import Any, Self

from protest.core.fixture import (
    FixtureCallable,
    get_callable_name,
    is_generator_like,
)
from protest.core.scope import Scope
from protest.di.resolver import FixtureNotFoundError, Resolver
from protest.di.suite_resolver import SuiteResolver
from protest.execution.async_bridge import ensure_async


class TestExecutionContext:
    """Isolated context for a single test execution.

    Manages FUNCTION-scoped fixtures independently per test, allowing parallel
    execution. SUITE and SESSION scoped fixtures are delegated to the parent resolver.
    """

    def __init__(self, parent: Resolver | SuiteResolver) -> None:
        self._parent = parent
        self._cache: dict[FixtureCallable, Any] = {}
        self._exit_stack = AsyncExitStack()

    async def __aenter__(self) -> Self:
        await self._exit_stack.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        result = await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
        return result or False

    async def resolve(self, target_func: FixtureCallable) -> Any:
        """Resolve a fixture, isolating FUNCTION scope to this context."""
        scope = self._get_scope(target_func)

        if scope == Scope.FUNCTION:
            return await self._resolve_function_scoped(target_func)
        return await self._parent.resolve(target_func)

    async def _resolve_function_scoped(self, target_func: FixtureCallable) -> Any:
        """Resolve a FUNCTION-scoped fixture with local caching and teardown."""
        if target_func in self._cache:
            return self._cache[target_func]

        fixture = self._get_fixture(target_func)
        kwargs = await self._resolve_dependencies(target_func)

        if is_generator_like(fixture.func):
            if inspect.isasyncgenfunction(fixture.func):
                async_cm = asynccontextmanager(fixture.func)(**kwargs)
                result = await self._exit_stack.enter_async_context(async_cm)
            else:
                sync_cm = contextmanager(fixture.func)(**kwargs)
                result = self._exit_stack.enter_context(sync_cm)
        else:
            result = await ensure_async(fixture.func, **kwargs)

        self._cache[target_func] = result
        return result

    async def _resolve_dependencies(
        self, target_func: FixtureCallable
    ) -> dict[str, Any]:
        """Resolve all dependencies of a fixture."""
        kwargs: dict[str, Any] = {}
        dependencies = self._get_dependencies(target_func)

        for param_name, dep_func in dependencies.items():
            kwargs[param_name] = await self.resolve(dep_func)

        return kwargs

    def _get_scope(self, func: FixtureCallable) -> Scope:
        """Get the scope of a fixture from parent resolver."""
        fixture = self._get_fixture(func)
        return fixture.scope

    def _get_fixture(self, func: FixtureCallable):
        """Get fixture from parent registry."""
        fixture = self._parent.get_fixture(func)
        if fixture is not None:
            return fixture
        if isinstance(self._parent, SuiteResolver):
            fixture = self._parent._parent_resolver.get_fixture(func)
            if fixture is not None:
                return fixture
        raise FixtureNotFoundError(get_callable_name(func))

    def _get_dependencies(self, func: FixtureCallable) -> dict[str, FixtureCallable]:
        """Get dependencies from parent resolver."""
        deps = self._parent.get_dependencies(func)
        if deps:
            return deps
        if isinstance(self._parent, SuiteResolver):
            return self._parent._parent_resolver.get_dependencies(func)
        return {}
