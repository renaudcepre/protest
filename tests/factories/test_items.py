from __future__ import annotations

from typing import TYPE_CHECKING

from protest.entities import TestItem

if TYPE_CHECKING:
    from protest.core.suite import ProTestSuite


def make_test_item(
    name: str,
    module: str = "mod",
    suite: ProTestSuite | None = None,
    case_ids: list[str] | None = None,
    tags: set[str] | None = None,
) -> TestItem:
    """Factory for creating TestItem instances in tests."""

    def dummy() -> None:
        pass

    dummy.__name__ = name
    dummy.__module__ = module
    return TestItem(
        func=dummy,
        suite=suite,
        case_ids=case_ids or [],
        tags=tags or set(),
    )


def make_test_item_from_node_id(node_id: str) -> TestItem:
    """Create a TestItem from a node_id string (e.g., 'mod::test_name')."""
    parts = node_id.split("::")
    module = parts[0]
    func_name = parts[-1]

    def dummy() -> None:
        pass

    dummy.__module__ = module
    dummy.__name__ = func_name

    return TestItem(func=dummy, suite=None)
