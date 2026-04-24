"""Tests for `_classify_changes` — diffing logic for `protest history --compare`.

Each case entry is a minimal dict mirroring what `_all_cases(entry)` returns
from a history JSONL record: at least `passed`, optionally `case_hash` and
`eval_hash`.
"""

from __future__ import annotations

from protest.cli.history import _classify_changes


def _case(
    *,
    passed: bool = True,
    case_hash: str | None = None,
    eval_hash: str | None = None,
) -> dict:
    entry: dict = {"passed": passed}
    if case_hash is not None:
        entry["case_hash"] = case_hash
    if eval_hash is not None:
        entry["eval_hash"] = eval_hash
    return entry


class TestClassifyChangesDeleted:
    """Cases present in `prev` but absent from `curr` land in `deleted`."""

    def test_single_deletion(self) -> None:
        prev = {"case_a": _case(passed=True), "case_b": _case(passed=True)}
        curr = {"case_a": _case(passed=True)}
        changes = _classify_changes(curr, prev)
        assert changes["deleted"] == ["case_b"]
        assert changes["new"] == []
        assert changes["fixed"] == []
        assert changes["regressed"] == []
        assert changes["modified"] == []

    def test_multiple_deletions_preserve_prev_order(self) -> None:
        prev = {
            "alpha": _case(),
            "beta": _case(),
            "gamma": _case(),
            "delta": _case(),
        }
        curr = {"alpha": _case()}
        changes = _classify_changes(curr, prev)
        assert changes["deleted"] == ["beta", "gamma", "delta"]

    def test_deletion_coexists_with_other_changes(self) -> None:
        prev = {
            "to_delete": _case(passed=True),
            "to_fix": _case(passed=False),
            "stable": _case(passed=True),
        }
        curr = {
            "to_fix": _case(passed=True),
            "stable": _case(passed=True),
            "brand_new": _case(passed=True),
        }
        changes = _classify_changes(curr, prev)
        assert changes["deleted"] == ["to_delete"]
        assert changes["fixed"] == ["to_fix"]
        assert changes["new"] == ["brand_new"]

    def test_all_cases_deleted(self) -> None:
        prev = {"a": _case(), "b": _case()}
        curr: dict = {}
        changes = _classify_changes(curr, prev)
        assert changes["deleted"] == ["a", "b"]
        assert changes["new"] == []

    def test_no_deletions(self) -> None:
        prev = {"a": _case()}
        curr = {"a": _case(), "b": _case()}
        changes = _classify_changes(curr, prev)
        assert changes["deleted"] == []
        assert changes["new"] == ["b"]


class TestClassifyChangesExistingCategories:
    """Existing categories keep working after adding `deleted`."""

    def test_new_case(self) -> None:
        changes = _classify_changes({"a": _case()}, {})
        assert changes["new"] == ["a"]

    def test_fixed_case(self) -> None:
        prev = {"a": _case(passed=False)}
        curr = {"a": _case(passed=True)}
        assert _classify_changes(curr, prev)["fixed"] == ["a"]

    def test_regressed_case(self) -> None:
        prev = {"a": _case(passed=True)}
        curr = {"a": _case(passed=False)}
        assert _classify_changes(curr, prev)["regressed"] == ["a"]

    def test_modified_case_hash(self) -> None:
        prev = {"a": _case(case_hash="h1")}
        curr = {"a": _case(case_hash="h2")}
        assert _classify_changes(curr, prev)["modified"] == ["a (case modified)"]

    def test_modified_eval_hash(self) -> None:
        prev = {"a": _case(eval_hash="h1")}
        curr = {"a": _case(eval_hash="h2")}
        assert _classify_changes(curr, prev)["modified"] == ["a (scoring modified)"]

    def test_no_changes(self) -> None:
        prev = {"a": _case(passed=True)}
        curr = {"a": _case(passed=True)}
        changes = _classify_changes(curr, prev)
        assert all(not v for v in changes.values())


class TestClassifyChangesResultShape:
    """Result dict always has the five expected keys."""

    def test_empty_inputs_still_yield_five_buckets(self) -> None:
        changes = _classify_changes({}, {})
        assert set(changes.keys()) == {
            "fixed",
            "regressed",
            "modified",
            "new",
            "deleted",
        }
        assert all(v == [] for v in changes.values())
