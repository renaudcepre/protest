from __future__ import annotations

import asyncio
import inspect
import time
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager, suppress
from inspect import signature
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    get_args,
    get_origin,
    get_type_hints,
    overload,
)

from protest.core.fixture import is_generator_like
from protest.di.decorators import (
    FIXTURE_MARKER_ATTR,
    FixtureWrapper,
    get_fixture_marker,
    unwrap_fixture,
)
from protest.di.factory import FixtureFactory
from protest.di.markers import Use
from protest.di.proxy import SafeProxy
from protest.entities import (
    Fixture,
    FixtureCallable,
    FixtureInfo,
    FixtureScope,
    SuitePath,
    format_fixture_scope,
)
from protest.events.types import Event
from protest.exceptions import (
    AlreadyRegisteredError,
    CircularDependencyError,
    PlainFunctionError,
    ScopeMismatchError,
)
from protest.execution.async_bridge import ensure_async
from protest.execution.context import cancellation_event
from protest.utils import get_callable_name

if TYPE_CHECKING:
    from types import TracebackType

    from protest.compat import Self
    from protest.events.bus import EventBus


class FixtureContainer:
    """Manages fixture registration, dependency analysis, and resolution.

    Scope is determined by the FixtureScope enum:
    - SESSION: Lives entire session (global cache)
    - SUITE: Lives while suite runs (cached per current_path at resolution time)
    - TEST: Fresh instance per test

    For SUITE scope, fixtures are cached per the calling suite's path (current_path),
    not per a specific suite they're declared on. This enables the Mark & Collect
    pattern where fixtures are decorated standalone without coupling to a suite instance.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._registry: dict[FixtureCallable, Fixture] = {}
        self._dependencies: dict[FixtureCallable, dict[str, FixtureCallable]] = {}
        self._scopes: dict[FixtureCallable, FixtureScope] = {}
        self._suite_paths: dict[
            FixtureCallable, SuitePath
        ] = {}  # Owner suite path for SUITE fixtures
        self._exit_stack: AsyncExitStack = AsyncExitStack()
        self._resolve_locks: dict[FixtureCallable, asyncio.Lock] = {}
        # For SUITE scope: cache and exit stacks keyed by owner suite path
        self._suite_caches: dict[SuitePath, dict[FixtureCallable, Any]] = {}
        self._suite_exit_stacks: dict[SuitePath, AsyncExitStack] = {}
        self._event_bus = event_bus
        self._autouse_fixtures: set[FixtureCallable] = set()

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    def register(  # noqa: PLR0913
        self,
        func: FixtureCallable,
        scope: FixtureScope = FixtureScope.TEST,
        is_factory: bool = False,
        cache: bool = True,
        managed: bool = True,
        tags: set[str] | None = None,
        autouse: bool = False,
        suite_path: SuitePath | None = None,
    ) -> None:
        """Register a fixture with a specific scope.

        Args:
            func: The fixture function.
            scope: Lifecycle scope for this fixture:
                - SESSION: Global cache, lives entire session
                - SUITE: Cached per suite, requires suite_path
                - TEST: Fresh instance per test (default)
            is_factory: Whether this fixture returns a FixtureFactory callable.
            cache: Whether to cache factory instances by kwargs (only for factories).
            managed: If True (default), factory fixtures are wrapped in FixtureFactory.
                     If False, the fixture returns its own callable (legacy/class pattern).
            tags: Tags for this fixture (propagated to tests using it).
            autouse: Whether this fixture should be auto-resolved at scope start.
            suite_path: For SUITE scope, the path of the suite that owns this fixture.
                       Tests in this suite or child suites can access the fixture.
        """
        if func in self._registry:
            raise AlreadyRegisteredError(get_callable_name(func))

        fixture = Fixture(
            func,
            is_factory=is_factory,
            cache=cache,
            managed=managed,
            tags=tags or set(),
        )
        self._scopes[func] = scope
        if scope == FixtureScope.SUITE and suite_path is not None:
            self._suite_paths[func] = suite_path
        self._analyze_and_store_dependencies(func, scope)
        self._registry[func] = fixture
        self._resolve_locks[func] = asyncio.Lock()

        if autouse:
            self._autouse_fixtures.add(func)

    def has_fixture(self, func: FixtureCallable) -> bool:
        """Check if a fixture is registered."""
        actual_func = unwrap_fixture(func)
        return actual_func in self._registry

    def get_fixture(self, func: FixtureCallable) -> Fixture | None:
        """Return the Fixture for a function, or None if not registered."""
        actual_func = unwrap_fixture(func)
        return self._registry.get(actual_func)

    def get_scope(self, func: FixtureCallable) -> FixtureScope | None:
        """Return the scope for a fixture, or None if not registered."""
        actual_func = unwrap_fixture(func)
        return self._scopes.get(actual_func)

    def get_suite_path(self, func: FixtureCallable) -> SuitePath | None:
        """Return the owner suite path for a SUITE-scoped fixture."""
        actual_func = unwrap_fixture(func)
        return self._suite_paths.get(actual_func)

    def get_dependencies(self, func: FixtureCallable) -> dict[str, FixtureCallable]:
        """Return the dependencies of a fixture as {param_name: fixture_func}."""
        actual_func = unwrap_fixture(func)
        return self._dependencies.get(actual_func, {})

    def get_fixture_tags(self, func: FixtureCallable) -> set[str]:
        """Get tags declared on a fixture."""
        actual_func = unwrap_fixture(func)
        fixture = self._registry.get(actual_func)
        return fixture.tags.copy() if fixture else set()

    def get_transitive_tags(self, func: FixtureCallable) -> set[str]:
        """Get all tags from a fixture and its dependencies (transitive)."""
        actual_func = unwrap_fixture(func)
        return self._collect_transitive_tags(actual_func, set())

    def _collect_transitive_tags(
        self, func: FixtureCallable, visited: set[FixtureCallable]
    ) -> set[str]:
        """Recursively collect tags from fixture and all its dependencies."""
        actual_func = unwrap_fixture(func)
        if actual_func in visited:
            return set()
        visited.add(actual_func)

        tags: set[str] = set()
        fixture = self._registry.get(actual_func)
        if fixture:
            tags.update(fixture.tags)

        for dep_func in self._dependencies.get(actual_func, {}).values():
            tags.update(self._collect_transitive_tags(dep_func, visited))

        return tags

    @overload
    def _ensure_registered(self, func: FixtureWrapper[FixtureCallable]) -> Fixture: ...
    @overload
    def _ensure_registered(self, func: FixtureCallable) -> Fixture: ...

    def _ensure_registered(
        self, func: FixtureCallable | FixtureWrapper[FixtureCallable]
    ) -> Fixture:
        """Ensure a fixture is registered and return it.

        In the "Scope at Binding" pattern:
        - Fixtures bound via session.bind()/suite.bind() are pre-registered
        - Unbound fixtures with @fixture()/@factory() decorator → TEST scope (default)
        - Plain functions without decorator → PlainFunctionError

        Accepts:
        - FixtureWrapper: auto-registers as TEST scope if not already registered
        - Pre-registered functions: returns from registry
        - Unregistered plain functions: raises PlainFunctionError
        """
        if isinstance(func, FixtureWrapper):
            actual_func: FixtureCallable = func.func

            if actual_func not in self._registry:
                # Unbound fixture → TEST scope by default
                marker = get_fixture_marker(func)
                if marker:
                    self.register(
                        actual_func,
                        scope=FixtureScope.TEST,  # Default for unbound fixtures
                        is_factory=marker.is_factory,
                        cache=marker.cache,
                        managed=marker.managed,
                        tags=set(marker.tags),
                        autouse=False,  # TEST scope can't have autouse at session/suite level
                    )
                else:
                    # Legacy: use FixtureRegistration
                    reg = func.registration
                    self.register(
                        actual_func,
                        scope=FixtureScope.TEST,
                        is_factory=reg.is_factory,
                        cache=reg.cache,
                        managed=reg.managed,
                        tags=reg.tags,
                        autouse=False,
                    )
            return self._registry[actual_func]

        # Check for marker on plain function (decorated but not wrapped)
        if hasattr(func, FIXTURE_MARKER_ATTR):
            marker = get_fixture_marker(func)
            if marker and func not in self._registry:
                # Unbound fixture → TEST scope by default
                self.register(
                    func,
                    scope=FixtureScope.TEST,
                    is_factory=marker.is_factory,
                    cache=marker.cache,
                    managed=marker.managed,
                    tags=set(marker.tags),
                    autouse=False,
                )
            if func in self._registry:
                return self._registry[func]

        if func in self._registry:
            return self._registry[func]

        raise PlainFunctionError(get_callable_name(func))

    async def resolve(
        self,
        target_func: FixtureCallable,
        current_path: SuitePath | None = None,
        dependency_chain: tuple[FixtureCallable, ...] = (),
        context_cache: dict[FixtureCallable, Any] | None = None,
        context_exit_stack: AsyncExitStack | None = None,
    ) -> Any:
        """Resolve a fixture recursively.

        Args:
            target_func: The fixture function (must be decorated with @fixture/@factory).
            current_path: Current execution context path (suite path for tests).
                For SUITE-scoped fixtures, this determines the cache key.
            dependency_chain: Stack tracking fixtures being resolved (for cycle detection).
            context_cache: External cache for TEST-scoped fixtures (injected by TestExecutionContext).
            context_exit_stack: External exit stack for TEST-scoped fixtures teardown.

        Returns:
            The resolved fixture value.
        """
        target_fixture = self._ensure_registered(target_func)
        actual_func = target_fixture.func

        if actual_func in dependency_chain:
            cycle_path = [get_callable_name(func) for func in dependency_chain]
            cycle_path.append(get_callable_name(actual_func))
            raise CircularDependencyError(cycle_path)

        scope = self._scopes[actual_func]
        new_chain = (*dependency_chain, actual_func)

        match scope:
            case FixtureScope.SESSION:
                return await self._resolve_session_scoped(
                    target_fixture,
                    current_path,
                    new_chain,
                    context_cache,
                    context_exit_stack,
                )
            case FixtureScope.SUITE:
                return await self._resolve_suite_scoped(
                    target_fixture,
                    current_path,
                    new_chain,
                    context_cache,
                    context_exit_stack,
                )
            case FixtureScope.TEST:
                return await self._resolve_test_scoped(
                    target_fixture,
                    current_path,
                    new_chain,
                    context_cache,
                    context_exit_stack,
                )

    async def _resolve_session_scoped(
        self,
        target_fixture: Fixture,
        current_path: SuitePath | None,
        dependency_chain: tuple[FixtureCallable, ...],
        context_cache: dict[FixtureCallable, Any] | None,
        context_exit_stack: AsyncExitStack | None,
    ) -> Any:
        """Resolve a session-scoped fixture with global caching."""
        if target_fixture.is_cached:
            return target_fixture.cached_value

        async with self._resolve_locks[target_fixture.func]:
            if target_fixture.is_cached:
                return target_fixture.cached_value

            kwargs = await self._resolve_dependencies(
                target_fixture.func,
                current_path,
                dependency_chain,
                context_cache,
                context_exit_stack,
            )
            result = await self._resolve_fixture_value(
                target_fixture, kwargs, self._exit_stack
            )

            target_fixture.cached_value = result
            target_fixture.is_cached = True
            return result

    async def _resolve_suite_scoped(
        self,
        target_fixture: Fixture,
        current_path: SuitePath | None,
        dependency_chain: tuple[FixtureCallable, ...],
        context_cache: dict[FixtureCallable, Any] | None,
        context_exit_stack: AsyncExitStack | None,
    ) -> Any:
        """Resolve a suite-scoped fixture with per-owner-suite caching.

        The cache key is the fixture's owner suite path (from registration),
        NOT the current test's suite path. This means:
        - A fixture bound to suite "A::B" is cached once for "A::B"
        - Tests in "A::B", "A::B::C", "A::B::D" all share the same instance
        """
        # Use fixture's owner suite path as cache key
        # Fallback to current_path for backward compat, then empty path
        owner_path = self._suite_paths.get(target_fixture.func)
        cache_key = owner_path or current_path or SuitePath("")

        if cache_key not in self._suite_caches:
            self._suite_caches[cache_key] = {}

        cache = self._suite_caches[cache_key]
        if target_fixture.func in cache:
            return cache[target_fixture.func]

        async with self._resolve_locks[target_fixture.func]:
            if target_fixture.func in cache:
                return cache[target_fixture.func]

            if cache_key not in self._suite_exit_stacks:
                self._suite_exit_stacks[cache_key] = AsyncExitStack()

            kwargs = await self._resolve_dependencies(
                target_fixture.func,
                current_path,
                dependency_chain,
                context_cache,
                context_exit_stack,
            )
            result = await self._resolve_fixture_value(
                target_fixture, kwargs, self._suite_exit_stacks[cache_key]
            )

            cache[target_fixture.func] = result
            return result

    async def _resolve_test_scoped(
        self,
        target_fixture: Fixture,
        current_path: SuitePath | None,
        dependency_chain: tuple[FixtureCallable, ...],
        context_cache: dict[FixtureCallable, Any] | None,
        context_exit_stack: AsyncExitStack | None,
    ) -> Any:
        """Resolve a test-scoped fixture using injected context resources.

        When context_cache and context_exit_stack are provided (by TestExecutionContext),
        uses them for caching and teardown. Otherwise falls back to creating a local
        exit stack (for direct resolve calls outside test context).
        """
        actual_func = target_fixture.func

        if context_cache is not None and actual_func in context_cache:
            return context_cache[actual_func]

        kwargs = await self._resolve_dependencies(
            actual_func,
            current_path,
            dependency_chain,
            context_cache,
            context_exit_stack,
        )

        exit_stack = (
            context_exit_stack if context_exit_stack is not None else AsyncExitStack()
        )
        result = await self._resolve_fixture_value(target_fixture, kwargs, exit_stack)

        if context_cache is not None:
            context_cache[actual_func] = result

        return result

    async def _resolve_fixture_value(
        self,
        fixture: Fixture,
        kwargs: dict[str, Any],
        exit_stack: AsyncExitStack,
    ) -> Any:
        """Resolve a fixture value based on its type (factory/managed/regular)."""
        fixture_name = get_callable_name(fixture.func)

        if fixture.is_factory and fixture.managed:
            return self._create_fixture_factory(fixture, kwargs, exit_stack)

        if fixture.is_factory and not fixture.managed:
            result = await self._execute_fixture(fixture, kwargs, exit_stack)
            return SafeProxy(result, fixture_name)

        return await self._execute_fixture(fixture, kwargs, exit_stack)

    async def _resolve_dependencies(
        self,
        target_func: FixtureCallable,
        current_path: SuitePath | None,
        dependency_chain: tuple[FixtureCallable, ...],
        context_cache: dict[FixtureCallable, Any] | None,
        context_exit_stack: AsyncExitStack | None,
    ) -> dict[str, Any]:
        """Resolve all dependencies for a fixture."""
        kwargs: dict[str, Any] = {}
        for param_name, dep_func in self._dependencies.get(target_func, {}).items():
            kwargs[param_name] = await self.resolve(
                dep_func,
                current_path,
                dependency_chain,
                context_cache,
                context_exit_stack,
            )
        return kwargs

    def _create_fixture_factory(
        self,
        fixture: Fixture,
        resolved_dependencies: dict[str, Any],
        exit_stack: AsyncExitStack,
    ) -> FixtureFactory[Any]:
        """Create a FixtureFactory wrapper for a factory fixture."""
        fixture_name = get_callable_name(fixture.func)
        return FixtureFactory(
            fixture=fixture,
            fixture_name=fixture_name,
            resolved_dependencies=resolved_dependencies,
            exit_stack=exit_stack,
            cache_enabled=fixture.cache,
        )

    async def _execute_fixture(
        self, fixture: Fixture, kwargs: dict[str, Any], exit_stack: AsyncExitStack
    ) -> Any:
        """Execute fixture function, handling generators for setup/teardown."""
        fixture_name = get_callable_name(fixture.func)
        scope = self._scopes.get(fixture.func, FixtureScope.TEST)
        scope_path = self._suite_paths.get(fixture.func)
        is_autouse = fixture.func in self._autouse_fixtures

        lifetime_start = time.perf_counter()
        setup_start = time.perf_counter()
        await self._emit_fixture_setup_start_async(
            fixture_name, scope, scope_path, is_autouse
        )

        if is_generator_like(fixture.func):
            # Push emit_done FIRST (runs LAST due to LIFO)
            exit_stack.push_async_callback(
                self._emit_fixture_teardown_done_async,
                fixture_name,
                scope,
                scope_path,
                lifetime_start,
                is_autouse,
            )

            # Enter the context manager (runs in the middle)
            if inspect.isasyncgenfunction(fixture.func):
                async_cm = asynccontextmanager(fixture.func)(**kwargs)
                result = await exit_stack.enter_async_context(async_cm)
            else:
                sync_cm = contextmanager(fixture.func)(**kwargs)
                result = exit_stack.enter_context(sync_cm)

            # Push emit_start LAST (runs FIRST due to LIFO)
            exit_stack.push_async_callback(
                self._emit_fixture_teardown_start_async,
                fixture_name,
                scope,
                scope_path,
                is_autouse,
            )
        else:
            result = await ensure_async(fixture.func, **kwargs)

        # Emit setup done after fixture setup completes
        setup_duration = time.perf_counter() - setup_start
        await self._emit_fixture_setup_done_async(
            fixture_name, scope, scope_path, setup_duration, is_autouse
        )

        return result

    async def _emit_fixture_setup_start_async(
        self,
        name: str,
        scope: FixtureScope,
        scope_path: SuitePath | None,
        autouse: bool,
    ) -> None:
        if self._event_bus is None:
            return

        await self._event_bus.emit(
            Event.FIXTURE_SETUP_START,
            FixtureInfo(name=name, scope=scope, scope_path=scope_path, autouse=autouse),
        )

    async def _emit_fixture_setup_done_async(
        self,
        name: str,
        scope: FixtureScope,
        scope_path: SuitePath | None,
        duration: float,
        autouse: bool,
    ) -> None:
        if self._event_bus is None:
            return

        await self._event_bus.emit(
            Event.FIXTURE_SETUP_DONE,
            FixtureInfo(
                name=name,
                scope=scope,
                scope_path=scope_path,
                duration=duration,
                autouse=autouse,
            ),
        )

    async def _emit_fixture_teardown_start_async(
        self,
        name: str,
        scope: FixtureScope,
        scope_path: SuitePath | None,
        autouse: bool,
    ) -> None:
        if self._event_bus is None:
            return

        await self._event_bus.emit(
            Event.FIXTURE_TEARDOWN_START,
            FixtureInfo(name=name, scope=scope, scope_path=scope_path, autouse=autouse),
        )

    async def _emit_fixture_teardown_done_async(
        self,
        name: str,
        scope: FixtureScope,
        scope_path: SuitePath | None,
        start_time: float,
        autouse: bool,
    ) -> None:
        if self._event_bus is None:
            return

        duration = time.perf_counter() - start_time
        await self._event_bus.emit(
            Event.FIXTURE_TEARDOWN_DONE,
            FixtureInfo(
                name=name,
                scope=scope,
                scope_path=scope_path,
                duration=duration,
                autouse=autouse,
            ),
        )

    async def resolve_suite_autouse(self, suite_path: SuitePath) -> None:
        """Resolve SUITE-scoped autouse fixtures accessible from this suite.

        Only resolves fixtures that are owned by this suite or an ancestor suite.
        A fixture owned by "A::B" is accessible from "A::B", "A::B::C", etc.
        """
        for fixture_func in self._autouse_fixtures:
            if self._scopes.get(fixture_func) != FixtureScope.SUITE:
                continue
            owner_path = self._suite_paths.get(fixture_func)
            if owner_path is None:
                continue
            # Resolve if owner is this suite or an ancestor of this suite
            if owner_path.is_ancestor_of(suite_path):
                await self.resolve(fixture_func, current_path=suite_path)

    async def resolve_session_autouse(self) -> None:
        """Resolve all SESSION-scoped autouse fixtures."""
        for fixture_func in self._autouse_fixtures:
            if self._scopes.get(fixture_func) == FixtureScope.SESSION:
                await self.resolve(fixture_func, current_path=None)

    async def resolve_test_autouse(
        self,
        current_path: SuitePath | None,
        context_cache: dict[FixtureCallable, Any],
        context_exit_stack: AsyncExitStack,
    ) -> None:
        """Resolve all TEST-scoped autouse fixtures for the current test.

        TEST-scoped autouse fixtures are resolved once per test, using the
        test's context cache and exit stack for proper lifecycle management.

        Args:
            current_path: Suite path for the test (for dependency resolution).
            context_cache: Test's fixture cache (from TestExecutionContext).
            context_exit_stack: Test's exit stack (for teardown).
        """
        for fixture_func in self._autouse_fixtures:
            if self._scopes.get(fixture_func) == FixtureScope.TEST:
                await self.resolve(
                    fixture_func,
                    current_path=current_path,
                    context_cache=context_cache,
                    context_exit_stack=context_exit_stack,
                )

    def is_autouse(self, func: FixtureCallable) -> bool:
        """Check if a fixture is marked as autouse."""
        actual_func = unwrap_fixture(func)
        return actual_func in self._autouse_fixtures

    async def teardown_path(self, scope_path: SuitePath) -> None:
        """Teardown all fixtures for a given scope path."""
        if scope_path in self._suite_exit_stacks:
            await self._suite_exit_stacks[scope_path].aclose()
            del self._suite_exit_stacks[scope_path]
        if scope_path in self._suite_caches:
            del self._suite_caches[scope_path]

    async def teardown_suite(self, suite_path: SuitePath) -> None:
        """Teardown all fixtures for a suite path."""
        await self.teardown_path(suite_path)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        interrupt_event = cancellation_event.get()

        for path in reversed(list(self._suite_exit_stacks.keys())):
            if await self._run_teardown_interruptible(
                self._suite_exit_stacks[path], interrupt_event
            ):
                # Cancelled - abort remaining teardowns
                self._suite_exit_stacks.clear()
                self._suite_caches.clear()
                return False

        self._suite_exit_stacks.clear()
        self._suite_caches.clear()

        if await self._run_teardown_interruptible(
            self._exit_stack, interrupt_event, exc_type, exc_val, exc_tb
        ):
            return False

        return False

    async def _run_teardown_interruptible(
        self,
        exit_stack: AsyncExitStack,
        interrupt_event: asyncio.Event | None,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> bool:
        """Run exit stack teardown, interruptible by cancellation event.

        Returns True if cancelled (should abort), False if completed normally.
        Teardown runs in a thread pool so sync blocking code doesn't freeze
        the event loop, allowing us to detect and respond to cancellation.
        """
        if interrupt_event is None:
            await exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            return False

        if interrupt_event.is_set():
            return True

        # Run teardown in thread pool so sync code doesn't block event loop
        loop = asyncio.get_running_loop()

        def run_sync_teardown() -> None:
            # Create a new event loop for the thread to run async teardowns
            new_loop = asyncio.new_event_loop()
            try:
                new_loop.run_until_complete(
                    exit_stack.__aexit__(exc_type, exc_val, exc_tb)
                )
            finally:
                new_loop.close()

        async def run_in_thread() -> None:
            await loop.run_in_executor(None, run_sync_teardown)

        teardown_task = asyncio.create_task(run_in_thread())
        wait_cancel = asyncio.create_task(interrupt_event.wait())

        done, _ = await asyncio.wait(
            {teardown_task, wait_cancel},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if wait_cancel in done:
            # Cancellation requested - abandon the teardown
            # The thread continues but we stop waiting
            return True

        # Teardown completed normally
        wait_cancel.cancel()
        with suppress(asyncio.CancelledError):
            await wait_cancel
        return False

    def _analyze_and_store_dependencies(
        self, func: FixtureCallable, scope: FixtureScope
    ) -> None:
        """Analyze function signature and store dependencies."""
        actual_func = unwrap_fixture(func)
        func_signature = signature(actual_func)

        try:
            type_hints = get_type_hints(actual_func, include_extras=True)
        except Exception:
            type_hints = {}

        dependencies: dict[str, FixtureCallable] = {}
        for param_name, param in func_signature.parameters.items():
            resolved_annotation = type_hints.get(param_name, param.annotation)
            if dependency := self._extract_dependency_from_annotation(
                resolved_annotation
            ):
                dep_func = unwrap_fixture(dependency)
                self._ensure_registered(dependency)
                self._validate_scope(func, scope, dep_func)
                dependencies[param_name] = dep_func
        self._dependencies[func] = dependencies

    def _validate_scope(
        self,
        requester_func: FixtureCallable,
        requester_scope: FixtureScope,
        dependency_func: FixtureCallable,
    ) -> None:
        """Validate that dependency has equal or wider scope.

        Scope hierarchy (wider to narrower): SESSION > SUITE > TEST

        Rules:
        - SESSION fixtures can only depend on SESSION fixtures
        - SUITE fixtures can depend on SESSION or SUITE fixtures
        - TEST fixtures can depend on anything
        """
        dep_scope = self._scopes[dependency_func]

        # TEST scope can depend on anything
        if requester_scope == FixtureScope.TEST:
            return

        # SUITE scope can depend on SESSION or SUITE
        if requester_scope == FixtureScope.SUITE:
            if dep_scope == FixtureScope.TEST:
                raise ScopeMismatchError(
                    get_callable_name(requester_func),
                    format_fixture_scope(requester_scope),
                    get_callable_name(dependency_func),
                    format_fixture_scope(dep_scope),
                )
            return

        # SESSION scope can only depend on SESSION
        if (
            requester_scope == FixtureScope.SESSION
            and dep_scope != FixtureScope.SESSION
        ):
            raise ScopeMismatchError(
                get_callable_name(requester_func),
                format_fixture_scope(requester_scope),
                get_callable_name(dependency_func),
                format_fixture_scope(dep_scope),
            )

    @staticmethod
    def _extract_dependency_from_annotation(
        annotation: Any,
    ) -> FixtureCallable | None:
        """Extract dependency from a resolved Annotated[Type, Use(fixture)] or return None."""
        if get_origin(annotation) is Annotated:
            for metadata in get_args(annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        return None
