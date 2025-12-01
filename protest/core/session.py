from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from protest.compat import Self
    from protest.core.fixture import FixtureCallable
    from protest.core.suite import ProTestSuite
    from protest.plugin import PluginBase

from protest.di.resolver import FIXTURE_FACTORY_ATTR, Resolver, is_factory_fixture
from protest.events.bus import EventBus
from protest.events.types import Event

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class ProTestSession:
    """Main test session orchestrator.

    Manages test collection, fixture resolution, and plugin coordination.
    Use as async context manager to ensure proper fixture teardown.

    Fixtures registered with @session.fixture() live for the entire session.

    Args:
        concurrency: Number of parallel test workers (default: 1).
        autouse: Fixtures to auto-resolve at session start before any test runs.
    """

    def __init__(
        self,
        concurrency: int = 1,
        autouse: list[FixtureCallable] | None = None,
    ) -> None:
        self._resolver = Resolver()
        self._events = EventBus()
        self._suites: list[ProTestSuite] = []
        self._tests: list[Callable[..., Any]] = []
        self._fixtures: list[FixtureCallable] = []
        self._concurrency = max(1, concurrency)
        self._autouse = autouse or []

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
    def fixtures(self) -> list[FixtureCallable]:
        return self._fixtures

    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def fixture(self, factory: bool = False) -> Callable[[FuncT], FuncT]:
        """Register a fixture scoped to the session (lives entire session)."""

        def decorator(func: FuncT) -> FuncT:
            if factory:
                setattr(func, FIXTURE_FACTORY_ATTR, True)
            self._fixtures.append(func)
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
        for func in self._fixtures:
            factory = is_factory_fixture(func)
            self._resolver.register(func, scope_path=None, is_factory=factory)
        self._register_suite_fixtures(self._suites)

    def _register_suite_fixtures(self, suites: list[ProTestSuite]) -> None:
        """Recursively register fixtures from suites."""
        for suite in suites:
            for func in suite.fixtures:
                factory = is_factory_fixture(func)
                self._resolver.register(
                    func, scope_path=suite.full_path, is_factory=factory
                )
            self._register_suite_fixtures(suite.suites)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
