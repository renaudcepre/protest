from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.fixture import FixtureCallable
    from protest.core.session import ProTestSession

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class ProTestSuite:
    """Groups related tests with optional max concurrency and nested suites.

    Suites provide scoped fixture context. Fixtures registered with @suite.fixture()
    are created once per suite and torn down when the suite completes.

    Suites can be nested: child suites can access parent's fixtures but not vice-versa.

    Args:
        name: Unique identifier for this suite.
        max_concurrency: Cap concurrency for this suite (takes min with session/CLI).
    """

    def __init__(self, name: str, max_concurrency: int | None = None) -> None:
        self._name = name
        self._session: ProTestSession | None = None
        self._parent_suite: ProTestSuite | None = None
        self._tests: list[Callable[..., Any]] = []
        self._suites: list[ProTestSuite] = []
        self._fixtures: list[tuple[FixtureCallable, bool]] = []
        self._max_concurrency = max_concurrency

    @property
    def name(self) -> str:
        return self._name

    @property
    def full_path(self) -> str:
        """Return hierarchical path: Parent::Child::GrandChild."""
        if self._parent_suite:
            return f"{self._parent_suite.full_path}::{self._name}"
        return self._name

    @property
    def max_concurrency(self) -> int | None:
        return self._max_concurrency

    @property
    def tests(self) -> list[Callable[..., Any]]:
        return self._tests

    @property
    def suites(self) -> list[ProTestSuite]:
        return self._suites

    @property
    def fixtures(self) -> list[tuple[FixtureCallable, bool]]:
        return self._fixtures

    def test(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._tests.append(func)
            return func

        return decorator

    def fixture(self, factory: bool = False) -> Callable[[FuncT], FuncT]:
        """Register a fixture scoped to this suite."""

        def decorator(func: FuncT) -> FuncT:
            self._fixtures.append((func, factory))
            return func

        return decorator

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a child suite. Child can access parent's fixtures."""
        suite._parent_suite = self
        if self._session:
            suite._attach_to_session(self._session)
        self._suites.append(suite)

    def _attach_to_session(self, session: ProTestSession) -> None:
        self._session = session
        for child in self._suites:
            child._attach_to_session(session)
