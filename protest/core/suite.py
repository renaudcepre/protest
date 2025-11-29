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
            f"Suite '{suite_name}' cannot define SESSION-scoped fixture "
            f"'{fixture_name}'. SESSION fixtures must be defined on the session."
        )


class ProTestSuite:
    def __init__(self, name: str, concurrency: int | None = None) -> None:
        self._name = name
        self._session: ProTestSession | None = None
        self._resolver: SuiteResolver | None = None
        self._tests: list[Callable[..., Any]] = []
        self._concurrency = concurrency

    @property
    def name(self) -> str:
        return self._name

    @property
    def concurrency(self) -> int | None:
        return self._concurrency

    @property
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    @property
    def resolver(self) -> SuiteResolver:
        if self._resolver is None:
            msg = f"Suite '{self._name}' must be attached to a session first."
            raise RuntimeError(msg)
        return self._resolver

    def fixture(
        self, scope: Scope = Scope.FUNCTION
    ) -> Callable[[FixtureCallable], FixtureCallable]:
        def decorator(func: FixtureCallable) -> FixtureCallable:
            if self._session is None:
                msg = f"Suite '{self._name}' must be attached to a session first."
                raise RuntimeError(msg)

            if scope == Scope.SESSION:
                from protest.core.fixture import get_callable_name

                raise SuiteFixtureScopeError(self._name, get_callable_name(func))

            self.resolver.register(func, scope)
            return func

        return decorator

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
