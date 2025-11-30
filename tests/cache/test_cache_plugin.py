"""Tests for CachePlugin - --lf and --cache-clear functionality."""

import json
from pathlib import Path
from typing import Any

import pytest

from protest.cache import plugin as cache_plugin_module
from protest.cache.plugin import CachePlugin
from protest.core.collector import TestItem
from protest.core.session import ProTestSession
from protest.events.data import SessionResult, TestResult


@pytest.fixture
def temp_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override cache dir/file to use temp path."""
    cache_dir = tmp_path / ".protest"
    cache_file = cache_dir / "cache.json"
    monkeypatch.setattr(cache_plugin_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cache_plugin_module, "CACHE_FILE", cache_file)
    return cache_dir


@pytest.fixture
def cache_file(temp_cache_dir: Path) -> Path:
    """Return the cache file path."""
    return temp_cache_dir / "cache.json"


def make_test_item(node_id: str, suite_name: str | None = None) -> TestItem:
    """Create a TestItem with a dummy function."""

    def dummy() -> None:
        pass

    return TestItem(node_id=node_id, func=dummy, suite_name=suite_name)


def write_cache(cache_file: Path, data: dict[str, Any]) -> None:
    """Write cache data to file."""
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(data))


class TestCachePluginRecording:
    """Tests for recording test results."""

    def test_on_test_pass_records_passed(self, temp_cache_dir: Path) -> None:
        """on_test_pass records status=passed."""
        plugin = CachePlugin()
        result = TestResult(name="my_test", node_id="mod::my_test", duration=1.5)

        plugin.on_test_pass(result)

        assert plugin._results["mod::my_test"] == {"status": "passed", "duration": 1.5}

    def test_on_test_fail_records_failed(self, temp_cache_dir: Path) -> None:
        """on_test_fail records status=failed for test failures."""
        plugin = CachePlugin()
        result = TestResult(
            name="my_test",
            node_id="mod::my_test",
            error=AssertionError("oops"),
            duration=0.5,
            is_fixture_error=False,
        )

        plugin.on_test_fail(result)

        assert plugin._results["mod::my_test"] == {"status": "failed", "duration": 0.5}

    def test_on_test_fail_records_error_for_fixture_failure(
        self, temp_cache_dir: Path
    ) -> None:
        """on_test_fail records status=error for fixture errors."""
        plugin = CachePlugin()
        result = TestResult(
            name="my_test",
            node_id="mod::my_test",
            error=RuntimeError("fixture exploded"),
            duration=0.1,
            is_fixture_error=True,
        )

        plugin.on_test_fail(result)

        assert plugin._results["mod::my_test"] == {"status": "error", "duration": 0.1}

    def test_multiple_results_recorded(self, temp_cache_dir: Path) -> None:
        """Multiple test results are all recorded."""
        plugin = CachePlugin()

        plugin.on_test_pass(TestResult(name="a", node_id="mod::a", duration=1.0))
        plugin.on_test_fail(
            TestResult(name="b", node_id="mod::b", error=Exception(), duration=2.0)
        )

        expected_result_count = 2
        assert len(plugin._results) == expected_result_count
        assert plugin._results["mod::a"]["status"] == "passed"
        assert plugin._results["mod::b"]["status"] == "failed"


class TestCachePluginSaveLoad:
    """Tests for cache file save/load operations."""

    def test_save_cache_creates_file(
        self, temp_cache_dir: Path, cache_file: Path
    ) -> None:
        """on_session_end saves results to cache file."""
        plugin = CachePlugin()
        plugin.on_test_pass(TestResult(name="t", node_id="mod::t", duration=1.0))

        plugin.on_session_end(SessionResult(passed=1, failed=0))

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["results"]["mod::t"]["status"] == "passed"
        assert "timestamp" in data
        assert data["version"] == 1

    def test_load_cache_reads_existing(
        self, temp_cache_dir: Path, cache_file: Path
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
        session = ProTestSession()
        plugin = CachePlugin()

        plugin.setup(session)

        results = plugin._cache_data["results"]
        assert results["mod::t"]["status"] == "failed"

    def test_load_cache_handles_missing_file(self, temp_cache_dir: Path) -> None:
        """setup handles missing cache file gracefully."""
        session = ProTestSession()
        plugin = CachePlugin()

        plugin.setup(session)

        assert plugin._cache_data == {}

    def test_load_cache_handles_corrupted_json(
        self, temp_cache_dir: Path, cache_file: Path
    ) -> None:
        """setup handles corrupted JSON gracefully."""
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text("not valid json {{{{")
        session = ProTestSession()
        plugin = CachePlugin()

        plugin.setup(session)

        assert plugin._cache_data == {}


class TestCachePluginClear:
    """Tests for --cache-clear functionality."""

    def test_cache_clear_removes_file(
        self, temp_cache_dir: Path, cache_file: Path
    ) -> None:
        """cache_clear=True removes existing cache file."""
        write_cache(cache_file, {"version": 1, "results": {}})
        session = ProTestSession()
        plugin = CachePlugin(cache_clear=True)

        plugin.setup(session)

        assert not cache_file.exists()

    def test_cache_clear_handles_missing_file(self, temp_cache_dir: Path) -> None:
        """cache_clear=True handles missing file gracefully."""
        session = ProTestSession()
        plugin = CachePlugin(cache_clear=True)

        plugin.setup(session)

        assert plugin._cache_data == {}


class TestCachePluginFiltering:
    """Tests for --lf (last-failed) filtering."""

    def test_filter_returns_only_failed_tests(
        self, temp_cache_dir: Path, cache_file: Path
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
        session = ProTestSession()
        plugin = CachePlugin(last_failed=True)
        plugin.setup(session)

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
        self, temp_cache_dir: Path, cache_file: Path
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
        session = ProTestSession()
        plugin = CachePlugin(last_failed=True)
        plugin.setup(session)

        items = [make_test_item("mod::passing"), make_test_item("mod::new")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count

    def test_filter_returns_all_if_cache_empty(self, temp_cache_dir: Path) -> None:
        """If no cache, return all tests."""
        session = ProTestSession()
        plugin = CachePlugin(last_failed=True)
        plugin.setup(session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count

    def test_no_filter_when_last_failed_false(
        self, temp_cache_dir: Path, cache_file: Path
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
        session = ProTestSession()
        plugin = CachePlugin(last_failed=False)
        plugin.setup(session)

        items = [make_test_item("mod::passing"), make_test_item("mod::failing")]

        filtered = plugin.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count


class TestCachePluginIntegration:
    """Integration tests simulating multiple runs."""

    def test_second_run_with_lf_filters_correctly(
        self, temp_cache_dir: Path, cache_file: Path
    ) -> None:
        """Simulate: first run with failures, second run with --lf."""
        session = ProTestSession()
        plugin_first_run = CachePlugin()
        plugin_first_run.setup(session)

        plugin_first_run.on_test_pass(
            TestResult(name="a", node_id="mod::a", duration=1.0)
        )
        plugin_first_run.on_test_fail(
            TestResult(name="b", node_id="mod::b", error=Exception(), duration=1.0)
        )
        plugin_first_run.on_session_end(SessionResult(passed=1, failed=1))

        plugin_second_run = CachePlugin(last_failed=True)
        plugin_second_run.setup(session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]
        filtered = plugin_second_run.on_collection_finish(items)

        expected_filtered_count = 1
        assert len(filtered) == expected_filtered_count
        assert filtered[0].node_id == "mod::b"

    def test_cache_clear_then_lf_runs_all(
        self, temp_cache_dir: Path, cache_file: Path
    ) -> None:
        """--cache-clear followed by --lf should run all tests."""
        write_cache(
            cache_file,
            {
                "version": 1,
                "results": {"mod::b": {"status": "failed", "duration": 1.0}},
            },
        )

        session = ProTestSession()
        plugin_clear = CachePlugin(cache_clear=True)
        plugin_clear.setup(session)

        plugin_lf = CachePlugin(last_failed=True)
        plugin_lf.setup(session)

        items = [make_test_item("mod::a"), make_test_item("mod::b")]
        filtered = plugin_lf.on_collection_finish(items)

        expected_filtered_count = 2
        assert len(filtered) == expected_filtered_count
