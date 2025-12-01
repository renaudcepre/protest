"""Test collection and TestItem data structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession
    from protest.core.suite import ProTestSuite


def get_node_id(func: Callable[..., Any], suite_path: str | None) -> str:
    """Build the node_id: module.path::Parent::Child::test or module.path::test"""
    module_path: str = func.__module__  # type: ignore[attr-defined]
    func_name: str = func.__name__  # type: ignore[attr-defined]
    if suite_path:
        return f"{module_path}::{suite_path}::{func_name}"
    return f"{module_path}::{func_name}"


@dataclass
class TestItem:
    """Atomic unit representing a test with its metadata."""

    node_id: str
    func: Callable[..., Any]
    suite: ProTestSuite | None
    tags: set[str] = field(default_factory=set)

    @property
    def suite_path(self) -> str | None:
        return self.suite.full_path if self.suite else None


class Collector:
    """Collects tests from a session, recursively traversing nested suites."""

    def collect(self, session: ProTestSession) -> list[TestItem]:
        items: list[TestItem] = []

        for test_func in session.tests:
            node_id = get_node_id(test_func, None)
            items.append(TestItem(node_id=node_id, func=test_func, suite=None))

        for suite in session.suites:
            items.extend(self._collect_from_suite(suite))

        return items

    def _collect_from_suite(self, suite: ProTestSuite) -> list[TestItem]:
        """Recursively collect tests from suite and its children."""
        items: list[TestItem] = []

        for test_func in suite.tests:
            node_id = get_node_id(test_func, suite.full_path)
            items.append(TestItem(node_id=node_id, func=test_func, suite=suite))

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
