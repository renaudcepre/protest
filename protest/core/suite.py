from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from protest.di.decorators import unwrap_fixture

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession

from protest.di.decorators import get_fixture_marker
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
from protest.exceptions import ConcurrencyMismatchError

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
    def effective_max_concurrency(self) -> int | None:
        """Effective max_concurrency including inheritance from parent suites."""
        if self._max_concurrency is not None:
            return self._max_concurrency
        if self._parent_suite:
            return self._parent_suite.effective_max_concurrency
        return None

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

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a child suite. Child can access parent's fixtures."""
        parent_effective = self.effective_max_concurrency
        child_explicit = suite._max_concurrency
        if (
            parent_effective is not None
            and child_explicit is not None
            and child_explicit > parent_effective
        ):
            raise ConcurrencyMismatchError(
                suite.name, child_explicit, self.name, parent_effective
            )

        suite._parent_suite = self
        if self._session:
            suite._attach_to_session(self._session)
        self._suites.append(suite)

    def fixture(
        self,
        fn: Callable[..., object],
        autouse: bool = False,
    ) -> None:
        """Bind a fixture to this suite (SUITE scope).

        The fixture must be decorated with @fixture() or @factory().
        Scope is determined by this binding - no scope declaration needed
        on the decorator.

        Fixtures bound here will be:
        - Cached once per this suite (not per child suite)
        - Accessible to all tests in this suite AND child suites
        - Torn down when this suite completes

        Args:
            fn: Function decorated with @fixture() or @factory().
            autouse: If True, resolve automatically when suite starts.

        Raises:
            ValueError: If the function is not decorated with @fixture/@factory.

        Example:
            @fixture()
            def api_client():
                yield Client()

            api_suite = ProTestSuite("API")
            api_suite.fixture(api_client)  # SUITE scope
            api_suite.fixture(setup_env, autouse=True)  # SUITE + auto-resolve
        """

        actual_func = unwrap_fixture(fn)
        marker = get_fixture_marker(fn)
        if marker is None:
            raise ValueError(
                f"Function '{actual_func.__name__}' is not decorated with "
                "@fixture() or @factory(). Use the decorator first."
            )

        registration = FixtureRegistration(
            func=actual_func,
            is_factory=marker.is_factory,
            cache=marker.cache,
            managed=marker.managed,
            tags=set(marker.tags),
            autouse=autouse,
        )
        self._fixtures.append(registration)

    def _attach_to_session(self, session: ProTestSession) -> None:
        self._session = session
        for child in self._suites:
            child._attach_to_session(session)
