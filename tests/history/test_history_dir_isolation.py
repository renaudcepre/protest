"""Regression tests for B2: tests must not pollute the repo's history file.

The autouse `_isolate_protest_history` fixture in `tests/conftest.py`
monkeypatches `storage.DEFAULT_HISTORY_DIR` to a per-test temp directory.
These tests assert that both the storage functions and the HistoryPlugin
pick up the override - any regression in the plumbing would let runs leak
into `.protest/history.jsonl` in the real project cwd.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from protest.history import storage
from protest.history.plugin import HistoryPlugin

if TYPE_CHECKING:
    from pathlib import Path


class TestDefaultHistoryDirOverride:
    """The autouse fixture redirects the module-level constant."""

    def test_storage_default_points_to_tmp(self, tmp_path: Path) -> None:
        assert tmp_path / ".protest" == storage.DEFAULT_HISTORY_DIR

    def test_append_entry_uses_override(self, tmp_path: Path) -> None:
        target = storage.DEFAULT_HISTORY_DIR / storage.HISTORY_FILE
        storage.append_entry(target, {"k": "v"})
        assert target.exists()
        assert target.is_relative_to(tmp_path)

    def test_plugin_default_dir_follows_override(self, tmp_path: Path) -> None:
        plugin = HistoryPlugin()
        assert plugin._history_dir == tmp_path / ".protest"
        assert plugin._history_file.is_relative_to(tmp_path)


class TestExplicitHistoryDirWins:
    """Explicit `history_dir=` still takes precedence over the override."""

    def test_plugin_honors_explicit_dir(self, tmp_path: Path) -> None:
        explicit = tmp_path / "custom"
        plugin = HistoryPlugin(history_dir=explicit)
        assert plugin._history_dir == explicit
