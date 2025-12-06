from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from protest.compat import Self
    from protest.core.suite import ProTestSuite
    from protest.entities import FixtureCallable
    from protest.plugin import PluginBase

from protest.cache.plugin import CachePlugin
from protest.cache.storage import CacheStorage
from protest.core.collector import validate_no_from_params
from protest.di.decorators import FixtureWrapper
from protest.di.resolver import Resolver
from protest.entities import FixtureRegistration, TestRegistration
from protest.events.bus import EventBus
from protest.events.types import Event
from protest.filters import KeywordFilterPlugin, SuiteFilterPlugin
from protest.tags.plugin import TagFilterPlugin
from protest.utils import normalize_reason

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
        include_tags: set[str] | None = None,
        exclude_tags: set[str] | None = None,
    ) -> None:
        self._events = EventBus()
        self._resolver = Resolver(event_bus=self._events)
        self._suites: list[ProTestSuite] = []
        self._tests: list[TestRegistration] = []
        self._fixtures: list[FixtureRegistration] = []
        self._concurrency = max(1, concurrency)
        self._autouse = autouse or []
        self._cache_storage = CacheStorage()
        self._cache_plugin: CachePlugin | None = None
        self._cache_plugin_registered: bool = False
        self._tag_filter_plugin: TagFilterPlugin | None = None
        self._suite_filter_plugin: SuiteFilterPlugin | None = None
        self._keyword_filter_plugin: KeywordFilterPlugin | None = None
        self._exitfirst: bool = False
        self._capture: bool = True

        if default_reporter:
            self.use(_get_default_reporter())
        if default_cache:
            self._cache_plugin = CachePlugin()
        if include_tags or exclude_tags:
            self._tag_filter_plugin = TagFilterPlugin(include_tags, exclude_tags)
            self.use(self._tag_filter_plugin)

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

    def configure_cache(
        self, last_failed: bool = False, cache_clear: bool = False
    ) -> None:
        """Configure the cache plugin (--lf, --cache-clear)."""
        if self._cache_plugin is not None:
            self._cache_plugin._last_failed = last_failed
            self._cache_plugin._cache_clear = cache_clear
            if not self._cache_plugin_registered:
                self.use(self._cache_plugin)
                self._cache_plugin_registered = True

    def configure_tags(
        self,
        include_tags: set[str] | None = None,
        exclude_tags: set[str] | None = None,
    ) -> None:
        """Configure tag filtering (-t/--tag, --no-tag)."""
        if not include_tags and not exclude_tags:
            return
        if self._tag_filter_plugin is None:
            self._tag_filter_plugin = TagFilterPlugin(include_tags, exclude_tags)
            self.use(self._tag_filter_plugin)
        else:
            self._tag_filter_plugin._include_tags = include_tags or set()
            self._tag_filter_plugin._exclude_tags = exclude_tags or set()

    def configure_suite_filter(self, suite_filter: str | None = None) -> None:
        """Configure suite filtering (::SuiteName target syntax)."""
        if not suite_filter:
            return
        if self._suite_filter_plugin is None:
            self._suite_filter_plugin = SuiteFilterPlugin(suite_filter)
            self.use(self._suite_filter_plugin)
        else:
            self._suite_filter_plugin._suite_filter = suite_filter

    def configure_keyword_filter(self, patterns: list[str] | None = None) -> None:
        """Configure keyword filtering (-k patterns)."""
        if not patterns:
            return
        if self._keyword_filter_plugin is None:
            self._keyword_filter_plugin = KeywordFilterPlugin(patterns)
            self.use(self._keyword_filter_plugin)
        else:
            self._keyword_filter_plugin._patterns = patterns

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
        skip: bool | str = False,
        xfail: bool | str = False,
    ) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            self._tests.append(
                TestRegistration(
                    func=func,
                    tags=set(tags) if tags else set(),
                    skip_reason=normalize_reason(skip, "Skipped"),
                    xfail_reason=normalize_reason(xfail, "Expected failure"),
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

    def factory(
        self,
        cache: bool = True,
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
        for reg in self._fixtures:
            self._resolver.register(
                reg.func,
                scope_path=None,
                is_factory=reg.is_factory,
                cache=reg.cache,
                managed=reg.managed,
                tags=reg.tags,
            )
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
                )
            self._register_suite_fixtures(suite.suites)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
