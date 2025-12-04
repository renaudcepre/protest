"""Shared cache storage for inter-plugin data sharing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestCacheEntry:
    status: str
    duration: float


class CacheStorage:
    """Shared cache storage accessible via session.cache.

    Provides a clean API for plugins to read/write cached test data
    without direct file dependencies.

    Example:
        # In a plugin
        def setup(self, session: ProTestSession) -> None:
            results = session.cache.get_results()
            durations = session.cache.get_durations()

        def on_test_pass(self, result: TestResult) -> None:
            session.cache.set_result(result.node_id, "passed", result.duration)
    """

    DEFAULT_DIR = Path(".protest")
    DEFAULT_FILE = "cache.json"

    def __init__(
        self, cache_dir: Path | None = None, cache_file: str | None = None
    ) -> None:
        self._cache_dir = cache_dir or self.DEFAULT_DIR
        self._cache_file = self._cache_dir / (cache_file or self.DEFAULT_FILE)
        self._data: dict[str, Any] = {}
        self._results: dict[str, TestCacheEntry] = {}
        self._dirty = False

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def cache_file(self) -> Path:
        return self._cache_file

    def load(self) -> None:
        """Load cache from disk."""
        if self._cache_file.exists():
            try:
                raw_data = json.loads(self._cache_file.read_text())
                self._data = raw_data
                self._load_results_from_data(raw_data)
            except json.JSONDecodeError:
                self._data = {}
                self._results = {}

    def _load_results_from_data(self, data: dict[str, Any]) -> None:
        raw_results = data.get("results", {})
        if not isinstance(raw_results, dict):
            self._results = {}
            return
        self._results = {}
        for node_id, entry in raw_results.items():
            if isinstance(entry, dict):
                self._results[node_id] = TestCacheEntry(
                    status=entry.get("status", "unknown"),
                    duration=float(entry.get("duration", 0.0)),
                )

    def save(self) -> None:
        """Save cache to disk."""
        self._cache_dir.mkdir(exist_ok=True)
        results_dict = {
            node_id: {"status": entry.status, "duration": entry.duration}
            for node_id, entry in self._results.items()
        }
        data = {
            "version": 1,
            "timestamp": time.time(),
            "results": results_dict,
        }
        self._cache_file.write_text(json.dumps(data, indent=2))
        self._dirty = False

    def clear(self) -> None:
        """Clear all cached data."""
        if self._cache_file.exists():
            self._cache_file.unlink()
        self._data = {}
        self._results = {}
        self._dirty = False

    def get_results(self) -> dict[str, TestCacheEntry]:
        """Get all cached test results."""
        return dict(self._results)

    def get_result(self, node_id: str) -> TestCacheEntry | None:
        """Get cached result for a specific test."""
        return self._results.get(node_id)

    def set_result(self, node_id: str, status: str, duration: float) -> None:
        """Set a test result in the cache."""
        self._results[node_id] = TestCacheEntry(status=status, duration=duration)
        self._dirty = True

    def get_durations(self) -> dict[str, float]:
        """Get all cached test durations (useful for duration-based ordering)."""
        return {node_id: entry.duration for node_id, entry in self._results.items()}

    def get_failed_node_ids(self) -> set[str]:
        """Get node IDs of tests that failed in the last run."""
        return {
            node_id
            for node_id, entry in self._results.items()
            if entry.status in ("failed", "error")
        }

    def get_passed_node_ids(self) -> set[str]:
        """Get node IDs of tests that passed in the last run."""
        return {
            node_id
            for node_id, entry in self._results.items()
            if entry.status == "passed"
        }
