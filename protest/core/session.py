from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from protest.plugin import PluginBase

from protest.core.fixture import FixtureCallable
from protest.core.scope import Scope
from protest.core.suite import ProTestSuite
from protest.di.resolver import Resolver
from protest.events.bus import EventBus
from protest.events.types import Event


class ProTestSession:
    def __init__(self, concurrency: int = 1) -> None:
        self._resolver = Resolver()
        self._events = EventBus()
        self._suites: list[ProTestSuite] = []
        self._tests: list[Callable[..., Any]] = []
        self._concurrency = max(1, concurrency)

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

    def fixture(
        self, scope: Scope = Scope.SESSION
    ) -> Callable[[FixtureCallable], FixtureCallable]:
        def decorator(func: FixtureCallable) -> FixtureCallable:
            self._resolver.register(func, scope)
            return func

        return decorator

    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def include_suite(self, suite: ProTestSuite) -> None:
        suite._attach_to_session(self)
        self._suites.append(suite)

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
        await self._resolver.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return await self._resolver.__aexit__(exc_type, exc_val, exc_tb)
