"""Cache plugin for --lf (last-failed) and --cache-clear functionality."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.core.collector import TestItem
    from protest.core.session import ProTestSession
    from protest.events.data import SessionResult, TestResult

CACHE_DIR = Path(".protest")
CACHE_FILE = CACHE_DIR / "cache.json"


class CachePlugin(PluginBase):
    """Plugin that caches test results and provides --lf filtering."""

    def __init__(self, last_failed: bool = False, cache_clear: bool = False) -> None:
        self._last_failed = last_failed
        self._cache_clear = cache_clear
        self._results: dict[str, dict[str, float | str]] = {}
        self._cache_data: dict[str, Any] = {}

    def setup(self, session: ProTestSession) -> None:
        if self._cache_clear:
            self._clear_cache()
        else:
            self._load_cache()

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        """Filter tests based on --lf flag."""
        if self._last_failed:
            return self._filter_last_failed(items)
        return items

    def on_test_pass(self, result: TestResult) -> None:
        self._results[result.node_id] = {
            "status": "passed",
            "duration": result.duration or 0,
        }

    def on_test_fail(self, result: TestResult) -> None:
        status = "error" if result.is_fixture_error else "failed"
        self._results[result.node_id] = {
            "status": status,
            "duration": result.duration or 0,
        }

    def on_session_end(self, result: SessionResult) -> None:
        self._save_cache()

    def _filter_last_failed(self, items: list[TestItem]) -> list[TestItem]:
        """Keep only tests that failed in the last run."""
        results = self._cache_data.get("results", {})
        if not isinstance(results, dict):
            return items
        failed_ids = {
            node_id
            for node_id, result in results.items()
            if isinstance(result, dict) and result.get("status") in ("failed", "error")
        }
        filtered = [item for item in items if item.node_id in failed_ids]
        return filtered if filtered else items

    def _load_cache(self) -> None:
        if CACHE_FILE.exists():
            try:
                self._cache_data = json.loads(CACHE_FILE.read_text())
            except json.JSONDecodeError:
                self._cache_data = {}

    def _save_cache(self) -> None:
        CACHE_DIR.mkdir(exist_ok=True)
        data = {
            "version": 1,
            "timestamp": time.time(),
            "results": self._results,
        }
        CACHE_FILE.write_text(json.dumps(data, indent=2))

    def _clear_cache(self) -> None:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        self._cache_data = {}
