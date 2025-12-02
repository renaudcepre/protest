from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest.entities import TestItem
from protest.tags.plugin import TagFilterPlugin

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_test_item(name: str, tags: set[str] | None = None) -> TestItem:
    def dummy() -> None:
        pass

    dummy.__name__ = name
    dummy.__module__ = "mod"
    return TestItem(func=dummy, suite=None, tags=tags or set())


@pytest.fixture
def make_item() -> Callable[[str, set[str] | None], TestItem]:
    return _make_test_item


class TestTagFilterPluginNoFilters:
    def test_no_filters_returns_all(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin()
        items = [make_item("test_a", {"x"}), make_item("test_b", {"y"})]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestTagFilterPluginInclude:
    def test_include_filters_matching(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"unit"})
        items = [
            make_item("test_a", {"unit"}),
            make_item("test_b", {"integration"}),
            make_item("test_c", {"unit", "fast"}),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count
        names = {item.test_name for item in result}
        assert names == {"test_a", "test_c"}

    def test_include_with_no_matches(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"nonexistent"})
        items = [make_item("test_a", {"x"}), make_item("test_b", {"y"})]
        result = plugin.on_collection_finish(items)
        expected_count = 0
        assert len(result) == expected_count

    def test_include_with_or_logic(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"api", "unit"})
        items = [
            make_item("test_a", {"api"}),
            make_item("test_b", {"unit"}),
            make_item("test_c", {"integration"}),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestTagFilterPluginExclude:
    def test_exclude_removes_matching(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(exclude_tags={"flaky"})
        items = [
            make_item("test_a", {"unit", "flaky"}),
            make_item("test_b", {"unit"}),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_b"

    def test_exclude_with_no_matches(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(exclude_tags={"nonexistent"})
        items = [make_item("test_a", {"x"}), make_item("test_b", {"y"})]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestTagFilterPluginCombined:
    def test_include_and_exclude_combined(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"api"}, exclude_tags={"slow"})
        items = [
            make_item("test_a", {"api", "slow"}),
            make_item("test_b", {"api"}),
            make_item("test_c", {"unit"}),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_b"

    def test_exclude_takes_precedence(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"api"}, exclude_tags={"api"})
        items = [make_item("test_a", {"api"})]
        result = plugin.on_collection_finish(items)
        expected_count = 0
        assert len(result) == expected_count


class TestTagFilterPluginEdgeCases:
    def test_empty_tags_on_item(
        self, make_item: Callable[[str, set[str] | None], TestItem]
    ) -> None:
        plugin = TagFilterPlugin(include_tags={"unit"})
        items = [make_item("test_a", set()), make_item("test_b", {"unit"})]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_b"

    def test_empty_items_list(self) -> None:
        plugin = TagFilterPlugin(include_tags={"unit"})
        result = plugin.on_collection_finish([])
        expected_count = 0
        assert len(result) == expected_count
