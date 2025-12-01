import asyncio
import functools
import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from inspect import Parameter, signature
from types import TracebackType
from typing import Annotated, Any, get_args, get_origin

from protest.core.fixture import (
    Fixture,
    FixtureCallable,
    get_callable_name,
    is_generator_like,
)
from protest.di.markers import Use
from protest.exceptions import FixtureError, ProTestError
from protest.execution.async_bridge import ensure_async

FIXTURE_FACTORY_ATTR = "_protest_fixture_factory"


def is_factory_fixture(func: FixtureCallable) -> bool:
    return getattr(func, FIXTURE_FACTORY_ATTR, False)


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
            f"Fixture '{requester_name}' at scope '{requester_scope}' "
            f"cannot depend on '{dependency_name}' at scope '{dependency_scope}'."
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
    """Manages fixture registration, dependency analysis, and resolution.

    Scope is determined by the scope_path where a fixture is registered:
    - None: Session scope (lives entire session)
    - "SuiteName": Suite scope (lives while suite runs)
    - "Parent::Child": Nested suite scope

    Fixtures not explicitly registered are auto-registered with scope_path=FUNCTION_SCOPE
    (a special marker meaning fresh instance per test).
    """

    FUNCTION_SCOPE = "__function__"

    def __init__(self) -> None:
        self._registry: dict[FixtureCallable, Fixture] = {}
        self._dependencies: dict[FixtureCallable, dict[str, FixtureCallable]] = {}
        self._scope_paths: dict[FixtureCallable, str | None] = {}
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._resolve_locks: dict[FixtureCallable, asyncio.Lock] = {}
        self._path_caches: dict[str, dict[FixtureCallable, Any]] = {}
        self._path_exit_stacks: dict[str, AsyncExitStack] = {}

    def register(
        self,
        func: FixtureCallable,
        scope_path: str | None = None,
        is_factory: bool = False,
    ) -> None:
        """Register a fixture at a specific scope path.

        Args:
            func: The fixture function.
            scope_path: Where this fixture lives:
                - None: Session scope (global)
                - "SuiteName": Suite scope
                - "Parent::Child": Nested suite scope
                - FUNCTION_SCOPE: Function scope (fresh per test)
            is_factory: Whether this fixture returns a factory callable.
        """
        if func in self._registry:
            raise AlreadyRegisteredError(get_callable_name(func))

        fixture = Fixture(func, is_factory=is_factory)
        self._scope_paths[func] = scope_path
        self._analyze_and_store_dependencies(func, scope_path)
        self._registry[func] = fixture
        self._resolve_locks[func] = asyncio.Lock()

    def has_fixture(self, func: FixtureCallable) -> bool:
        return func in self._registry

    def get_fixture(self, func: FixtureCallable) -> Fixture | None:
        return self._registry.get(func)

    def get_scope_path(self, func: FixtureCallable) -> str | None:
        return self._scope_paths.get(func)

    def get_dependencies(self, func: FixtureCallable) -> dict[str, FixtureCallable]:
        return self._dependencies.get(func, {})

    def _ensure_registered(self, func: FixtureCallable) -> Fixture:
        """Auto-register a fixture if not yet registered.

        Unregistered functions are registered as FUNCTION scope (fresh per test).
        """
        if func not in self._registry:
            is_factory = is_factory_fixture(func)
            self.register(func, scope_path=self.FUNCTION_SCOPE, is_factory=is_factory)
        return self._registry[func]

    async def resolve(
        self,
        target_func: FixtureCallable,
        current_path: str | None = None,
    ) -> Any:
        """Resolve a fixture recursively.

        Args:
            target_func: The fixture function to resolve.
            current_path: Current execution context path (suite path for tests).

        Returns:
            The resolved fixture value.
        """
        self._ensure_registered(target_func)
        target_fixture = self._registry[target_func]
        scope_path = self._scope_paths[target_func]

        if scope_path is None:
            return await self._resolve_session_scoped(target_fixture, current_path)
        if scope_path == self.FUNCTION_SCOPE:
            return await self._resolve_function_scoped(target_fixture, current_path)
        return await self._resolve_path_scoped(target_fixture, scope_path, current_path)

    async def _resolve_session_scoped(
        self, target_fixture: Fixture, current_path: str | None
    ) -> Any:
        """Resolve a session-scoped fixture with global caching."""
        if target_fixture.is_cached:
            return target_fixture.cached_value

        async with self._resolve_locks[target_fixture.func]:
            if target_fixture.is_cached:
                return target_fixture.cached_value

            kwargs = await self._resolve_dependencies(target_fixture.func, current_path)
            result = await self._execute_fixture(
                target_fixture, kwargs, self._exit_stack
            )

            target_fixture.cached_value = result
            target_fixture.is_cached = True
            return result

    async def _resolve_path_scoped(
        self, target_fixture: Fixture, scope_path: str, current_path: str | None
    ) -> Any:
        """Resolve a path-scoped (suite) fixture with per-path caching."""
        if scope_path not in self._path_caches:
            self._path_caches[scope_path] = {}

        cache = self._path_caches[scope_path]
        if target_fixture.func in cache:
            return cache[target_fixture.func]

        async with self._resolve_locks[target_fixture.func]:
            if target_fixture.func in cache:
                return cache[target_fixture.func]

            if scope_path not in self._path_exit_stacks:
                self._path_exit_stacks[scope_path] = AsyncExitStack()

            kwargs = await self._resolve_dependencies(target_fixture.func, current_path)
            result = await self._execute_fixture(
                target_fixture, kwargs, self._path_exit_stacks[scope_path]
            )

            cache[target_fixture.func] = result
            return result

    async def _resolve_function_scoped(
        self, target_fixture: Fixture, current_path: str | None
    ) -> Any:
        """Resolve a function-scoped fixture (no caching at this level).

        Note: In practice, function-scoped fixtures are handled by TestExecutionContext
        which maintains its own cache per test. This method is a fallback.
        """
        kwargs = await self._resolve_dependencies(target_fixture.func, current_path)
        return await self._execute_fixture(target_fixture, kwargs, AsyncExitStack())

    async def _resolve_dependencies(
        self, target_func: FixtureCallable, current_path: str | None
    ) -> dict[str, Any]:
        """Resolve all dependencies for a fixture."""
        kwargs: dict[str, Any] = {}
        for param_name, dep_func in self._dependencies.get(target_func, {}).items():
            kwargs[param_name] = await self.resolve(dep_func, current_path)
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

    async def teardown_path(self, scope_path: str) -> None:
        """Teardown all fixtures for a given scope path."""
        if scope_path in self._path_exit_stacks:
            await self._path_exit_stacks[scope_path].aclose()
            del self._path_exit_stacks[scope_path]
        if scope_path in self._path_caches:
            del self._path_caches[scope_path]

    async def teardown_suite(self, suite_name: str) -> None:
        """Alias for teardown_path (backward compatibility)."""
        await self.teardown_path(suite_name)

    async def __aenter__(self) -> "Resolver":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        for path in list(self._path_exit_stacks.keys()):
            await self._path_exit_stacks[path].aclose()
        self._path_exit_stacks.clear()
        self._path_caches.clear()
        result = await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
        return result or False

    def _analyze_and_store_dependencies(
        self, func: FixtureCallable, scope_path: str | None
    ) -> None:
        """Analyze function signature and store dependencies."""
        func_signature = signature(func)
        dependencies: dict[str, FixtureCallable] = {}
        for param_name, param in func_signature.parameters.items():
            if dependency := self._extract_dependency_from_parameter(param):
                self._ensure_registered(dependency)
                self._validate_scope(func, scope_path, dependency)
                dependencies[param_name] = dependency
        self._dependencies[func] = dependencies

    def _validate_scope(
        self,
        requester_func: FixtureCallable,
        requester_path: str | None,
        dependency_func: FixtureCallable,
    ) -> None:
        """Validate that dependency has equal or wider scope.

        Rules:
        - Session (None) can only depend on session fixtures
        - Suite can depend on session or parent/same suite fixtures
        - Function can depend on anything
        """
        dep_path = self._scope_paths[dependency_func]

        if dep_path == self.FUNCTION_SCOPE:
            if requester_path != self.FUNCTION_SCOPE:
                raise ScopeMismatchError(
                    get_callable_name(requester_func),
                    self._format_scope(requester_path),
                    get_callable_name(dependency_func),
                    "function",
                )
            return

        if dep_path is None:
            return

        if requester_path is None:
            raise ScopeMismatchError(
                get_callable_name(requester_func),
                "session",
                get_callable_name(dependency_func),
                self._format_scope(dep_path),
            )

        if requester_path == self.FUNCTION_SCOPE:
            return

        if not self._is_parent_or_same_path(dep_path, requester_path):
            raise ScopeMismatchError(
                get_callable_name(requester_func),
                self._format_scope(requester_path),
                get_callable_name(dependency_func),
                self._format_scope(dep_path),
            )

    def _is_parent_or_same_path(self, potential_parent: str, child: str) -> bool:
        """Check if potential_parent is a parent path or same as child.

        "Parent" is parent of "Parent::Child"
        "Parent::Child" is same as "Parent::Child"
        "Other" is NOT parent of "Parent::Child"
        """
        if potential_parent == child:
            return True
        return child.startswith(potential_parent + "::")

    def _format_scope(self, scope_path: str | None) -> str:
        if scope_path is None:
            return "session"
        if scope_path == self.FUNCTION_SCOPE:
            return "function"
        return f"suite '{scope_path}'"

    @staticmethod
    def _extract_dependency_from_parameter(
        param: Parameter,
    ) -> FixtureCallable | None:
        """Extract dependency from Annotated[Type, Use(fixture)] or return None."""
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        return None
