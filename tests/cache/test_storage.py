from __future__ import annotations

import json
from pathlib import Path

import pytest

from protest.cache.storage import CacheStorage, TestCacheEntry


@pytest.fixture
def storage(tmp_path: Path) -> CacheStorage:
    """Create a CacheStorage with a temporary directory."""
    return CacheStorage(cache_dir=tmp_path / ".protest", cache_file="cache.json")


@pytest.fixture
def cache_file(storage: CacheStorage) -> Path:
    return storage.cache_file


class TestCacheStorageBasics:
    @pytest.mark.parametrize(
        "cache_dir,cache_file_name,expected_dir,expected_file_suffix",
        [
            pytest.param(None, None, ".protest", "cache.json", id="defaults"),
        ],
    )
    def test_default_paths(
        self,
        cache_dir: Path | None,
        cache_file_name: str | None,
        expected_dir: str,
        expected_file_suffix: str,
    ) -> None:
        """Given default constructor, when storage created, then paths use defaults."""
        storage = CacheStorage()

        assert storage.cache_dir == Path(expected_dir)
        assert storage.cache_file == Path(expected_dir) / expected_file_suffix

    def test_custom_paths(self, tmp_path: Path) -> None:
        """Given custom paths, when storage created, then custom paths are used."""
        custom_dir = tmp_path / "custom"
        custom_file = "data.json"

        storage = CacheStorage(cache_dir=custom_dir, cache_file=custom_file)

        assert storage.cache_dir == custom_dir
        assert storage.cache_file == custom_dir / custom_file


class TestCacheStorageSetGet:
    def test_set_and_get_result(self, storage: CacheStorage) -> None:
        """Given a result is set, when retrieved, then correct entry is returned."""
        node_id = "test::one"
        expected_status = "passed"
        expected_duration = 1.5

        storage.set_result(node_id, expected_status, expected_duration)
        entry = storage.get_result(node_id)

        assert entry is not None
        assert entry.status == expected_status
        assert entry.duration == expected_duration

    def test_get_nonexistent_result(self, storage: CacheStorage) -> None:
        """Given no result exists, when retrieved, then None is returned."""
        result = storage.get_result("nonexistent")

        assert result is None

    def test_get_results_returns_copy(self, storage: CacheStorage) -> None:
        """Given results exist, when get_results called, then modifying copy doesn't affect storage."""
        storage.set_result("test::one", "passed", 1.0)

        results = storage.get_results()
        results["test::modified"] = TestCacheEntry(status="x", duration=0.0)

        assert "test::modified" not in storage.get_results()

    def test_get_durations(self, storage: CacheStorage) -> None:
        """Given multiple results, when get_durations called, then dict of node_id to duration returned."""
        storage.set_result("test::fast", "passed", 0.1)
        storage.set_result("test::slow", "passed", 5.0)
        expected_durations = {"test::fast": 0.1, "test::slow": 5.0}

        durations = storage.get_durations()

        assert durations == expected_durations

    @pytest.mark.parametrize(
        "statuses,expected_failed",
        [
            pytest.param(
                [
                    ("test::pass", "passed"),
                    ("test::fail", "failed"),
                    ("test::error", "error"),
                ],
                {"test::fail", "test::error"},
                id="mixed_statuses",
            ),
        ],
    )
    def test_get_failed_node_ids(
        self,
        storage: CacheStorage,
        statuses: list[tuple[str, str]],
        expected_failed: set[str],
    ) -> None:
        """Given results with different statuses, when get_failed_node_ids called, then failed/error returned."""
        for node_id, status in statuses:
            storage.set_result(node_id, status, 1.0)

        failed = storage.get_failed_node_ids()

        assert failed == expected_failed

    def test_get_passed_node_ids(self, storage: CacheStorage) -> None:
        """Given results with different statuses, when get_passed_node_ids called, then only passed returned."""
        storage.set_result("test::pass1", "passed", 1.0)
        storage.set_result("test::pass2", "passed", 1.0)
        storage.set_result("test::fail", "failed", 1.0)
        expected_passed = {"test::pass1", "test::pass2"}

        passed = storage.get_passed_node_ids()

        assert passed == expected_passed


class TestCacheStorageSaveLoad:
    def test_save_creates_directory_and_file(
        self, storage: CacheStorage, cache_file: Path
    ) -> None:
        """Given results in storage, when save called, then file created with correct structure."""
        storage.set_result("test::one", "passed", 1.0)

        storage.save()

        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["version"] == 1
        assert "timestamp" in data
        assert data["results"]["test::one"]["status"] == "passed"

    def test_load_reads_existing_file(
        self, storage: CacheStorage, cache_file: Path
    ) -> None:
        """Given existing cache file, when load called, then data is restored."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "version": 1,
            "timestamp": 123,
            "results": {"test::one": {"status": "failed", "duration": 2.5}},
        }
        cache_file.write_text(json.dumps(cache_data))

        storage.load()
        entry = storage.get_result("test::one")

        assert entry is not None
        assert entry.status == "failed"
        assert entry.duration == 2.5

    @pytest.mark.parametrize(
        "file_content,scenario",
        [
            pytest.param(None, "missing_file", id="missing_file"),
            pytest.param("not valid json", "corrupted_json", id="corrupted_json"),
            pytest.param(
                '{"version": 1, "results": "invalid"}',
                "invalid_format",
                id="invalid_format",
            ),
        ],
    )
    def test_load_handles_error_cases(
        self,
        storage: CacheStorage,
        cache_file: Path,
        file_content: str | None,
        scenario: str,
    ) -> None:
        """Given invalid/missing cache file, when load called, then storage is empty (graceful degradation)."""
        if file_content is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(file_content)

        storage.load()

        assert storage.get_results() == {}


class TestCacheStorageClear:
    def test_clear_removes_file(self, storage: CacheStorage, cache_file: Path) -> None:
        """Given existing cache file, when clear called, then file is deleted."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"version": 1, "results": {}}))

        storage.clear()

        assert not cache_file.exists()

    def test_clear_resets_in_memory_data(self, storage: CacheStorage) -> None:
        """Given in-memory results, when clear called, then results are empty."""
        storage.set_result("test::one", "passed", 1.0)

        storage.clear()

        assert storage.get_results() == {}
        assert storage.get_result("test::one") is None

    def test_clear_handles_missing_file(self, storage: CacheStorage) -> None:
        """Given no cache file exists, when clear called, then no error and results empty."""
        storage.clear()

        assert storage.get_results() == {}


class TestCacheStorageRoundTrip:
    def test_save_then_load_preserves_data(self, tmp_path: Path) -> None:
        """Given results saved to file, when loaded in new storage, then data preserved."""
        storage1 = CacheStorage(cache_dir=tmp_path / ".protest")
        storage1.set_result("test::a", "passed", 1.0)
        storage1.set_result("test::b", "failed", 2.0)
        storage1.set_result("test::c", "error", 3.0)
        storage1.save()

        storage2 = CacheStorage(cache_dir=tmp_path / ".protest")
        storage2.load()

        assert storage2.get_result("test::a") == TestCacheEntry("passed", 1.0)
        assert storage2.get_result("test::b") == TestCacheEntry("failed", 2.0)
        assert storage2.get_result("test::c") == TestCacheEntry("error", 3.0)
