from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from protest.compat import Self
    from protest.core.suite import ProTestSuite
    from protest.entities import FixtureCallable
    from protest.plugin import PluginBase, PluginContext

from protest.cache.plugin import CachePlugin
from protest.cache.storage import CacheStorage
from protest.di.decorators import FixtureWrapper
from protest.di.resolver import Resolver
from protest.di.validation import validate_no_from_params
from protest.entities import (
    FixtureRegistration,
    Retry,
    Skip,
    TestRegistration,
    Xfail,
    normalize_retry,
    normalize_skip,
    normalize_xfail,
)
from protest.events.bus import EventBus
from protest.events.types import Event
from protest.reporting.log_file import LogFilePlugin
from protest.tags.plugin import TagFilterPlugin

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class ProTestSession:
    """Main test session orchestrator.

    Manages test collection, fixture resolution, and plugin coordination.
    Use as async context manager to ensure proper fixture teardown.

    Fixtures registered with @session.fixture() live for the entire session.
    Use @session.autouse() for fixtures that should be resolved at session start.

    Args:
        concurrency: Number of parallel test workers (default: 1).
    """

    def __init__(self, concurrency: int = 1) -> None:
        self._events = EventBus()
        self._resolver = Resolver(event_bus=self._events)
        self._suites: list[ProTestSuite] = []
        self._tests: list[TestRegistration] = []
        self._fixtures: list[FixtureRegistration] = []
        self._concurrency = max(1, concurrency)
        self._autouse_fixtures: list[FixtureCallable] = []
        self._cache_storage = CacheStorage()
        self._plugin_classes: list[type[PluginBase]] = []
        self._exitfirst: bool = False
        self._capture: bool = True
        self._setup_duration: float = 0
        self._teardown_duration: float = 0

    async def resolve_autouse(self) -> None:
        """Resolve all session autouse fixtures at session start."""
        for fixture_func in self._autouse_fixtures:
            await self._resolver.resolve(fixture_func)

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @concurrency.setter
    def concurrency(self, value: int) -> None:
        self._concurrency = max(1, value)

    @property
    def exitfirst(self) -> bool:
        return self._exitfirst

    @exitfirst.setter
    def exitfirst(self, value: bool) -> None:
        self._exitfirst = value

    @property
    def capture(self) -> bool:
        return self._capture

    @capture.setter
    def capture(self, value: bool) -> None:
        self._capture = value

    @property
    def setup_duration(self) -> float:
        """Duration of session setup (available after resolve_autouse)."""
        return self._setup_duration

    def set_setup_duration(self, duration: float) -> None:
        """Set the setup duration. Called by runner after autouse resolution."""
        self._setup_duration = duration

    @property
    def teardown_duration(self) -> float:
        """Duration of session teardown (available after __aexit__)."""
        return self._teardown_duration

    @property
    def resolver(self) -> Resolver:
        return self._resolver

    @property
    def events(self) -> EventBus:
        return self._events

    @property
    def suites(self) -> list[ProTestSuite]:
        return self._suites

    @property
    def tests(self) -> list[TestRegistration]:
        return self._tests

    @property
    def fixtures(self) -> list[FixtureRegistration]:
        return self._fixtures

    @property
    def cache(self) -> CacheStorage:
        """Shared cache storage for inter-plugin data sharing."""
        return self._cache_storage

    def test(
        self,
        tags: list[str] | None = None,
        timeout: float | None = None,
        skip: bool | str | Skip | None = None,
        xfail: bool | str | Xfail | None = None,
        retry: int | Retry | None = None,
    ) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            if timeout is not None and timeout < 0:
                raise ValueError(f"timeout must be non-negative, got {timeout}")

            norm_skip = normalize_skip(skip)
            norm_xfail = normalize_xfail(xfail)
            norm_retry = normalize_retry(retry)

            self._tests.append(
                TestRegistration(
                    func=func,
                    tags=set(tags) if tags else set(),
                    skip=norm_skip,
                    xfail=norm_xfail,
                    timeout=timeout,
                    retry=norm_retry,
                )
            )
            return func

        return decorator

    def fixture(
        self,
        tags: list[str] | None = None,
    ) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
        """Register a fixture scoped to the session (lives entire session)."""

        def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
            validate_no_from_params(func)
            fixture_tags = set(tags) if tags else set()
            registration = FixtureRegistration(
                func=func,
                is_factory=False,
                cache=True,
                managed=True,
                tags=fixture_tags,
            )
            self._fixtures.append(registration)
            return FixtureWrapper(func, registration)

        return decorator

    def autouse(
        self,
        tags: list[str] | None = None,
    ) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
        """Register an autouse fixture scoped to the session.

        Autouse fixtures are resolved at session start before any test runs.
        They can have dependencies on other session fixtures.
        """

        def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
            validate_no_from_params(func)
            fixture_tags = set(tags) if tags else set()
            registration = FixtureRegistration(
                func=func,
                is_factory=False,
                cache=True,
                managed=True,
                tags=fixture_tags,
                autouse=True,
            )
            self._fixtures.append(registration)
            return FixtureWrapper(func, registration)

        return decorator

    def factory(
        self,
        cache: bool = False,
        managed: bool = True,
        tags: list[str] | None = None,
    ) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
        """Register a factory fixture scoped to the session."""

        def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
            validate_no_from_params(func)
            fixture_tags = set(tags) if tags else set()
            registration = FixtureRegistration(
                func=func,
                is_factory=True,
                cache=cache,
                managed=managed,
                tags=fixture_tags,
            )
            self._fixtures.append(registration)
            return FixtureWrapper(func, registration)

        return decorator

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a suite to this session."""
        suite._attach_to_session(self)
        self._suites.append(suite)

    def include_suite(self, suite: ProTestSuite) -> None:
        """Alias for add_suite (backward compatibility)."""
        self.add_suite(suite)

    def use(self, plugin_class: type[PluginBase]) -> None:
        """Register a plugin class for CLI discovery.

        The plugin will be instantiated via from_cli() after CLI parsing.
        """
        self._plugin_classes.append(plugin_class)

    def register_default_plugins(self) -> None:
        """Register all standard ProTest plugins for CLI discovery.

        This includes: RichReporter, AsciiReporter, CachePlugin, LogFilePlugin,
        TagFilterPlugin, SuiteFilterPlugin, KeywordFilterPlugin.
        """
        from protest.filters.keyword import KeywordFilterPlugin as KFP
        from protest.filters.suite import SuiteFilterPlugin as SFP
        from protest.reporting.ascii import AsciiReporter
        from protest.reporting.rich_reporter import RichReporter

        self.use(RichReporter)
        self.use(AsciiReporter)
        self.use(CachePlugin)
        self.use(LogFilePlugin)
        self.use(TagFilterPlugin)
        self.use(SFP)
        self.use(KFP)

    @property
    def plugin_classes(self) -> list[type[PluginBase]]:
        """Get registered plugin classes."""
        return self._plugin_classes.copy()

    def register_plugin(self, plugin: PluginBase) -> None:
        """Register a plugin instance and wire it to the event bus.

        Use this to register a pre-configured plugin instance. For CLI usage,
        prefer `use(PluginClass)` which enables CLI option discovery.
        """
        if hasattr(plugin, "setup") and callable(plugin.setup):
            plugin.setup(self)

        for event in Event:
            method_name = f"on_{event.value}"
            handler = getattr(plugin, method_name, None)
            if handler and callable(handler):
                self._events.on(event, handler)

    def activate_plugins(self, ctx: PluginContext) -> None:
        """Activate all registered plugin classes with the given context.

        Each plugin's activate() method is called with the context.
        If it returns an instance, that instance is registered.
        If it returns None, the plugin is skipped.
        """
        for plugin_class in self._plugin_classes:
            instance = plugin_class.activate(ctx)
            if instance is not None:
                self.register_plugin(instance)

    async def __aenter__(self) -> Self:
        self._register_fixtures()
        await self._resolver.__aenter__()
        return self

    def _register_fixtures(self) -> None:
        """Register all fixtures from session and suites into resolver."""
        self._autouse_fixtures.clear()
        for reg in self._fixtures:
            self._resolver.register(
                reg.func,
                scope_path=None,
                is_factory=reg.is_factory,
                cache=reg.cache,
                managed=reg.managed,
                tags=reg.tags,
                autouse=reg.autouse,
            )
            if reg.autouse:
                self._autouse_fixtures.append(reg.func)
        self._register_suite_fixtures(self._suites)

    def _register_suite_fixtures(self, suites: list[ProTestSuite]) -> None:
        """Recursively register fixtures from suites."""
        for suite in suites:
            for reg in suite.fixtures:
                self._resolver.register(
                    reg.func,
                    scope_path=suite.full_path,
                    is_factory=reg.is_factory,
                    cache=reg.cache,
                    managed=reg.managed,
                    tags=reg.tags,
                    autouse=reg.autouse,
                )
            self._register_suite_fixtures(suite.suites)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        import time

        from protest.execution.capture import set_session_teardown_capture

        teardown_start = time.perf_counter()
        set_session_teardown_capture(True)
        try:
            return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            set_session_teardown_capture(False)
            self._teardown_duration = time.perf_counter() - teardown_start
