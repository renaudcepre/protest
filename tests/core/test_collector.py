"""Tests for test collection and TestItem data structure."""

from protest.core.collector import (
    Collector,
    TestItem,
    chunk_by_suite,
    get_last_chunk_index_per_suite,
    get_node_id,
)
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite


class TestGetNodeId:
    """Tests for node_id generation."""

    def test_node_id_without_suite(self) -> None:
        """Node ID for standalone test: module.path::test"""

        def my_test() -> None:
            pass

        node_id = get_node_id(my_test, None)

        assert node_id == f"{my_test.__module__}::my_test"

    def test_node_id_with_suite(self) -> None:
        """Node ID for suite test: module.path::Suite::test"""

        def my_test() -> None:
            pass

        node_id = get_node_id(my_test, "MySuite")

        assert node_id == f"{my_test.__module__}::MySuite::my_test"


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
        assert items[0].suite_name is None
        assert items[1].func == test_two
        assert items[1].suite_name is None

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
        assert items[0].suite_name == "my_suite"

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
        assert items[0].suite_name is None
        assert items[1].suite_name == "my_suite"

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

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        items = [
            TestItem(node_id="mod::Suite::test_a", func=test_a, suite_name="Suite"),
            TestItem(node_id="mod::Suite::test_b", func=test_b, suite_name="Suite"),
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
            TestItem(node_id="mod::test_a", func=test_a, suite_name=None),
            TestItem(node_id="mod::test_b", func=test_b, suite_name=None),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 1
        expected_tests_in_chunk = 2
        assert len(chunks) == expected_chunk_count
        assert len(chunks[0]) == expected_tests_in_chunk

    def test_chunk_alternating_suites(self) -> None:
        """Contiguous tests by suite, not merged if interleaved."""

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        def test_c() -> None:
            pass

        items = [
            TestItem(node_id="mod::A::test_a", func=test_a, suite_name="A"),
            TestItem(node_id="mod::B::test_b", func=test_b, suite_name="B"),
            TestItem(node_id="mod::A::test_c", func=test_c, suite_name="A"),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 3
        assert len(chunks) == expected_chunk_count
        assert chunks[0][0].suite_name == "A"
        assert chunks[1][0].suite_name == "B"
        assert chunks[2][0].suite_name == "A"

    def test_chunk_standalone_then_suite(self) -> None:
        """Standalone tests followed by suite tests create separate chunks."""

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        items = [
            TestItem(node_id="mod::test_a", func=test_a, suite_name=None),
            TestItem(node_id="mod::S::test_b", func=test_b, suite_name="S"),
        ]

        chunks = chunk_by_suite(items)

        expected_chunk_count = 2
        assert len(chunks) == expected_chunk_count
        assert chunks[0][0].suite_name is None
        assert chunks[1][0].suite_name == "S"


class TestGetLastChunkIndexPerSuite:
    """Tests for get_last_chunk_index_per_suite()."""

    def test_empty_chunks(self) -> None:
        """Empty chunks returns empty dict."""
        result = get_last_chunk_index_per_suite([])

        assert result == {}

    def test_single_suite_single_chunk(self) -> None:
        """Single suite in one chunk."""

        def test_a() -> None:
            pass

        chunks = [
            [TestItem(node_id="mod::S::test_a", func=test_a, suite_name="S")],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"S": 0}

    def test_suite_split_across_chunks(self) -> None:
        """Suite appearing in multiple chunks tracks last occurrence."""

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        def test_c() -> None:
            pass

        chunks = [
            [TestItem(node_id="mod::A::test_a", func=test_a, suite_name="A")],
            [TestItem(node_id="mod::B::test_b", func=test_b, suite_name="B")],
            [TestItem(node_id="mod::A::test_c", func=test_c, suite_name="A")],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"A": 2, "B": 1}

    def test_standalone_tests_not_tracked(self) -> None:
        """Standalone tests (suite_name=None) are not tracked."""

        def test_a() -> None:
            pass

        chunks = [
            [TestItem(node_id="mod::test_a", func=test_a, suite_name=None)],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {}

    def test_mixed_standalone_and_suite(self) -> None:
        """Only tracks suites, not standalone tests."""

        def test_a() -> None:
            pass

        def test_b() -> None:
            pass

        chunks = [
            [TestItem(node_id="mod::test_a", func=test_a, suite_name=None)],
            [TestItem(node_id="mod::S::test_b", func=test_b, suite_name="S")],
        ]

        result = get_last_chunk_index_per_suite(chunks)

        assert result == {"S": 1}
