"""Tests for `schema_version` on history JSONL entries.

The plugin stamps every new entry with `schema_version`. Readers skip
entries with a future version (written by a newer protest) and warn once
per version.

Legacy entries (no `schema_version` key at all — written before this was
introduced) are treated as version 0 and read without warning.
"""

from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING

from protest.history import storage
from protest.history.plugin import HistoryPlugin

if TYPE_CHECKING:
    from pathlib import Path


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


class TestSchemaVersionWrites:
    def test_append_entry_writes_schema_version_via_plugin(self) -> None:
        """HistoryPlugin stamps `schema_version` on every new entry."""
        plugin = HistoryPlugin()
        assert storage.SCHEMA_VERSION >= 1

        entry_with_version = {"schema_version": storage.SCHEMA_VERSION, "k": "v"}
        storage.append_entry(plugin._history_file, entry_with_version)
        loaded = json.loads(plugin._history_file.read_text().splitlines()[0])
        assert loaded["schema_version"] == storage.SCHEMA_VERSION


class TestFutureVersionSkipped:
    def test_future_version_is_skipped_by_load_history(self, tmp_path: Path) -> None:
        path = tmp_path / ".protest" / storage.HISTORY_FILE
        _write_jsonl(
            path,
            [
                {"schema_version": storage.SCHEMA_VERSION, "run_id": "current"},
                {"schema_version": storage.SCHEMA_VERSION + 10, "run_id": "future"},
            ],
        )
        storage._warned_future_versions.clear()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            entries = storage.load_history(history_dir=tmp_path / ".protest")
        run_ids = [e["run_id"] for e in entries]
        assert run_ids == ["current"]

    def test_future_version_is_skipped_by_load_previous_run(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / ".protest" / storage.HISTORY_FILE
        _write_jsonl(
            path,
            [
                {"schema_version": storage.SCHEMA_VERSION, "run_id": "older"},
                {"schema_version": storage.SCHEMA_VERSION + 1, "run_id": "newer"},
            ],
        )
        storage._warned_future_versions.clear()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            entry = storage.load_previous_run(history_dir=tmp_path / ".protest")
        assert entry is not None
        assert entry["run_id"] == "older"

    def test_warning_raised_once_per_future_version(self, tmp_path: Path) -> None:
        path = tmp_path / ".protest" / storage.HISTORY_FILE
        future = storage.SCHEMA_VERSION + 42
        _write_jsonl(
            path,
            [{"schema_version": future, "run_id": str(i)} for i in range(5)],
        )
        storage._warned_future_versions.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            storage.load_history(history_dir=tmp_path / ".protest")
        future_warnings = [
            w for w in caught if f"schema_version={future}" in str(w.message)
        ]
        assert len(future_warnings) == 1


class TestLegacyEntriesStillReadable:
    """Pre-schema_version entries have no key — treat as legacy (version 0)."""

    def test_entry_without_schema_version_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / ".protest" / storage.HISTORY_FILE
        _write_jsonl(path, [{"run_id": "legacy", "suites": {}}])
        storage._warned_future_versions.clear()
        entries = storage.load_history(history_dir=tmp_path / ".protest")
        assert len(entries) == 1
        assert entries[0]["run_id"] == "legacy"

    def test_entry_with_version_zero_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / ".protest" / storage.HISTORY_FILE
        _write_jsonl(path, [{"schema_version": 0, "run_id": "v0"}])
        storage._warned_future_versions.clear()
        entries = storage.load_history(history_dir=tmp_path / ".protest")
        assert len(entries) == 1
