from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any

from protest.core.fixture import FixtureCallable
from protest.core.scope import Scope
from protest.core.suite import ProTestSuite
from protest.di.resolver import Resolver


class ProTestSession:
    def __init__(self) -> None:
        self._resolver = Resolver()
        self._suites: list[ProTestSuite] = []
        self._tests: list[Callable[..., Any]] = []

    @property
    def resolver(self) -> Resolver:
        return self._resolver

    @property
    def suites(self) -> list[ProTestSuite]:
        return self._suites

    @property
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    def fixture(self, scope: Scope = Scope.SESSION) -> Callable[[FixtureCallable], FixtureCallable]:
        def decorator(func: FixtureCallable) -> FixtureCallable:
            self._resolver.register(func, scope)
            return func

        return decorator

    @property
    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def include_suite(self, suite: ProTestSuite) -> None:
        suite._attach_to_session(self)
        self._suites.append(suite)

    def __enter__(self) -> ProTestSession:
        self._resolver.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return self._resolver.__exit__(exc_type, exc_val, exc_tb)
