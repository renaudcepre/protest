import asyncio
import functools
import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from inspect import signature
from types import TracebackType
from typing import Annotated, Any, get_args, get_origin

from protest.core.fixture import (
    Fixture,
    FixtureCallable,
    get_callable_name,
    is_generator_like,
)
from protest.core.scope import Scope
from protest.di.decorators import get_fixture_scope, is_factory_fixture
from protest.di.markers import Use
from protest.exceptions import FixtureError, ProTestError
from protest.execution.async_bridge import ensure_async


def _wrap_factory(result: Any, fixture_name: str) -> Any:
    """Wrap a factory to convert its exceptions to FixtureError."""
    if not callable(result):
        return result

    if inspect.iscoroutinefunction(result):

        @functools.wraps(result)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await result(*args, **kwargs)
            except Exception as exc:
                raise FixtureError(fixture_name, exc) from exc

        return async_wrapper

    @functools.wraps(result)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return result(*args, **kwargs)
        except Exception as exc:
            raise FixtureError(fixture_name, exc) from exc

    return sync_wrapper


class ScopeMismatchError(ProTestError):
    def __init__(
        self,
        requester_name: str,
        requester_scope: str,
        dependency_name: str,
        dependency_scope: str,
    ):
        super().__init__(
            f"Fixture '{requester_name}' with scope {requester_scope} "
            f"cannot depend on '{dependency_name}' with scope {dependency_scope}."
        )


class AlreadyRegisteredError(ProTestError):
    def __init__(self, function_name: str):
        super().__init__(f"Function '{function_name}' is already registered.")


class UnregisteredDependencyError(ProTestError):
    def __init__(self, fixture_name: str, dependency_name: str):
        super().__init__(
            f"Fixture '{fixture_name}' depends on unregistered "
            f"function '{dependency_name}'. "
            f"Register '{dependency_name}' first."
        )


class FixtureNotFoundError(ProTestError):
    def __init__(self, fixture_name: str):
        super().__init__(f"Fixture '{fixture_name}' is not registered.")


class Resolver:
    """Manages fixture registration, dependency analysis, and resolution."""

    def __init__(self) -> None:
        self._registry: dict[FixtureCallable, Fixture] = {}
        self._dependencies: dict[FixtureCallable, dict[str, FixtureCallable]] = {}
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._resolve_locks: dict[FixtureCallable, asyncio.Lock] = {}
        self._suite_cache: dict[tuple[FixtureCallable, str], object] = {}
        self._suite_exit_stacks: dict[str, AsyncExitStack] = {}

    def register(self, func: FixtureCallable, scope: Scope) -> None:
        """Analyzes a function's dependencies and registers it as a Fixture."""
        if func in self._registry:
            raise AlreadyRegisteredError(get_callable_name(func))

        is_factory = is_factory_fixture(func)
        fixture = Fixture(func, scope, is_factory=is_factory)
        self._analyze_and_store_dependencies(fixture)
        self._registry[func] = fixture
        self._resolve_locks[func] = asyncio.Lock()

    def has_fixture(self, func: FixtureCallable) -> bool:
        """Check if a fixture is registered."""
        return func in self._registry

    def get_fixture(self, func: FixtureCallable) -> Fixture | None:
        """Get a fixture by its function, or None if not registered."""
        return self._registry.get(func)

    def get_dependencies(self, func: FixtureCallable) -> dict[str, FixtureCallable]:
        """Get dependencies for a fixture function."""
        return self._dependencies.get(func, {})

    def _ensure_registered(self, func: FixtureCallable) -> Fixture:
        """Auto-register a fixture if not yet registered and return it.

        Decorated functions use their declared scope.
        Undecorated functions default to FUNCTION scope.
        """
        if func not in self._registry:
            scope = get_fixture_scope(func) or Scope.FUNCTION
            self.register(func, scope)
        return self._registry[func]

    async def resolve(
        self, target_func: FixtureCallable, suite_name: str | None = None
    ) -> Any:
        """Resolve a fixture recursively, handling generators for setup/teardown.

        Generator fixtures (with yield) are wrapped as context managers and pushed
        onto the exit stack. Teardown runs when exiting the resolver context.
        Regular fixtures are called via ensure_async.

        Uses per-fixture locks to prevent race conditions in parallel execution.

        For SUITE-scoped fixtures, suite_name must be provided and caching is per-suite.
        """
        self._ensure_registered(target_func)
        target_fixture = self._registry[target_func]

        if target_fixture.scope == Scope.SUITE:
            if suite_name is None:
                msg = (
                    f"SUITE-scoped fixture '{get_callable_name(target_func)}'"
                    f" requires suite context"
                )
                raise RuntimeError(msg)
            return await self._resolve_suite_scoped(target_fixture, suite_name)

        return await self._resolve_session_scoped(target_fixture, suite_name)

    async def _resolve_session_scoped(
        self, target_fixture: Fixture, suite_name: str | None
    ) -> Any:
        """Resolve a SESSION-scoped fixture with global caching."""
        if target_fixture.is_cached:
            return target_fixture.cached_value

        async with self._resolve_locks[target_fixture.func]:
            if target_fixture.is_cached:
                return target_fixture.cached_value

            kwargs = await self._resolve_dependencies(target_fixture.func, suite_name)
            result = await self._execute_fixture(
                target_fixture, kwargs, self._exit_stack
            )

            target_fixture.cached_value = result
            target_fixture.is_cached = True
            return result

    async def _resolve_suite_scoped(
        self, target_fixture: Fixture, suite_name: str
    ) -> Any:
        """Resolve a SUITE-scoped fixture with per-suite caching."""
        cache_key = (target_fixture.func, suite_name)
        if cache_key in self._suite_cache:
            return self._suite_cache[cache_key]

        async with self._resolve_locks[target_fixture.func]:
            if cache_key in self._suite_cache:
                return self._suite_cache[cache_key]

            if suite_name not in self._suite_exit_stacks:
                self._suite_exit_stacks[suite_name] = AsyncExitStack()

            kwargs = await self._resolve_dependencies(target_fixture.func, suite_name)
            result = await self._execute_fixture(
                target_fixture, kwargs, self._suite_exit_stacks[suite_name]
            )

            self._suite_cache[cache_key] = result
            return result

    async def _resolve_dependencies(
        self, target_func: FixtureCallable, suite_name: str | None
    ) -> dict[str, Any]:
        """Resolve all dependencies for a fixture."""
        kwargs: dict[str, Any] = {}
        for param_name, dep_func in self._dependencies.get(target_func, {}).items():
            kwargs[param_name] = await self.resolve(dep_func, suite_name)
        return kwargs

    async def _execute_fixture(
        self, fixture: Fixture, kwargs: dict[str, Any], exit_stack: AsyncExitStack
    ) -> Any:
        """Execute fixture function, handling generators for setup/teardown."""
        if is_generator_like(fixture.func):
            if inspect.isasyncgenfunction(fixture.func):
                async_cm = asynccontextmanager(fixture.func)(**kwargs)
                result = await exit_stack.enter_async_context(async_cm)
            else:
                sync_cm = contextmanager(fixture.func)(**kwargs)
                result = exit_stack.enter_context(sync_cm)
        else:
            result = await ensure_async(fixture.func, **kwargs)

        if fixture.is_factory:
            return _wrap_factory(result, get_callable_name(fixture.func))
        return result

    async def teardown_suite(self, suite_name: str) -> None:
        """Teardown all SUITE-scoped fixtures for a given suite."""
        if suite_name in self._suite_exit_stacks:
            await self._suite_exit_stacks[suite_name].aclose()
            del self._suite_exit_stacks[suite_name]
        keys_to_remove = [key for key in self._suite_cache if key[1] == suite_name]
        for key in keys_to_remove:
            del self._suite_cache[key]

    async def __aenter__(self) -> "Resolver":
        """Enter resolver context. Use 'async with resolver:' for teardown."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        """Exit resolver context, triggering teardown for generator fixtures."""
        result = await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
        return result or False

    def clear_cache(self, scope: Scope) -> None:
        """Clears the cache for all fixtures within a specific scope."""
        for fixture in self._registry.values():
            if fixture.scope == scope:
                fixture.clear_cache()

    def _analyze_and_store_dependencies(self, fixture: Fixture) -> None:
        """Analyzes a fixture's function signature and populates its dependencies."""
        func_signature = signature(fixture.func)
        dependencies: dict[str, FixtureCallable] = {}
        for param_name, param in func_signature.parameters.items():
            if dependency := self._extract_dependency_from_parameter(param):
                self._ensure_registered(dependency)
                self._validate_scope(fixture, dependency)
                dependencies[param_name] = dependency
        self._dependencies[fixture.func] = dependencies

    def _validate_scope(
        self, requester: Fixture, dependency_func: FixtureCallable
    ) -> None:
        """Ensures a dependency has a wider or equal scope than its requester."""
        dependency_fixture = self._registry[dependency_func]
        if dependency_fixture.scope.value > requester.scope.value:
            raise ScopeMismatchError(
                get_callable_name(requester.func),
                requester.scope.name,
                get_callable_name(dependency_fixture.func),
                dependency_fixture.scope.name,
            )

    @staticmethod
    def _extract_dependency_from_parameter(
        param: inspect.Parameter,
    ) -> FixtureCallable | None:
        """Extract dependency from Annotated[Type, Use(fixture)] or return None."""
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        return None
