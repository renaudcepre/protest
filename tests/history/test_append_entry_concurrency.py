"""Tests for `append_entry` — concurrent writer safety.

Covers the basic invariant (one entry = one parseable line) and the
multiprocess-concurrency case: N workers append concurrently to the same
file; every line must be parseable JSON. Without locking, interleaved
writes larger than `PIPE_BUF` would corrupt lines and the test would fail.

Also covers `clean_dirty` concurrency: a concurrent `append_entry` while
`clean_dirty` is running must not be silently dropped by the truncate.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
from pathlib import Path

from protest.history.storage import append_entry, clean_dirty


def _worker_append(args: tuple[str, int, int]) -> None:
    """Child-process entry: append `count` entries, each padded to ~5 KB.

    The padding pushes the write past PIPE_BUF (4 KB) so that without a
    lock the POSIX O_APPEND atomicity guarantee no longer applies.
    """
    path_str, worker_id, count = args
    path = Path(path_str)
    padding = "x" * 5000
    for i in range(count):
        append_entry(path, {"worker": worker_id, "i": i, "pad": padding})


def _worker_append_innocent(args: tuple[str, int, int]) -> None:
    """Append entries on an unrelated commit — `clean_dirty` must not touch them."""
    path_str, worker_id, count = args
    path = Path(path_str)
    for i in range(count):
        append_entry(
            path,
            {
                "worker": worker_id,
                "i": i,
                "git": {"commit": "innocent_commit", "dirty": False},
                "suites": {},
            },
        )


def _worker_clean_dirty(args: tuple[str, int]) -> None:
    """Repeatedly run clean_dirty while another worker appends."""
    path_str, count = args
    history_dir = Path(path_str).parent
    for _ in range(count):
        clean_dirty(history_dir=history_dir)


class TestAppendEntryBasic:
    """Single-writer invariants."""

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "history.jsonl"
        append_entry(target, {"k": "v"})
        assert target.exists()
        assert target.parent.is_dir()

    def test_appends_one_line_per_call(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        append_entry(path, {"a": 1})
        append_entry(path, {"b": 2})
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_default_str_serializes_non_json_types(self, tmp_path: Path) -> None:
        """`json.dumps(..., default=str)` handles non-serializable values."""
        path = tmp_path / "history.jsonl"

        class Marker:
            def __str__(self) -> str:
                return "marker-str"

        append_entry(path, {"obj": Marker()})
        (line,) = path.read_text().splitlines()
        assert json.loads(line) == {"obj": "marker-str"}


class TestAppendEntryConcurrency:
    """Multi-process concurrent appends produce N parseable lines."""

    def test_concurrent_writers_do_not_interleave(self, tmp_path: Path) -> None:
        path = tmp_path / "history.jsonl"
        workers = 8
        per_worker = 5
        total = workers * per_worker

        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            pool.map(
                _worker_append,
                [(str(path), wid, per_worker) for wid in range(workers)],
            )

        lines = path.read_text().splitlines()
        assert len(lines) == total, (
            f"expected {total} lines, got {len(lines)} — some writes were lost"
        )

        counts_per_worker: dict[int, int] = {}
        for raw in lines:
            entry = json.loads(raw)  # raises JSONDecodeError on interleaved bytes
            counts_per_worker[entry["worker"]] = (
                counts_per_worker.get(entry["worker"], 0) + 1
            )

        assert counts_per_worker == dict.fromkeys(range(workers), per_worker)


class TestCleanDirtyConcurrency:
    """`clean_dirty` and `append_entry` must serialize via the same lock.

    The dangerous race: clean_dirty does (read → compute kept → truncate →
    rewrite). Without a lock, an `append_entry` landing between the read
    and the truncate is silently overwritten — the new entry disappears.
    Here we run both in parallel and check the conserved quantity: every
    appended "innocent" entry (different commit) must survive.
    """

    def test_concurrent_append_not_dropped_by_clean_dirty(self, tmp_path: Path) -> None:
        # Skip outside a git repo — clean_dirty depends on `git rev-parse HEAD`.
        try:
            subprocess.run(
                ["git", "rev-parse", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return

        path = tmp_path / "history.jsonl"
        # Pre-populate with one no-op entry so the file exists for clean_dirty.
        append_entry(
            path,
            {
                "worker": -1,
                "git": {"commit": "preexisting", "dirty": False},
                "suites": {},
            },
        )

        per_worker = 30
        ctx = mp.get_context("spawn")
        with ctx.Pool(2) as pool:
            pool.starmap(
                _dispatch_worker,
                [
                    ("append", str(path), 0, per_worker),
                    ("clean", str(path), 0, per_worker),
                ],
            )

        lines = path.read_text().splitlines()
        # Every line still parses (no torn writes).
        innocent_count = 0
        for raw in lines:
            entry = json.loads(raw)
            if entry.get("git", {}).get("commit") == "innocent_commit":
                innocent_count += 1
        # All `per_worker` innocent appends survived — none silently
        # discarded by an interleaved clean_dirty truncate.
        assert innocent_count == per_worker, (
            f"expected {per_worker} innocent entries, got {innocent_count} — "
            "concurrent clean_dirty dropped some appends"
        )


def _dispatch_worker(kind: str, path_str: str, worker_id: int, count: int) -> None:
    """Top-level dispatcher so spawn() can pickle the call."""
    if kind == "append":
        _worker_append_innocent((path_str, worker_id, count))
    else:
        _worker_clean_dirty((path_str, count))
