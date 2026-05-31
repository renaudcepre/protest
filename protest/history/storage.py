"""JSONL history storage: load, append, filter, clean."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import warnings
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

if sys.platform == "win32":
    import msvcrt

    @contextlib.contextmanager
    def _exclusive_file_lock(f: IO[Any]) -> Iterator[None]:
        """Hold an exclusive advisory lock on `f` for the block's duration.

        Windows `msvcrt.locking` cannot lock regions beyond EOF, so we lock
        a sibling `<path>.lock` file that we ensure always has 1 byte. All
        writers cooperate on this sibling, so concurrent appends to the
        main file are serialized.
        """
        lock_path = Path(f"{f.name}.lock")
        with open(lock_path, "a+b") as lf:
            lf.seek(0, 2)
            if lf.tell() == 0:
                lf.write(b"\0")
                lf.flush()
            lf.seek(0)
            msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lf.seek(0)
                msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    @contextlib.contextmanager
    def _exclusive_file_lock(f: IO[Any]) -> Iterator[None]:
        """Hold an exclusive advisory lock on `f` for the block's duration.

        POSIX `fcntl.flock` locks the file descriptor directly; cross-process
        callers opening the same path will block until the lock is released.
        """
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


DEFAULT_HISTORY_DIR = Path(".protest")
HISTORY_FILE = "history.jsonl"

# JSONL entry schema version. Bump when the on-disk shape changes in a way
# that older readers can't transparently handle (new required fields,
# restructured nesting). Entries written before this was introduced have no
# `schema_version` key and are treated as version 0 (legacy — best-effort).
SCHEMA_VERSION = 1

_warned_future_versions: set[int] = set()


def _is_future_schema(entry: dict[str, Any]) -> bool:
    """Return True if the entry was written by a newer protest version.

    Entries with `schema_version > SCHEMA_VERSION` are skipped by readers,
    with a one-time warning per version (avoids N warnings for N such
    entries).
    """
    version = entry.get("schema_version", 0)
    if not isinstance(version, int) or version <= SCHEMA_VERSION:
        return False
    if version not in _warned_future_versions:
        _warned_future_versions.add(version)
        warnings.warn(
            f"history.jsonl contains entries with schema_version={version}, "
            f"but this protest supports up to {SCHEMA_VERSION}. "
            f"Those entries will be skipped. Upgrade protest to read them.",
            stacklevel=3,
        )
    return True


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
        filtered = _apply_entry_filters(
            entry,
            evals_only=evals_only,
            tests_only=tests_only,
            model=model,
            suite=suite,
        )
        if filtered is not None:
            entries.append(filtered)

    entries.sort(key=lambda e: e.get("timestamp", ""))
    if n is not None:
        entries = entries[-n:]
    return entries


def _apply_entry_filters(
    entry: dict[str, Any],
    *,
    evals_only: bool,
    tests_only: bool,
    model: str | None,
    suite: str | None,
) -> dict[str, Any] | None:
    """Apply CLI filters to a single history entry.

    Returns the (possibly suite-pruned) entry to keep, or None to drop it.
    `--model` / `--suite` operate at the suite level: any suite in the run
    that matches keeps the entry alive, with non-matching suites pruned out.
    """
    if _is_future_schema(entry):
        return None
    if evals_only and not _has_suite_kind(entry, "eval"):
        return None
    if tests_only and not _has_suite_kind(entry, "test"):
        return None
    if model is None and suite is None:
        return entry

    kept_suites: dict[str, Any] = {}
    for sname, sdata in entry.get("suites", {}).items():
        if not isinstance(sdata, dict):
            continue
        if model is not None and sdata.get("model") != model:
            continue
        if suite is not None and sname != suite:
            continue
        kept_suites[sname] = sdata
    if not kept_suites:
        return None
    return {**entry, "suites": kept_suites}


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

    Serializes concurrent writes from separate processes sharing the same
    history file (e.g. a CI matrix) via an exclusive advisory lock:
    `fcntl.flock` on POSIX, `msvcrt.locking` on a sibling `<path>.lock`
    file on Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, default=str) + "\n"
    with open(path, "a") as f, _exclusive_file_lock(f):
        f.write(line)
        f.flush()


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
        if _is_future_schema(entry):
            continue
        if evals_only and entry.get("evals") is None:
            continue
        return dict(entry)
    return None


def _current_git_head() -> str | None:
    """Return the current HEAD short SHA, or None when not in a git repo."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def is_dirty_entry(entry: dict[str, Any], current_commit: str | None) -> bool:
    """Return True if `entry` was produced on a dirty working tree at HEAD."""
    if not current_commit:
        return False
    git = entry.get("git") or {}
    return bool(git.get("dirty")) and git.get("commit") == current_commit


def count_dirty_entries(history_dir: Path | None = None) -> int:
    """Count entries `clean_dirty()` would remove (without touching the file)."""
    path = (history_dir or DEFAULT_HISTORY_DIR) / HISTORY_FILE
    if not path.exists():
        return 0
    current_commit = _current_git_head()
    if not current_commit:
        return 0
    count = 0
    for line in path.read_text().strip().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_dirty_entry(entry, current_commit):
            count += 1
    return count


def clean_dirty(history_dir: Path | None = None) -> int:
    """Remove entries where git.dirty=True AND git.commit matches current HEAD.

    Returns the number of entries removed.

    The read+write happens under `_exclusive_file_lock` so a concurrent
    `append_entry` cannot land between our read and our truncate (which
    would silently drop the new entry).
    """
    path = (history_dir or DEFAULT_HISTORY_DIR) / HISTORY_FILE
    if not path.exists():
        return 0

    current_commit = _current_git_head()
    if not current_commit:
        return 0

    with open(path, "r+") as f, _exclusive_file_lock(f):
        f.seek(0)
        lines = f.read().strip().splitlines()
        kept: list[str] = []
        removed = 0

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if is_dirty_entry(entry, current_commit):
                removed += 1
            else:
                kept.append(line)

        if removed:
            f.seek(0)
            f.truncate()
            if kept:
                f.write("\n".join(kept) + "\n")
    return removed
