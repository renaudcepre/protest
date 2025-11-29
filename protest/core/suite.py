from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from protest.core.fixture import FixtureCallable
from protest.core.scope import Scope
from protest.di.suite_resolver import SuiteResolver
from protest.exceptions import ProTestError

if TYPE_CHECKING:
    from protest.core.session import ProTestSession


class SuiteFixtureScopeError(ProTestError):
    def __init__(self, suite_name: str, fixture_name: str):
        super().__init__(
            f"Suite '{suite_name}' cannot define SESSION-scoped fixture '{fixture_name}'. "
            f"SESSION fixtures must be defined on the session."
        )


class ProTestSuite:
    def __init__(self, name: str) -> None:
        self._name = name
        self._session: ProTestSession | None = None
        self._resolver: SuiteResolver | None = None
        self._tests: list[Callable[..., Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    @property
    def resolver(self) -> SuiteResolver:
        if self._resolver is None:
            raise RuntimeError(
                f"Suite '{self._name}' must be included in a session before accessing resolver."
            )
        return self._resolver

    def fixture(self, scope: Scope = Scope.FUNCTION) -> Callable[[FixtureCallable], FixtureCallable]:
        def decorator(func: FixtureCallable) -> FixtureCallable:
            if self._session is None:
                raise RuntimeError(
                    f"Suite '{self._name}' must be included in a session before defining fixtures."
                )

            if scope == Scope.SESSION:
                from protest.core.fixture import get_callable_name
                raise SuiteFixtureScopeError(self._name, get_callable_name(func))

            self.resolver.register(func, scope)
            return func

        return decorator

    @property
    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def resolve_fixture(self, func: FixtureCallable) -> Any:
        return self.resolver.resolve(func)

    def _attach_to_session(self, session: ProTestSession) -> None:
        self._session = session
        self._resolver = SuiteResolver(session.resolver, self._name)
