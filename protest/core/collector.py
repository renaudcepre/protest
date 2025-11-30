"""Test collection and TestItem data structure."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.session import ProTestSession


def get_node_id(func: Callable[..., Any], suite_name: str | None) -> str:
    """Build the node_id: module.path::Suite::test or module.path::test"""
    module_path: str = func.__module__  # type: ignore[attr-defined]
    func_name: str = func.__name__  # type: ignore[attr-defined]
    if suite_name:
        return f"{module_path}::{suite_name}::{func_name}"
    return f"{module_path}::{func_name}"


@dataclass
class TestItem:
    """Atomic unit representing a test with its metadata."""

    node_id: str
    func: Callable[..., Any]
    suite_name: str | None
    tags: set[str] = field(default_factory=set)


class Collector:
    """Collects tests from a session and produces a flat list of TestItem."""

    def collect(self, session: ProTestSession) -> list[TestItem]:
        items: list[TestItem] = []

        for test_func in session.tests:
            node_id = get_node_id(test_func, None)
            items.append(TestItem(node_id=node_id, func=test_func, suite_name=None))

        for suite in session.suites:
            for test_func in suite.tests:
                node_id = get_node_id(test_func, suite.name)
                items.append(
                    TestItem(node_id=node_id, func=test_func, suite_name=suite.name)
                )

        return items


def chunk_by_suite(items: list[TestItem]) -> list[list[TestItem]]:
    """Group contiguous tests by suite."""
    if not items:
        return []
    return [
        list(group) for _, group in groupby(items, key=lambda item: item.suite_name)
    ]


def get_last_chunk_index_per_suite(chunks: list[list[TestItem]]) -> dict[str, int]:
    """For each suite, return the index of its last chunk."""
    last_indices: dict[str, int] = {}
    for chunk_idx, chunk in enumerate(chunks):
        suite_name = chunk[0].suite_name
        if suite_name:
            last_indices[suite_name] = chunk_idx
    return last_indices
