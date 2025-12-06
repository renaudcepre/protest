from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest.entities import TestItem
from protest.filters import KeywordFilterPlugin

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_test_item(
    name: str, case_ids: list[str] | None = None, tags: set[str] | None = None
) -> TestItem:
    def dummy() -> None:
        pass

    dummy.__name__ = name
    dummy.__module__ = "mod"
    return TestItem(func=dummy, suite=None, case_ids=case_ids or [], tags=tags or set())


@pytest.fixture
def make_item() -> Callable[[str, list[str] | None, set[str] | None], TestItem]:
    return _make_test_item


class TestKeywordFilterPluginNoPatterns:
    def test_no_patterns_returns_all(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin()
        items = [make_item("test_login"), make_item("test_logout")]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count

    def test_none_patterns_returns_all(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=None)
        items = [make_item("test_a"), make_item("test_b")]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count

    def test_empty_list_returns_all(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=[])
        items = [make_item("test_a"), make_item("test_b")]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestKeywordFilterPluginSinglePattern:
    def test_matches_substring(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["login"])
        items = [
            make_item("test_login"),
            make_item("test_user_login"),
            make_item("test_logout"),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count
        names = {item.test_name for item in result}
        assert names == {"test_login", "test_user_login"}

    def test_no_match_filters_out(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["nonexistent"])
        items = [make_item("test_login"), make_item("test_logout")]
        result = plugin.on_collection_finish(items)
        expected_count = 0
        assert len(result) == expected_count

    def test_exact_match(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["test_login"])
        items = [make_item("test_login"), make_item("test_login_fail")]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestKeywordFilterPluginMultiplePatterns:
    def test_multiple_patterns_or_logic(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["login", "auth"])
        items = [
            make_item("test_login"),
            make_item("test_auth"),
            make_item("test_logout"),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count
        names = {item.test_name for item in result}
        assert names == {"test_login", "test_auth"}


class TestKeywordFilterPluginCaseIds:
    def test_matches_case_ids(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["admin"])
        items = [
            make_item("test_user", ["admin"]),
            make_item("test_user", ["guest"]),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].case_ids == ["admin"]

    def test_matches_multiple_case_ids(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["admin-create"])
        items = [
            make_item("test_user", ["admin", "create"]),
            make_item("test_user", ["guest", "read"]),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count

    def test_matches_test_name_with_case_ids(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["test_user"])
        items = [
            make_item("test_user", ["admin"]),
            make_item("test_role", ["admin"]),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_user"


class TestKeywordFilterPluginEdgeCases:
    def test_case_sensitive(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["Login"])
        items = [make_item("test_login"), make_item("test_Login")]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_Login"

    def test_empty_items_list(self) -> None:
        plugin = KeywordFilterPlugin(patterns=["login"])
        result = plugin.on_collection_finish([])
        expected_count = 0
        assert len(result) == expected_count

    def test_special_characters_in_pattern(
        self, make_item: Callable[[str, list[str] | None, set[str] | None], TestItem]
    ) -> None:
        plugin = KeywordFilterPlugin(patterns=["test_"])
        items = [make_item("test_login"), make_item("login_test")]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_login"
