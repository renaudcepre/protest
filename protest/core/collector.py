"""Test collection and TestItem data structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from inspect import signature
from itertools import groupby, product
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin

from protest.di.markers import ForEach, From
from protest.utils import get_callable_name

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession
    from protest.core.suite import ProTestSuite


@dataclass
class TestItem:
    """Atomic unit representing a test with its metadata."""

    func: Callable[..., Any]
    suite: ProTestSuite | None
    tags: set[str] = field(default_factory=set)
    case_kwargs: dict[str, Any] = field(default_factory=dict)
    case_ids: list[str] = field(default_factory=list)

    @property
    def test_name(self) -> str:
        return get_callable_name(self.func)

    @property
    def module_path(self) -> str:
        return getattr(self.func, "__module__", "<unknown>")

    @property
    def suite_path(self) -> str | None:
        return self.suite.full_path if self.suite else None

    @property
    def node_id(self) -> str:
        if self.suite_path:
            base = f"{self.module_path}::{self.suite_path}::{self.test_name}"
        else:
            base = f"{self.module_path}::{self.test_name}"
        if self.case_ids:
            return f"{base}[{'-'.join(self.case_ids)}]"
        return base


def _extract_from_params(func: Callable[..., Any]) -> dict[str, ForEach[Any]]:
    """Extract parameters annotated with From(source)."""
    result: dict[str, ForEach[Any]] = {}
    for param_name, param in signature(func).parameters.items():
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, From):
                    result[param_name] = metadata.source
                    break
    return result


def _expand_test(
    func: Callable[..., Any], suite: ProTestSuite | None
) -> list[TestItem]:
    """Expand a test function into multiple TestItems based on From() params."""
    from_params = _extract_from_params(func)

    if not from_params:
        return [TestItem(func=func, suite=suite)]

    param_names = list(from_params.keys())
    sources = [from_params[name] for name in param_names]

    items: list[TestItem] = []
    for combination in product(*sources):
        case_kwargs = dict(zip(param_names, combination, strict=True))
        case_ids = [sources[idx].get_id(val) for idx, val in enumerate(combination)]

        items.append(
            TestItem(
                func=func,
                suite=suite,
                case_kwargs=case_kwargs,
                case_ids=case_ids,
            )
        )

    return items


class Collector:
    """Collects tests from a session, recursively traversing nested suites."""

    def collect(self, session: ProTestSession) -> list[TestItem]:
        items: list[TestItem] = []

        for test_func in session.tests:
            items.extend(_expand_test(test_func, suite=None))

        for suite in session.suites:
            items.extend(self._collect_from_suite(suite))

        return items

    def _collect_from_suite(self, suite: ProTestSuite) -> list[TestItem]:
        """Recursively collect tests from suite and its children."""
        items: list[TestItem] = []

        for test_func in suite.tests:
            items.extend(_expand_test(test_func, suite))

        for child in suite.suites:
            items.extend(self._collect_from_suite(child))

        return items


def chunk_by_suite(items: list[TestItem]) -> list[list[TestItem]]:
    """Group contiguous tests by suite."""
    if not items:
        return []
    return [list(group) for _, group in groupby(items, key=lambda item: item.suite)]


def get_last_chunk_index_per_suite(chunks: list[list[TestItem]]) -> dict[str, int]:
    """For each suite, return the index of its last chunk (including descendants)."""
    last_indices: dict[str, int] = {}
    for chunk_idx, chunk in enumerate(chunks):
        suite = chunk[0].suite
        if suite:
            last_indices[suite.full_path] = chunk_idx
            _update_parent_indices(last_indices, suite, chunk_idx)
    return last_indices


def _update_parent_indices(
    last_indices: dict[str, int], suite: ProTestSuite, chunk_idx: int
) -> None:
    """Update parent suite indices when a child chunk is seen."""
    parent = suite._parent_suite
    while parent:
        last_indices[parent.full_path] = chunk_idx
        parent = parent._parent_suite
