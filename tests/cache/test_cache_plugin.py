from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from protest.cache.plugin import CachePlugin
from protest.cache.storage import CacheStorage
from protest.core.session import ProTestSession
from protest.entities import SessionResult, TestResult
from tests.factories.test_items import make_test_item_from_node_id as make_test_item

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def temp_session(tmp_path: Path) -> ProTestSession:
    """Create a session with a temporary cache directory."""
    session = ProTestSession()
    session._cache_storage = CacheStorage(
        cache_dir=tmp_path / ".protest", cache_file="cache.json"
    )
    return session


@pytest.fixture
def cache_file(temp_session: ProTestSession) -> Path:
    """Return the cache file path."""
    return temp_session.cache.cache_file


def write_cache(cache_file: Path, data: dict[str, Any]) -> None:
    """Write cache data to file."""
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(data))


class TestCachePluginRecording:
    """Tests for recording test results via session.cache."""

    def test_on_test_pass_records_passed(self, temp_session: ProTestSession) -> None:
        """on_test_pass records status=passed via session.cache."""
        plugin = CachePlugin()
        plugin.setup(temp_session)
        result = TestResult(name="my_test", node_id="mod::my_test", duration=1.5)

        plugin.on_test_pass(result)

        entry = temp_session.cache.get_result("mod::my_test")
        assert entry is not None
        assert entry.status == "passed"
        assert entry.duration == 1.5

    def test_on_test_fail_records_failed(self, temp_session: ProTestSession) -> None:
        """on_test_fail records status=failed for test failures."""
        plugin = CachePlugin()
        plugin.setup(temp_session)
        result = TestResult(
            name="my_test",
            node_id="mod::my_test",
            error=AssertionError("oops"),
            duration=0.5,
            is_fixture_error=False,
        )

        plugin.on_test_fail(result)

        entry = temp_session.cache.get_result("mod::my_test")
        assert entry is not None
        assert entry.status == "failed"
        assert entry.duration == 0.5

    def test_on_test_fail_records_error_for_fixture_failure(
        self, temp_session: ProTestSession
    ) -> None:
        """on_test_fail records status=error for fixture errors."""

        plugin = CachePlugin()
        plugin.setup(temp_session)
        result = TestResult(
            name="my_test",
            node_id="mod::my_test",
            error=RuntimeError("fixture exploded"),
            duration=0.1,
            is_fixture_error=True,
        )

        plugin.on_test_fail(result)

        entry = temp_session.cache.get_result("mod::my_test")
        assert entry is not None
        assert entry.status == "error"
        assert entry.duration == 0.1

    def test_multiple_results_recorded(self, temp_session: ProTestSession) -> None:
        """Multiple test results are all recorded."""

        plugin = CachePlugin()
        plugin.setup(temp_session)

        plugin.on_test_pass(TestResult(name="a", node_id="mod::a", duration=1.0))
        plugin.on_test_fail(
            TestResult(name="b", node_id="mod::b", error=Exception(), duration=2.0)
        )

        results = temp_session.cache.get_results()
        expected_result_count = 2
        assert len(results) == expected_result_count
        assert results["mod::a"].status == "passed"
        assert results["mod::b"].status == "failed"


class TestCachePluginSaveLoad:
    """Tests for cache file save/load operations."""

    def test_save_cache_creates_file(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """on_session_end saves results to cache file."""

        plugin = CachePlugin()
        plugin.setup(temp_session)
        plugin.on_test_pass(TestResult(name="t", node_id="mod::t", duration=1.0))

        plugin.on_session_end(SessionResult(passed=1, failed=0))

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["results"]["mod::t"]["status"] == "passed"
        assert "timestamp" in data
        assert data["version"] == 1

    def test_load_cache_reads_existing(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """setup loads existing cache data."""

        write_cache(
            cache_file,
            {
                "version": 1,
                "timestamp": 123,
                "results": {"mod::t": {"status": "failed", "duration": 1.0}},
            },
        )
        plugin = CachePlugin()

        plugin.setup(temp_session)

        entry = temp_session.cache.get_result("mod::t")
        assert entry is not None
        assert entry.status == "failed"

    def test_load_cache_handles_missing_file(
        self, temp_session: ProTestSession
    ) -> None:
        """setup handles missing cache file gracefully."""

        plugin = CachePlugin()

        plugin.setup(temp_session)

        assert temp_session.cache.get_results() == {}

    def test_load_cache_handles_corrupted_json(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """setup handles corrupted JSON gracefully."""

        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text("not valid json {{{{")
        plugin = CachePlugin()

        plugin.setup(temp_session)

        assert temp_session.cache.get_results() == {}


class TestCachePluginClear:
    """Tests for --cache-clear functionality."""

    def test_cache_clear_removes_file(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """cache_clear=True removes existing cache file."""

        write_cache(cache_file, {"version": 1, "results": {}})
        plugin = CachePlugin(cache_clear=True)

        plugin.setup(temp_session)

        assert not cache_file.exists()

    def test_cache_clear_handles_missing_file(
        self, temp_session: ProTestSession
    ) -> None:
        """cache_clear=True handles missing file gracefully."""

        plugin = CachePlugin(cache_clear=True)

        plugin.setup(temp_session)

        assert temp_session.cache.get_results() == {}


class TestCachePluginFiltering:
    """Tests for --lf (last-failed) filtering."""

    def test_filter_returns_only_failed_tests(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """on_collection_finish returns only previously failed tests."""

        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {
                    "mod::passing": {"status": "passed", "duration": 1.0},
                    "mod::failing": {"status": "failed", "duration": 1.0},
                    "mod::erroring": {"status": "error", "duration": 1.0},
                },
            },
        )
        plugin = CachePlugin(last_failed=True)
        plugin.setup(temp_session)

        items = [
            make_test_item("mod::passing"),
            make_test_item("mod::failing"),
            make_test_item("mod::erroring"),
            make_test_item("mod::new_test"),
        ]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count
        filtered_ids = {item.node_id for item in filtered}
        assert filtered_ids == {"mod::failing", "mod::erroring"}

    def test_filter_returns_all_if_no_failures_in_cache(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """If cache has no failures, return all tests as fallback."""

        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {
                    "mod::passing": {"status": "passed", "duration": 1.0},
                },
            },
        )
        plugin = CachePlugin(last_failed=True)
        plugin.setup(temp_session)

        items = [make_test_item("mod::passing"), make_test_item("mod::new")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count

    def test_filter_returns_empty_if_failures_exist_but_no_match(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """If cache has failures but no items match, return empty list (no fallback)."""
        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {
                    "mod::old_failing": {"status": "failed", "duration": 1.0},
                },
            },
        )
        plugin = CachePlugin(last_failed=True)
        plugin.setup(temp_session)

        items = [make_test_item("mod::new_test"), make_test_item("mod::another_new")]

        filtered = plugin.on_collection_finish(items)

        assert filtered == []

    def test_filter_returns_all_if_cache_empty(
        self, temp_session: ProTestSession
    ) -> None:
        """If no cache, return all tests."""

        plugin = CachePlugin(last_failed=True)
        plugin.setup(temp_session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count

    def test_no_filter_when_last_failed_false(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """Without --lf, on_collection_finish returns all tests."""

        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {
                    "mod::failing": {"status": "failed", "duration": 1.0},
                },
            },
        )
        plugin = CachePlugin(last_failed=False)
        plugin.setup(temp_session)

        items = [make_test_item("mod::passing"), make_test_item("mod::failing")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count

    def test_filter_without_setup_raises_error(self) -> None:
        """Calling _filter_last_failed without setup() raises RuntimeError."""
        plugin = CachePlugin(last_failed=True)
        # Note: setup() NOT called, so _cache is None

        items = [make_test_item("mod::test")]

        with pytest.raises(RuntimeError, match="CachePlugin improperly configured"):
            plugin._filter_last_failed(items)


class TestCachePluginIntegration:
    """Integration tests simulating multiple runs."""

    def test_second_run_with_lf_filters_correctly(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """Simulate: first run with failures, second run with --lf."""

        plugin_first_run = CachePlugin()
        plugin_first_run.setup(temp_session)

        plugin_first_run.on_test_pass(
            TestResult(name="a", node_id="mod::a", duration=1.0)
        )
        plugin_first_run.on_test_fail(
            TestResult(name="b", node_id="mod::b", error=Exception(), duration=1.0)
        )
        plugin_first_run.on_session_end(SessionResult(passed=1, failed=1))

        plugin_second_run = CachePlugin(last_failed=True)
        plugin_second_run.setup(temp_session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]
        filtered = plugin_second_run.on_collection_finish(items)

        expected_filtered_count = 1
        assert len(filtered) == expected_filtered_count
        assert filtered[0].node_id == "mod::b"

    def test_cache_clear_then_lf_runs_all(
        self, temp_session: ProTestSession, cache_file: Path
    ) -> None:
        """--cache-clear followed by --lf should run all tests."""

        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {"mod::b": {"status": "failed", "duration": 1.0}},
            },
        )

        plugin_clear = CachePlugin(cache_clear=True)
        plugin_clear.setup(temp_session)

        plugin_lf = CachePlugin(last_failed=True)
        plugin_lf.setup(temp_session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]
        filtered = plugin_lf.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count
