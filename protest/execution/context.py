"""Per-test execution context for isolated FUNCTION-scoped fixtures."""

import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import TracebackType
from typing import Any

from protest.compat import Self
from protest.core.fixture import (
    Fixture,
    FixtureCallable,
    get_callable_name,
    is_generator_like,
)
from protest.di.resolver import Resolver, _wrap_factory
from protest.execution.async_bridge import ensure_async


class TestExecutionContext:
    """Isolated context for a single test execution.

    Manages FUNCTION-scoped fixtures independently per test, allowing parallel
    execution. Suite and session scoped fixtures are delegated to the parent resolver.
    """

    def __init__(self, parent: Resolver, suite_path: str | None = None) -> None:
        self._parent = parent
        self._suite_path = suite_path
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
        fixture = self._parent._ensure_registered(target_func)
        scope_path = self._parent.get_scope_path(target_func)

        if scope_path == Resolver.FUNCTION_SCOPE:
            return await self._resolve_function_scoped(target_func, fixture)
        return await self._parent.resolve(target_func, current_path=self._suite_path)

    async def _resolve_function_scoped(
        self, target_func: FixtureCallable, fixture: Fixture
    ) -> Any:
        """Resolve a FUNCTION-scoped fixture with local caching and teardown."""
        if target_func in self._cache:
            return self._cache[target_func]

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

        if fixture.is_factory:
            result = _wrap_factory(result, get_callable_name(fixture.func))

        self._cache[target_func] = result
        return result

    async def _resolve_dependencies(
        self, target_func: FixtureCallable
    ) -> dict[str, Any]:
        """Resolve all dependencies of a fixture."""
        kwargs: dict[str, Any] = {}
        dependencies = self._parent.get_dependencies(target_func)

        for param_name, dep_func in dependencies.items():
            kwargs[param_name] = await self.resolve(dep_func)

        return kwargs
