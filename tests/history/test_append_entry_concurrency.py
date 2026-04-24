"""Tests for `append_entry` — concurrent writer safety.

Covers the basic invariant (one entry = one parseable line) and the
multiprocess-concurrency case: N workers append concurrently to the same
file; every line must be parseable JSON. Without locking, interleaved
writes larger than `PIPE_BUF` would corrupt lines and the test would fail.
"""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

from protest.history.storage import append_entry


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
