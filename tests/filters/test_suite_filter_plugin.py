from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest.core.suite import ProTestSuite
from protest.entities import TestItem
from protest.filters import SuiteFilterPlugin

if TYPE_CHECKING:
    from collections.abc import Callable


def _make_test_item(
    name: str, suite: ProTestSuite | None = None, tags: set[str] | None = None
) -> TestItem:
    def dummy() -> None:
        pass

    dummy.__name__ = name
    dummy.__module__ = "mod"
    return TestItem(func=dummy, suite=suite, tags=tags or set())


@pytest.fixture
def make_item() -> Callable[[str, ProTestSuite | None, set[str] | None], TestItem]:
    return _make_test_item


@pytest.fixture
def api_suite() -> ProTestSuite:
    return ProTestSuite("API")


@pytest.fixture
def users_suite(api_suite: ProTestSuite) -> ProTestSuite:
    users = ProTestSuite("Users")
    api_suite.add_suite(users)
    return users


@pytest.fixture
def orders_suite(api_suite: ProTestSuite) -> ProTestSuite:
    orders = ProTestSuite("Orders")
    api_suite.add_suite(orders)
    return orders


class TestSuiteFilterPluginNoFilter:
    def test_no_filter_returns_all(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin()
        items = [
            make_item("test_standalone"),
            make_item("test_api", api_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count

    def test_none_filter_returns_all(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter=None)
        items = [make_item("test_a", api_suite), make_item("test_b", api_suite)]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count


class TestSuiteFilterPluginBasic:
    def test_matches_exact_suite(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="API")
        items = [make_item("test_api", api_suite)]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_api"

    def test_excludes_standalone_tests(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="API")
        items = [
            make_item("test_standalone"),
            make_item("test_api", api_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_api"

    def test_excludes_sibling_suites(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        other_suite = ProTestSuite("Other")
        plugin = SuiteFilterPlugin(suite_filter="API")
        items = [
            make_item("test_api", api_suite),
            make_item("test_other", other_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_api"


class TestSuiteFilterPluginNested:
    def test_matches_child_suites(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
        users_suite: ProTestSuite,
        orders_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="API")
        items = [
            make_item("test_api", api_suite),
            make_item("test_users", users_suite),
            make_item("test_orders", orders_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 3
        assert len(result) == expected_count

    def test_filter_specific_child(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
        users_suite: ProTestSuite,
        orders_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="API::Users")
        items = [
            make_item("test_api", api_suite),
            make_item("test_users", users_suite),
            make_item("test_orders", orders_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_users"

    def test_filter_deeply_nested(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        users_suite: ProTestSuite,
    ) -> None:
        perms_suite = ProTestSuite("Permissions")
        users_suite.add_suite(perms_suite)
        plugin = SuiteFilterPlugin(suite_filter="API::Users")
        items = [
            make_item("test_users", users_suite),
            make_item("test_perms", perms_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 2
        assert len(result) == expected_count

    def test_partial_path_no_match(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        users_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="Users")
        items = [make_item("test_users", users_suite)]
        result = plugin.on_collection_finish(items)
        expected_count = 0
        assert len(result) == expected_count


class TestSuiteFilterPluginEdgeCases:
    def test_nonexistent_suite_returns_empty(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
        api_suite: ProTestSuite,
    ) -> None:
        plugin = SuiteFilterPlugin(suite_filter="NonExistent")
        items = [make_item("test_api", api_suite)]
        result = plugin.on_collection_finish(items)
        expected_count = 0
        assert len(result) == expected_count

    def test_empty_items_list(self) -> None:
        plugin = SuiteFilterPlugin(suite_filter="API")
        result = plugin.on_collection_finish([])
        expected_count = 0
        assert len(result) == expected_count

    def test_suite_name_prefix_collision(
        self,
        make_item: Callable[[str, ProTestSuite | None, set[str] | None], TestItem],
    ) -> None:
        api_suite = ProTestSuite("API")
        api_v2_suite = ProTestSuite("APIv2")
        plugin = SuiteFilterPlugin(suite_filter="API")
        items = [
            make_item("test_api", api_suite),
            make_item("test_api_v2", api_v2_suite),
        ]
        result = plugin.on_collection_finish(items)
        expected_count = 1
        assert len(result) == expected_count
        assert result[0].test_name == "test_api"
