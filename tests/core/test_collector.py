"""Tests for test collection and TestItem data structure."""

from typing import Annotated

from protest import Use
from protest.core.collector import (
    Collector,
    TestItem,
    chunk_by_suite,
    get_last_chunk_index_per_suite,
)
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.di.decorators import fixture


class TestTestItemNodeId:
    """Tests for TestItem.node_id property."""

    def test_node_id_without_suite(self) -> None:
        """Node ID for standalone test: module.path::test"""

        def my_test() -> None:
            pass

        item = TestItem(func=my_test, suite=None)

        assert item.node_id == f"{my_test.__module__}::my_test"

    def test_node_id_with_suite(self) -> None:
        """Node ID for suite test: module.path::Suite::test"""
        suite = ProTestSuite("MySuite")

        def my_test() -> None:
            pass

        item = TestItem(func=my_test, suite=suite)

        assert item.node_id == f"{my_test.__module__}::MySuite::my_test"

    def test_node_id_with_case_ids(self) -> None:
        """Node ID with parameterized case IDs."""

        def my_test() -> None:
            pass

        item = TestItem(func=my_test, suite=None, case_ids=["alice", "admin"])

        assert item.node_id == f"{my_test.__module__}::my_test[alice-admin]"


class TestCollector:
    """Tests for Collector.collect()."""

    def test_collect_empty_session(self) -> None:
        """Empty session produces empty list."""
        session = ProTestSession()
        collector = Collector()

        items = collector.collect(session)

        assert items == []

    def test_collect_standalone_tests(self) -> None:
        """Collects standalone tests from session."""
        session = ProTestSession()

        @session.test()
        def test_one() -> None:
            pass

        @session.test()
        def test_two() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_count = 2
        assert len(items) == expected_count
        assert items[0].func == test_one
        assert items[0].suite is None
        assert items[1].func == test_two
        assert items[1].suite is None

    def test_collect_suite_tests(self) -> None:
        """Collects tests from suites."""
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.include_suite(suite)

        @suite.test()
        def suite_test() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_count = 1
        assert len(items) == expected_count
        assert items[0].func == suite_test
        assert items[0].suite is suite
        assert items[0].suite_path == "my_suite"

    def test_collect_mixed_tests(self) -> None:
        """Collects both standalone and suite tests."""
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.include_suite(suite)

        @session.test()
        def standalone_test() -> None:
            pass

        @suite.test()
        def suite_test() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_count = 2
        assert len(items) == expected_count
        assert items[0].suite is None
        assert items[1].suite_path == "my_suite"

    def test_collect_generates_correct_node_ids(self) -> None:
        """Collected items have correct node_ids."""
        session = ProTestSession()
        suite = ProTestSuite("MySuite")
        session.include_suite(suite)

        @session.test()
        def standalone() -> None:
            pass

        @suite.test()
        def in_suite() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        module = standalone.__module__
        assert items[0].node_id == f"{module}::standalone"
        assert items[1].node_id == f"{module}::MySuite::in_suite"


class TestChunkBySuite:
    """Tests for chunk_by_suite()."""

    def test_chunk_empty_list(self) -> None:
        """Empty list produces empty chunks."""
        chunks = chunk_by_suite([])

        assert chunks == []

    def test_chunk_single_suite(self) -> None:
        """All tests from same suite in one chunk."""
        suite = ProTestSuite("Suite")

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        items = [
            TestItem(func=test_a, suite=suite),
            TestItem(func=test_b, suite=suite),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 1
        expected_tests_in_chunk = 2
        assert len(chunks) == expected_chunk_count
        assert len(chunks[0]) == expected_tests_in_chunk

    def test_chunk_standalone_tests(self) -> None:
        """Standalone tests (None suite) grouped together."""

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        items = [
            TestItem(func=test_a, suite=None),
            TestItem(func=test_b, suite=None),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 1
        expected_tests_in_chunk = 2
        assert len(chunks) == expected_chunk_count
        assert len(chunks[0]) == expected_tests_in_chunk

    def test_chunk_alternating_suites(self) -> None:
        """Contiguous tests by suite, not merged if interleaved."""
        suite_a = ProTestSuite("A")
        suite_b = ProTestSuite("B")

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        def test_c() -> None:
            pass

        items = [
            TestItem(func=test_a, suite=suite_a),
            TestItem(func=test_b, suite=suite_b),
            TestItem(func=test_c, suite=suite_a),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 3
        assert len(chunks) == expected_chunk_count
        assert chunks[0][0].suite_path == "A"
        assert chunks[1][0].suite_path == "B"
        assert chunks[2][0].suite_path == "A"

    def test_chunk_standalone_then_suite(self) -> None:
        """Standalone tests followed by suite tests create separate chunks."""
        suite_s = ProTestSuite("S")

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        items = [
            TestItem(func=test_a, suite=None),
            TestItem(func=test_b, suite=suite_s),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 2
        assert len(chunks) == expected_chunk_count
        assert chunks[0][0].suite is None
        assert chunks[1][0].suite_path == "S"


class TestGetLastChunkIndexPerSuite:
    """Tests for get_last_chunk_index_per_suite()."""

    def test_empty_chunks(self) -> None:
        """Empty chunks returns empty dict."""
        result = get_last_chunk_index_per_suite([])

        assert result == {}

    def test_single_suite_single_chunk(self) -> None:
        """Single suite in one chunk."""
        suite_s = ProTestSuite("S")

        def test_a() -> None:
            pass

        chunks = [
            [TestItem(func=test_a, suite=suite_s)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"S": 0}

    def test_suite_split_across_chunks(self) -> None:
        """Suite appearing in multiple chunks tracks last occurrence."""
        suite_a = ProTestSuite("A")
        suite_b = ProTestSuite("B")

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        def test_c() -> None:
            pass

        chunks = [
            [TestItem(func=test_a, suite=suite_a)],
            [TestItem(func=test_b, suite=suite_b)],
            [TestItem(func=test_c, suite=suite_a)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"A": 2, "B": 1}

    def test_standalone_tests_not_tracked(self) -> None:
        """Standalone tests (suite=None) are not tracked."""

        def test_a() -> None:
            pass

        chunks = [
            [TestItem(func=test_a, suite=None)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {}

    def test_mixed_standalone_and_suite(self) -> None:
        """Only tracks suites, not standalone tests."""
        suite_s = ProTestSuite("S")

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        chunks = [
            [TestItem(func=test_a, suite=None)],
            [TestItem(func=test_b, suite=suite_s)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"S": 1}

    def test_nested_suites_updates_parent_indices(self) -> None:
        """Parent suite index is updated when child chunks appear."""
        api_suite = ProTestSuite("API")
        users_suite = ProTestSuite("Users")
        perms_suite = ProTestSuite("Perms")
        orders_suite = ProTestSuite("Orders")

        api_suite.add_suite(users_suite)
        users_suite.add_suite(perms_suite)
        api_suite.add_suite(orders_suite)

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        def test_c() -> None:
            pass

        def test_d() -> None:
            pass

        chunks = [
            [TestItem(func=test_a, suite=api_suite)],
            [TestItem(func=test_b, suite=users_suite)],
            [TestItem(func=test_c, suite=perms_suite)],
            [TestItem(func=test_d, suite=orders_suite)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result["API"] == 3
        assert result["API::Users"] == 2
        assert result["API::Users::Perms"] == 2
        assert result["API::Orders"] == 3


class TestTransitiveFixtureTags:
    """Tests for transitive tag collection from fixtures."""

    def test_diamond_dependency_collects_shared_fixture_tags_once(self) -> None:
        """Diamond pattern: A→B→D and A→C→D collects D's tags correctly.

        This test covers the `if func in visited: return set()` branch in
        _get_transitive_fixture_tags which handles shared dependencies.

        Structure:
            fixture D (tags: ["database"])
            fixture B → depends on D
            fixture C → depends on D
            fixture A → depends on B and C
            test → uses A

        D's tags should be collected exactly once via the visited set.
        """
        session = ProTestSession()

        @fixture(tags=["database"])
        def shared_fixture() -> str:
            return "shared"

        @fixture()
        def fixture_b(
            dep: Annotated[str, Use(shared_fixture)],
        ) -> str:
            return f"b-{dep}"

        @fixture()
        def fixture_c(
            dep: Annotated[str, Use(shared_fixture)],
        ) -> str:
            return f"c-{dep}"

        @fixture()
        def fixture_a(
            b: Annotated[str, Use(fixture_b)],
            c: Annotated[str, Use(fixture_c)],
        ) -> str:
            return f"a-{b}-{c}"

        session.fixture(shared_fixture)
        session.fixture(fixture_b)
        session.fixture(fixture_c)
        session.fixture(fixture_a)

        @session.test()
        def test_diamond(
            a: Annotated[str, Use(fixture_a)],
        ) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        # The "database" tag from shared_fixture should be propagated
        assert "database" in items[0].tags

    def test_deep_transitive_tags_propagation(self) -> None:
        """Tags propagate through multiple levels of fixture dependencies."""
        session = ProTestSession()

        @fixture(tags=["level3"])
        def deep_fixture() -> str:
            return "deep"

        @fixture(tags=["level2"])
        def mid_fixture(
            dep: Annotated[str, Use(deep_fixture)],
        ) -> str:
            return dep

        @fixture(tags=["level1"])
        def top_fixture(
            dep: Annotated[str, Use(mid_fixture)],
        ) -> str:
            return dep

        session.fixture(deep_fixture)
        session.fixture(mid_fixture)
        session.fixture(top_fixture)

        @session.test()
        def test_deep(
            f: Annotated[str, Use(top_fixture)],
        ) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].tags == {"level1", "level2", "level3"}
