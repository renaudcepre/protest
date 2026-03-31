"""Tests for history stats — error-only runs must be excluded from stats."""

from __future__ import annotations

from protest.cli.history import _aggregate_suites, _rich_score_arrows


def _make_entry(
    suite_name: str = "pipeline",
    passed: int = 0,
    total: int = 0,
    errored: int = 0,
    cases: dict | None = None,
) -> dict:
    """Build a minimal history entry with one suite."""
    return {
        "suites": {
            suite_name: {
                "kind": "eval",
                "passed": passed,
                "total_cases": total,
                "errored": errored,
                "cases": cases or {},
            }
        }
    }


def _case(passed: bool, score: float) -> dict:
    return {"passed": passed, "scores": {"accuracy": score}}


def _error_case() -> dict:
    return {"passed": False, "is_error": True, "scores": {}}


class TestErrorRunsExcludedFromStats:
    """Error-only runs (fixture crashes) are excluded from stats."""

    def test_error_runs_not_counted(self) -> None:
        """Runs where errored >= total should not count in n_runs or pass_rates."""
        entries = [
            _make_entry(passed=29, total=39, cases={"a": _case(True, 0.8)}),
            _make_entry(passed=0, total=1, errored=1, cases={"x": _error_case()}),
            _make_entry(passed=0, total=1, errored=1, cases={"x": _error_case()}),
            _make_entry(passed=28, total=39, cases={"a": _case(True, 0.7)}),
            _make_entry(passed=0, total=1, errored=1, cases={"x": _error_case()}),
        ]

        suites = _aggregate_suites(entries)
        s = suites["pipeline"]

        # Only 2 real runs counted
        assert s["n_runs"] == 2
        assert len(s["pass_rates"]) == 2
        # pass_rates reflect only real runs
        assert s["pass_rates"][0] == 29 / 39
        assert s["pass_rates"][1] == 28 / 39

    def test_error_cases_not_tracked(self) -> None:
        """Cases with is_error=True should not appear in cases_seen or score_values."""
        entries = [
            _make_entry(
                passed=1,
                total=2,
                errored=0,
                cases={
                    "real_case": _case(True, 0.9),
                    "errored_case": _error_case(),
                },
            ),
        ]

        suites = _aggregate_suites(entries)
        s = suites["pipeline"]
        assert "real_case" in s["cases_seen"]
        assert "errored_case" not in s["cases_seen"]
        assert len(s["score_values"]["accuracy"]) == 1

    def test_error_cases_not_in_flaky(self) -> None:
        """Error cases should never appear as flaky."""
        entries = [
            _make_entry(passed=1, total=1, cases={"a": _case(True, 0.9)}),
            _make_entry(
                passed=0,
                total=1,
                errored=1,
                cases={"a": _error_case()},
            ),
        ]

        suites = _aggregate_suites(entries)
        s = suites["pipeline"]
        # Only the real run is counted
        assert s["n_runs"] == 1
        assert len(s["flaky"]) == 0

    def test_all_error_runs_produce_empty_suite(self) -> None:
        """If ALL runs are errors, suite has 0 runs and empty stats."""
        entries = [
            _make_entry(passed=0, total=1, errored=1, cases={"x": _error_case()}),
            _make_entry(passed=0, total=1, errored=1, cases={"x": _error_case()}),
        ]

        suites = _aggregate_suites(entries)
        # Suite exists but has 0 real runs
        assert suites["pipeline"]["n_runs"] == 0
        assert suites["pipeline"]["pass_rates"] == []

    def test_mixed_real_and_error_runs(self) -> None:
        """Real data pattern: mostly errors with a few real runs."""
        entries = [
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=29, total=39, cases={"a": _case(True, 0.7)}),  # real
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=28, total=39, cases={"a": _case(True, 0.8)}),  # real
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=0, total=1, errored=1),  # error
            _make_entry(passed=0, total=1, errored=1),  # error
        ]

        suites = _aggregate_suites(entries)
        s = suites["pipeline"]

        assert s["n_runs"] == 2  # not 10
        assert len(s["pass_rates"]) == 2
        # Arrows reflect only the 2 real runs, not the 8 errors
        arrows = _rich_score_arrows(s["score_values"])
        # accuracy went 0.7 → 0.8 → should show ↗
        assert "↗" in arrows


class TestScoreArrowsWithCleanData:
    """Score arrows with only real runs (no errors to filter)."""

    def test_stable_scores_show_no_trend(self) -> None:
        entries = [
            _make_entry(passed=2, total=2, cases={"a": _case(True, 0.8)}),
            _make_entry(passed=2, total=2, cases={"a": _case(True, 0.8)}),
        ]
        suites = _aggregate_suites(entries)
        arrows = _rich_score_arrows(suites["pipeline"]["score_values"])
        assert "→" in arrows

    def test_improving_scores_show_up(self) -> None:
        entries = [
            _make_entry(passed=1, total=1, cases={"a": _case(True, 0.3)}),
            _make_entry(passed=1, total=1, cases={"a": _case(True, 0.9)}),
        ]
        suites = _aggregate_suites(entries)
        arrows = _rich_score_arrows(suites["pipeline"]["score_values"])
        assert "↗" in arrows

    def test_declining_scores_show_down(self) -> None:
        entries = [
            _make_entry(passed=1, total=1, cases={"a": _case(True, 0.9)}),
            _make_entry(passed=1, total=1, cases={"a": _case(True, 0.3)}),
        ]
        suites = _aggregate_suites(entries)
        arrows = _rich_score_arrows(suites["pipeline"]["score_values"])
        assert "↘" in arrows
