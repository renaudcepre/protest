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
    def test_default_paths(self) -> None:
        storage = CacheStorage()
        assert storage.cache_dir == Path(".protest")
        assert storage.cache_file == Path(".protest/cache.json")

    def test_custom_paths(self, tmp_path: Path) -> None:
        storage = CacheStorage(cache_dir=tmp_path / "custom", cache_file="data.json")
        assert storage.cache_dir == tmp_path / "custom"
        assert storage.cache_file == tmp_path / "custom" / "data.json"


class TestCacheStorageSetGet:
    def test_set_and_get_result(self, storage: CacheStorage) -> None:
        storage.set_result("test::one", "passed", 1.5)

        entry = storage.get_result("test::one")
        assert entry is not None
        assert entry.status == "passed"
        assert entry.duration == 1.5

    def test_get_nonexistent_result(self, storage: CacheStorage) -> None:
        assert storage.get_result("nonexistent") is None

    def test_get_results_returns_copy(self, storage: CacheStorage) -> None:
        storage.set_result("test::one", "passed", 1.0)
        results = storage.get_results()
        results["test::modified"] = TestCacheEntry(status="x", duration=0.0)

        assert "test::modified" not in storage.get_results()

    def test_get_durations(self, storage: CacheStorage) -> None:
        storage.set_result("test::fast", "passed", 0.1)
        storage.set_result("test::slow", "passed", 5.0)

        durations = storage.get_durations()
        assert durations == {"test::fast": 0.1, "test::slow": 5.0}

    def test_get_failed_node_ids(self, storage: CacheStorage) -> None:
        storage.set_result("test::pass", "passed", 1.0)
        storage.set_result("test::fail", "failed", 1.0)
        storage.set_result("test::error", "error", 1.0)

        failed = storage.get_failed_node_ids()
        assert failed == {"test::fail", "test::error"}

    def test_get_passed_node_ids(self, storage: CacheStorage) -> None:
        storage.set_result("test::pass1", "passed", 1.0)
        storage.set_result("test::pass2", "passed", 1.0)
        storage.set_result("test::fail", "failed", 1.0)

        passed = storage.get_passed_node_ids()
        assert passed == {"test::pass1", "test::pass2"}


class TestCacheStorageSaveLoad:
    def test_save_creates_directory_and_file(
        self, storage: CacheStorage, cache_file: Path
    ) -> None:
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
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "timestamp": 123,
                    "results": {"test::one": {"status": "failed", "duration": 2.5}},
                }
            )
        )

        storage.load()

        entry = storage.get_result("test::one")
        assert entry is not None
        assert entry.status == "failed"
        assert entry.duration == 2.5

    def test_load_handles_missing_file(self, storage: CacheStorage) -> None:
        storage.load()

        assert storage.get_results() == {}

    def test_load_handles_corrupted_json(
        self, storage: CacheStorage, cache_file: Path
    ) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("not valid json")

        storage.load()

        assert storage.get_results() == {}

    def test_load_handles_invalid_results_format(
        self, storage: CacheStorage, cache_file: Path
    ) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"version": 1, "results": "invalid"}))

        storage.load()

        assert storage.get_results() == {}


class TestCacheStorageClear:
    def test_clear_removes_file(self, storage: CacheStorage, cache_file: Path) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"version": 1, "results": {}}))

        storage.clear()

        assert not cache_file.exists()

    def test_clear_resets_in_memory_data(self, storage: CacheStorage) -> None:
        storage.set_result("test::one", "passed", 1.0)

        storage.clear()

        assert storage.get_results() == {}
        assert storage.get_result("test::one") is None

    def test_clear_handles_missing_file(self, storage: CacheStorage) -> None:
        storage.clear()
        assert storage.get_results() == {}


class TestCacheStorageRoundTrip:
    def test_save_then_load_preserves_data(self, tmp_path: Path) -> None:
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
