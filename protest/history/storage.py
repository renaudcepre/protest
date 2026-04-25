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
        if _is_future_schema(entry):
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
