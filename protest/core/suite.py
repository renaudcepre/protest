from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession

from protest.core.collector import validate_no_from_params
from protest.di.decorators import FixtureWrapper
from protest.entities import FixtureRegistration, TestRegistration
from protest.utils import normalize_reason

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class ProTestSuite:
    """Groups related tests with optional max concurrency and nested suites.

    Suites provide scoped fixture context. Fixtures registered with @suite.fixture()
    are created once per suite and torn down when the suite completes.

    Suites can be nested: child suites can access parent's fixtures but not vice-versa.
    Tags are inherited from parent suites.

    Args:
        name: Unique identifier for this suite.
        max_concurrency: Cap concurrency for this suite (takes min with session/CLI).
        tags: Tags for this suite (inherited by tests and child suites).
        description: Optional description for documentation purposes.
    """

    def __init__(
        self,
        name: str,
        max_concurrency: int | None = None,
        tags: list[str] | None = None,
        description: str | None = None,
    ) -> None:
        self._name = name
        self._description = description
        self._session: ProTestSession | None = None
        self._parent_suite: ProTestSuite | None = None
        self._tests: list[TestRegistration] = []
        self._suites: list[ProTestSuite] = []
        self._fixtures: list[FixtureRegistration] = []
        self._max_concurrency = max_concurrency
        self._tags: set[str] = set(tags) if tags else set()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str | None:
        return self._description

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
    def tags(self) -> set[str]:
        """Tags declared directly on this suite."""
        return self._tags

    @property
    def all_tags(self) -> set[str]:
        """All tags including inherited from parent suites."""
        if self._parent_suite:
            return self._tags | self._parent_suite.all_tags
        return self._tags.copy()

    @property
    def tests(self) -> list[TestRegistration]:
        return self._tests

    @property
    def suites(self) -> list[ProTestSuite]:
        return self._suites

    @property
    def fixtures(self) -> list[FixtureRegistration]:
        return self._fixtures

    def test(
        self,
        tags: list[str] | None = None,
        skip: bool | str = False,
        xfail: bool | str = False,
        timeout: float | None = None,
    ) -> Callable[[FuncT], FuncT]:
        def decorator(func: FuncT) -> FuncT:
            if timeout is not None and timeout < 0:
                raise ValueError(f"timeout must be non-negative, got {timeout}")
            self._tests.append(
                TestRegistration(
                    func=func,
                    tags=set(tags) if tags else set(),
                    skip_reason=normalize_reason(skip, "Skipped"),
                    xfail_reason=normalize_reason(xfail, "Expected failure"),
                    timeout=timeout,
                )
            )
            return func

        return decorator

    def fixture(
        self,
        tags: list[str] | None = None,
    ) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
        """Register a fixture scoped to this suite."""

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
        """Register a factory fixture scoped to this suite."""

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
        """Add a child suite. Child can access parent's fixtures."""
        suite._parent_suite = self
        if self._session:
            suite._attach_to_session(self._session)
        self._suites.append(suite)

    def _attach_to_session(self, session: ProTestSession) -> None:
        self._session = session
        for child in self._suites:
            child._attach_to_session(session)
