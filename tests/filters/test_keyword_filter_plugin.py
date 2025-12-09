from __future__ import annotations

import pytest

from protest.filters import KeywordFilterPlugin
from tests.factories.test_items import make_test_item


class TestKeywordFilterPluginNoPatterns:
    @pytest.mark.parametrize(
        "patterns",
        [
            pytest.param(None, id="none_patterns"),
            pytest.param([], id="empty_list"),
        ],
    )
    def test_returns_all_items(self, patterns: list[str] | None) -> None:
        """Given no patterns, when filtering, then all items returned."""
        plugin = KeywordFilterPlugin(patterns=patterns)
        items = [make_test_item("test_login"), make_test_item("test_logout")]

        result = plugin.on_collection_finish(items)

        expected_count = 2
        assert len(result) == expected_count


class TestKeywordFilterPluginSinglePattern:
    @pytest.mark.parametrize(
        "pattern,test_names,expected_names",
        [
            pytest.param(
                "login",
                ["test_login", "test_user_login", "test_logout"],
                {"test_login", "test_user_login"},
                id="substring_match",
            ),
            pytest.param(
                "nonexistent", ["test_login", "test_logout"], set(), id="no_match"
            ),
            pytest.param(
                "test_login",
                ["test_login", "test_login_fail"],
                {"test_login", "test_login_fail"},
                id="exact_match",
            ),
        ],
    )
    def test_single_pattern_matching(
        self, pattern: str, test_names: list[str], expected_names: set[str]
    ) -> None:
        """Given a single pattern, when filtering, then matching items returned."""
        plugin = KeywordFilterPlugin(patterns=[pattern])
        items = [make_test_item(name) for name in test_names]

        result = plugin.on_collection_finish(items)

        result_names = {item.test_name for item in result}
        assert result_names == expected_names


class TestKeywordFilterPluginMultiplePatterns:
    def test_multiple_patterns_or_logic(self) -> None:
        """Given multiple patterns, when filtering, then OR logic is applied."""
        plugin = KeywordFilterPlugin(patterns=["login", "auth"])
        items = [
            make_test_item("test_login"),
            make_test_item("test_auth"),
            make_test_item("test_logout"),
        ]

        result = plugin.on_collection_finish(items)

        expected_count = 2
        assert len(result) == expected_count
        names = {item.test_name for item in result}
        assert names == {"test_login", "test_auth"}


class TestKeywordFilterPluginCaseIds:
    @pytest.mark.parametrize(
        "pattern,items_data,expected_count,expected_case_ids",
        [
            pytest.param(
                "admin",
                [("test_user", ["admin"]), ("test_user", ["guest"])],
                1,
                ["admin"],
                id="matches_single_case_id",
            ),
            pytest.param(
                "admin-create",
                [("test_user", ["admin", "create"]), ("test_user", ["guest", "read"])],
                1,
                ["admin", "create"],
                id="matches_multiple_case_ids",
            ),
        ],
    )
    def test_matches_case_ids(
        self,
        pattern: str,
        items_data: list[tuple[str, list[str]]],
        expected_count: int,
        expected_case_ids: list[str],
    ) -> None:
        """Given pattern, when filtering with case_ids, then case_ids are matched."""
        plugin = KeywordFilterPlugin(patterns=[pattern])
        items = [
            make_test_item(name, case_ids=case_ids) for name, case_ids in items_data
        ]

        result = plugin.on_collection_finish(items)

        assert len(result) == expected_count
        assert result[0].case_ids == expected_case_ids

    def test_matches_test_name_with_case_ids(self) -> None:
        """Given pattern matching test name, when filtering, then test name is matched."""
        plugin = KeywordFilterPlugin(patterns=["test_user"])
        items = [
            make_test_item("test_user", case_ids=["admin"]),
            make_test_item("test_role", case_ids=["admin"]),
        ]

        result = plugin.on_collection_finish(items)

        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_user"


class TestKeywordFilterPluginEdgeCases:
    def test_case_sensitive(self) -> None:
        """Given case-sensitive pattern, when filtering, then exact case is matched."""
        plugin = KeywordFilterPlugin(patterns=["Login"])
        items = [make_test_item("test_login"), make_test_item("test_Login")]

        result = plugin.on_collection_finish(items)

        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_Login"

    def test_empty_items_list(self) -> None:
        """Given empty items list, when filtering, then empty list returned."""
        plugin = KeywordFilterPlugin(patterns=["login"])

        result = plugin.on_collection_finish([])

        expected_count = 0
        assert len(result) == expected_count

    def test_special_characters_in_pattern(self) -> None:
        """Given pattern with special characters, when filtering, then literal match is used."""
        plugin = KeywordFilterPlugin(patterns=["test_"])
        items = [make_test_item("test_login"), make_test_item("login_test")]

        result = plugin.on_collection_finish(items)

        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_login"
