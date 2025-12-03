import inspect
import time
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from types import TracebackType
from typing import Any

from protest.compat import Self
from protest.core.fixture import is_generator_like
from protest.di.factory import FixtureFactory
from protest.di.proxy import SafeProxy
from protest.di.resolver import Resolver
from protest.entities import Fixture, FixtureCallable, FixtureInfo
from protest.events.types import Event
from protest.execution.async_bridge import ensure_async
from protest.utils import get_callable_name


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

        fixture_name = get_callable_name(fixture.func)
        kwargs = await self._resolve_dependencies(target_func)

        result: Any
        if fixture.is_factory and fixture.managed:
            result = FixtureFactory(
                fixture=fixture,
                fixture_name=fixture_name,
                resolved_dependencies=kwargs,
                exit_stack=self._exit_stack,
                cache_enabled=fixture.cache,
            )
        elif fixture.is_factory and not fixture.managed:
            result = await self._execute_fixture(fixture, kwargs, fixture_name)
            result = SafeProxy(result, fixture_name)
        else:
            result = await self._execute_fixture(fixture, kwargs, fixture_name)

        self._cache[target_func] = result
        return result

    async def _execute_fixture(
        self, fixture: Fixture, kwargs: dict[str, Any], fixture_name: str
    ) -> Any:
        """Execute a fixture function, handling generators for setup/teardown."""
        start_time = time.perf_counter()
        await self._emit_fixture_setup_async(fixture_name)

        if is_generator_like(fixture.func):
            if inspect.isasyncgenfunction(fixture.func):
                async_cm = asynccontextmanager(fixture.func)(**kwargs)
                result = await self._exit_stack.enter_async_context(async_cm)
            else:
                sync_cm = contextmanager(fixture.func)(**kwargs)
                result = self._exit_stack.enter_context(sync_cm)

            self._exit_stack.push_async_callback(
                self._emit_fixture_teardown_async, fixture_name, start_time
            )
        else:
            result = await ensure_async(fixture.func, **kwargs)

        return result

    async def _emit_fixture_setup_async(self, name: str) -> None:
        if self._parent._event_bus is None:
            return

        await self._parent._event_bus.emit(
            Event.FIXTURE_SETUP, FixtureInfo(name=name, scope="function")
        )

    async def _emit_fixture_teardown_async(self, name: str, start_time: float) -> None:
        if self._parent._event_bus is None:
            return

        duration = time.perf_counter() - start_time
        await self._parent._event_bus.emit(
            Event.FIXTURE_TEARDOWN,
            FixtureInfo(name=name, scope="function", duration=duration),
        )

    async def _resolve_dependencies(
        self, target_func: FixtureCallable
    ) -> dict[str, Any]:
        """Resolve all dependencies of a fixture."""
        kwargs: dict[str, Any] = {}
        dependencies = self._parent.get_dependencies(target_func)

        for param_name, dep_func in dependencies.items():
            kwargs[param_name] = await self.resolve(dep_func)

        return kwargs
