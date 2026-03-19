from __future__ import annotations

from inspect import signature
from itertools import groupby, product
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from protest.di.decorators import get_fixture_marker, unwrap_fixture
from protest.di.markers import Use
from protest.di.validation import _extract_from_params
from protest.entities import FixtureCallable, SuitePath, TestItem, TestRegistration

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession
    from protest.core.suite import ProTestSuite


def _extract_use_fixtures(func: Callable[..., Any]) -> list[FixtureCallable]:
    """Extract fixtures referenced via Use() markers in function parameters."""
    try:
        type_hints = get_type_hints(func, include_extras=True)
    except Exception:
        type_hints = {}

    fixtures: list[FixtureCallable] = []
    for param_name in signature(func).parameters:
        annotation = type_hints.get(param_name)
        if annotation is not None and get_origin(annotation) is Annotated:
            for metadata in get_args(annotation)[1:]:
                if isinstance(metadata, Use):
                    # Unwrap FixtureWrapper to get the original function
                    fixtures.append(unwrap_fixture(metadata.dependency))
                    break
    return fixtures


def get_transitive_fixtures(
    func: Callable[..., Any],
    visited: set[FixtureCallable] | None = None,
) -> set[FixtureCallable]:
    """Get all fixtures (direct + transitive) used by a function.

    Recursively follows Use() markers to collect all fixtures in the
    dependency chain. Handles cycles via visited set.

    Args:
        func: The function to analyze (test or fixture).
        visited: Set of already-visited fixtures (for cycle prevention).

    Returns:
        Set of all fixture functions used directly or transitively.
    """
    if visited is None:
        visited = set()

    result: set[FixtureCallable] = set()
    direct = _extract_use_fixtures(func)

    for fixture_func in direct:
        if fixture_func in visited:
            continue
        visited.add(fixture_func)
        result.add(fixture_func)
        # Recursively get fixtures used by this fixture
        result.update(get_transitive_fixtures(fixture_func, visited))

    return result


class Collector:
    """Collects tests from a session, recursively traversing nested suites."""

    def __init__(self) -> None:
        self._fixture_tags: dict[FixtureCallable, set[str]] = {}
        self._fixture_deps: dict[FixtureCallable, list[FixtureCallable]] = {}

    def collect(self, session: ProTestSession) -> list[TestItem]:
        """Collect all tests from session and nested suites into TestItems."""
        self._build_fixture_index(session)

        items: list[TestItem] = []

        for test_reg in session.tests:
            items.extend(self._expand_registration(test_reg, suite=None))

        for suite in session.suites:
            items.extend(self._collect_from_suite(suite))

        return items

    def _build_fixture_index(self, session: ProTestSession) -> None:
        """Build index of all fixtures with their tags and dependencies."""
        for fixture_reg in session.fixtures:
            self._fixture_tags[fixture_reg.func] = fixture_reg.tags
            self._fixture_deps[fixture_reg.func] = _extract_use_fixtures(
                fixture_reg.func
            )

        self._index_suite_fixtures(session.suites)

    def _index_suite_fixtures(self, suites: list[ProTestSuite]) -> None:
        """Recursively index fixtures from suites."""
        for suite in suites:
            for fixture_reg in suite.fixtures:
                self._fixture_tags[fixture_reg.func] = fixture_reg.tags
                self._fixture_deps[fixture_reg.func] = _extract_use_fixtures(
                    fixture_reg.func
                )
            self._index_suite_fixtures(suite.suites)

    def _get_transitive_fixture_tags(
        self, func: FixtureCallable, visited: set[FixtureCallable] | None = None
    ) -> set[str]:
        """Get all tags from a fixture and its dependencies (transitive)."""
        if visited is None:
            visited = set()
        if func in visited:
            return set()
        visited.add(func)

        # Try indexed tags first, fallback to marker for unbound fixtures
        if func in self._fixture_tags:
            tags = self._fixture_tags[func].copy()
        else:
            marker = get_fixture_marker(func)
            tags = set(marker.tags) if marker else set()

        # Get dependencies: indexed or extract from signature for unbound
        deps = self._fixture_deps.get(func) or _extract_use_fixtures(func)
        for dep_func in deps:
            tags.update(self._get_transitive_fixture_tags(dep_func, visited))

        return tags

    def _compute_test_tags(
        self, test_reg: TestRegistration, suite: ProTestSuite | None
    ) -> set[str]:
        """Compute all tags for a test: explicit + suite + fixture (transitive)."""
        tags = test_reg.tags.copy()

        if suite:
            tags.update(suite.all_tags)

        for fixture_func in _extract_use_fixtures(test_reg.func):
            tags.update(self._get_transitive_fixture_tags(fixture_func))

        return tags

    def _expand_registration(
        self, test_reg: TestRegistration, suite: ProTestSuite | None
    ) -> list[TestItem]:
        """Expand a TestRegistration into TestItems with computed tags."""
        tags = self._compute_test_tags(test_reg, suite)
        from_params = _extract_from_params(test_reg.func)

        if not from_params:
            return [
                TestItem(
                    func=test_reg.func,
                    suite=suite,
                    tags=tags,
                    skip=test_reg.skip,
                    xfail=test_reg.xfail,
                    timeout=test_reg.timeout,
                    retry=test_reg.retry,
                )
            ]

        param_names = list(from_params.keys())
        sources = [from_params[name] for name in param_names]

        items: list[TestItem] = []
        for combination in product(*sources):
            case_kwargs = dict(zip(param_names, combination, strict=True))
            case_ids = [
                sources[index].get_id(value) for index, value in enumerate(combination)
            ]

            items.append(
                TestItem(
                    func=test_reg.func,
                    suite=suite,
                    tags=tags.copy(),
                    case_kwargs=case_kwargs,
                    case_ids=case_ids,
                    skip=test_reg.skip,
                    xfail=test_reg.xfail,
                    timeout=test_reg.timeout,
                    retry=test_reg.retry,
                )
            )

        return items

    def _collect_from_suite(self, suite: ProTestSuite) -> list[TestItem]:
        """Recursively collect tests from suite and its children."""
        items: list[TestItem] = []

        for test_reg in suite.tests:
            items.extend(self._expand_registration(test_reg, suite))

        for child in suite.suites:
            items.extend(self._collect_from_suite(child))

        return items


def chunk_by_suite(items: list[TestItem]) -> list[list[TestItem]]:
    """Group contiguous tests by suite."""
    if not items:
        return []
    return [list(group) for _, group in groupby(items, key=lambda item: item.suite)]


def get_last_chunk_index_per_suite(
    chunks: list[list[TestItem]],
) -> dict[SuitePath, int]:
    """For each suite, return the index of its last chunk (including descendants)."""
    last_indices: dict[SuitePath, int] = {}
    for chunk_idx, chunk in enumerate(chunks):
        suite = chunk[0].suite
        if suite:
            last_indices[suite.full_path] = chunk_idx
            _update_parent_indices(last_indices, suite, chunk_idx)
    return last_indices


def _update_parent_indices(
    last_indices: dict[SuitePath, int], suite: ProTestSuite, chunk_idx: int
) -> None:
    """Update parent suite indices when a child chunk is seen."""
    parent = suite._parent_suite
    while parent:
        last_indices[parent.full_path] = chunk_idx
        parent = parent._parent_suite
