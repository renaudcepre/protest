"""JSONL history storage: load, append, filter, clean."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_HISTORY_DIR = Path(".protest")
HISTORY_FILE = "history.jsonl"


def load_history(
    history_dir: Path | None = None,
    n: int | None = None,
    model: str | None = None,
    suite: str | None = None,
    evals_only: bool = False,
    tests_only: bool = False,
) -> list[dict[str, Any]]:
    """Load history entries with optional filtering."""
    path = (history_dir or DEFAULT_HISTORY_DIR) / HISTORY_FILE
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in path.read_text().strip().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evals_only and not _has_suite_kind(entry, "eval"):
            continue
        if tests_only and not _has_suite_kind(entry, "test"):
            continue
        if model and (entry.get("evals") or {}).get("model") != model:
            continue
        if suite and suite not in entry.get("suites", {}):
            continue
        entries.append(entry)

    entries.sort(key=lambda e: e.get("timestamp", ""))
    if n is not None:
        entries = entries[-n:]
    return entries


def _has_suite_kind(entry: dict[str, Any], kind: str) -> bool:
    """Check if entry has at least one suite with the given kind."""
    suites = entry.get("suites", {})
    for suite_data in suites.values():
        if isinstance(suite_data, dict) and suite_data.get("kind") == kind:
            return True
    # Legacy fallback: entries without kind field
    if not any(isinstance(s, dict) and "kind" in s for s in suites.values()):
        if kind == "eval":
            return entry.get("evals") is not None
        if kind == "test":
            return entry.get("evals") is None
    return False


def append_entry(path: Path, entry: dict[str, Any]) -> None:
    """Append a single JSON entry to a JSONL file.

    Note: no file locking — concurrent writes from separate processes
    could corrupt the file. In practice, protest runs are single-process
    (async workers share the same process). If concurrent CI jobs write
    to the same history file, consider using separate history_dir per job.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def load_previous_run(
    history_dir: Path | None = None,
    evals_only: bool = False,
) -> dict[str, Any] | None:
    """Load the most recent history entry."""
    path = (history_dir or DEFAULT_HISTORY_DIR) / HISTORY_FILE
    if not path.exists():
        return None
    lines = path.read_text().strip().splitlines()
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evals_only and entry.get("evals") is None:
            continue
        return dict(entry)
    return None


def clean_dirty(history_dir: Path | None = None) -> int:
    """Remove entries where git.dirty=True AND git.commit matches current HEAD.

    Returns the number of entries removed.
    """
    path = (history_dir or DEFAULT_HISTORY_DIR) / HISTORY_FILE
    if not path.exists():
        return 0

    try:
        current_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 0

    lines = path.read_text().strip().splitlines()
    kept: list[str] = []
    removed = 0

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        git = entry.get("git") or {}
        if git.get("dirty") and git.get("commit") == current_commit:
            removed += 1
        else:
            kept.append(line)

    if removed:
        path.write_text("\n".join(kept) + "\n" if kept else "")
    return removed
