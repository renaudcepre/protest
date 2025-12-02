from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from protest.compat import Self
    from protest.core.fixture import FixtureCallable
    from protest.core.suite import ProTestSuite
    from protest.plugin import PluginBase

from protest.cache.plugin import CachePlugin
from protest.di.resolver import Resolver
from protest.events.bus import EventBus
from protest.events.types import Event

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


def _get_default_reporter() -> PluginBase:
    """Get the best available reporter (Rich if installed, else Ascii)."""
    try:
        from protest.reporting.rich_reporter import RichReporter

        return RichReporter()
    except ImportError:
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()


class ProTestSession:
    """Main test session orchestrator.

    Manages test collection, fixture resolution, and plugin coordination.
    Use as async context manager to ensure proper fixture teardown.

    Fixtures registered with @session.fixture() live for the entire session.

    Args:
        concurrency: Number of parallel test workers (default: 1).
        autouse: Fixtures to auto-resolve at session start before any test runs.
        default_reporter: If True (default), adds RichReporter (or AsciiReporter fallback).
        default_cache: If True (default), adds CachePlugin for --lf support.
    """

    def __init__(
        self,
        concurrency: int = 1,
        autouse: list[FixtureCallable] | None = None,
        default_reporter: bool = True,
        default_cache: bool = True,
    ) -> None:
        self._events = EventBus()
        self._resolver = Resolver(event_bus=self._events)
        self._suites: list[ProTestSuite] = []
        self._tests: list[Callable[..., Any]] = []
        self._fixtures: list[tuple[FixtureCallable, bool]] = []
        self._concurrency = max(1, concurrency)
        self._autouse = autouse or []
        self._cache_plugin: CachePlugin | None = None

        if default_reporter:
            self.use(_get_default_reporter())
        if default_cache:
            self._cache_plugin = CachePlugin()
            self.use(self._cache_plugin)

    @property
    def autouse(self) -> list[FixtureCallable]:
        return self._autouse

    async def resolve_autouse(self) -> None:
        """Resolve all autouse fixtures at session start."""
        for fixture_func in self._autouse:
            await self._resolver.resolve(fixture_func)

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @concurrency.setter
    def concurrency(self, value: int) -> None:
        self._concurrency = max(1, value)

    def configure_cache(
        self, last_failed: bool = False, cache_clear: bool = False
    ) -> None:
        """Configure the cache plugin (--lf, --cache-clear)."""
        if self._cache_plugin is not None:
            self._cache_plugin._last_failed = last_failed
            self._cache_plugin._cache_clear = cache_clear

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
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    @property
    def fixtures(self) -> list[tuple[FixtureCallable, bool]]:
        return self._fixtures

    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def fixture(self, factory: bool = False) -> Callable[[FuncT], FuncT]:
        """Register a fixture scoped to the session (lives entire session)."""

        def decorator(func: FuncT) -> FuncT:
            self._fixtures.append((func, factory))
            return func

        return decorator

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a suite to this session."""
        suite._attach_to_session(self)
        self._suites.append(suite)

    def include_suite(self, suite: ProTestSuite) -> None:
        """Alias for add_suite (backward compatibility)."""
        self.add_suite(suite)

    def use(self, plugin: PluginBase) -> None:
        """Enregistre un plugin avec wiring automatique des hooks."""
        if hasattr(plugin, "setup") and callable(plugin.setup):
            plugin.setup(self)

        for event in Event:
            method_name = f"on_{event.value}"
            handler = getattr(plugin, method_name, None)
            if handler and callable(handler):
                self._events.on(event, handler)

    async def __aenter__(self) -> Self:
        self._register_fixtures()
        await self._resolver.__aenter__()
        return self

    def _register_fixtures(self) -> None:
        """Register all fixtures from session and suites into resolver."""
        for func, is_factory in self._fixtures:
            self._resolver.register(func, scope_path=None, is_factory=is_factory)
        self._register_suite_fixtures(self._suites)

    def _register_suite_fixtures(self, suites: list[ProTestSuite]) -> None:
        """Recursively register fixtures from suites."""
        for suite in suites:
            for func, is_factory in suite.fixtures:
                self._resolver.register(
                    func, scope_path=suite.full_path, is_factory=is_factory
                )
            self._register_suite_fixtures(suite.suites)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
