"""Tests for `EvalCaseResult.from_test_result`.

This classmethod is the single constructor used by both the runner (post-
execution) and the results writer (pass/fail hooks). The test below pins the
full field mapping so that future additions to `EvalPayload` or `TestResult`
either update the classmethod or break the test.
"""

from __future__ import annotations

import pytest

from protest.entities.events import EvalPayload, EvalScoreEntry, TestResult
from protest.evals.types import EvalCaseResult


def _make_payload(**overrides: object) -> EvalPayload:
    defaults: dict[str, object] = {
        "case_name": "case_one",
        "passed": True,
        "task_duration": 0.123,
        "inputs": "in",
        "output": "out",
        "expected_output": "expected",
        "scores": {"accuracy": EvalScoreEntry(value=0.9, passed=True)},
        "case_hash": "ch",
        "eval_hash": "eh",
        "task_input_tokens": 100,
        "task_output_tokens": 200,
        "task_cost": 0.01,
        "judge_call_count": 1,
        "judge_input_tokens": 50,
        "judge_output_tokens": 30,
        "judge_cost": 0.005,
    }
    defaults.update(overrides)
    return EvalPayload(**defaults)  # type: ignore[arg-type]


def _make_result(
    *,
    error: Exception | None = None,
    is_fixture_error: bool = False,
    payload: EvalPayload | None = None,
    node_id: str = "suite::case_one",
) -> TestResult:
    return TestResult(
        name="case_one",
        node_id=node_id,
        error=error,
        is_fixture_error=is_fixture_error,
        is_eval=True,
        eval_payload=payload or _make_payload(),
    )


class TestFromTestResultHappyPath:
    """Full field mapping: all payload + result fields land in the result."""

    def test_all_fields_copied(self) -> None:
        result = _make_result()
        case = EvalCaseResult.from_test_result(result)
        assert case.case_name == "case_one"
        assert case.node_id == "suite::case_one"
        assert case.duration == pytest.approx(0.123)
        assert case.passed is True
        assert case.inputs == "in"
        assert case.output == "out"
        assert case.expected_output == "expected"
        assert case.case_hash == "ch"
        assert case.eval_hash == "eh"
        assert case.is_error is False

    def test_scores_converted_from_entries(self) -> None:
        case = EvalCaseResult.from_test_result(_make_result())
        assert len(case.scores) == 1
        assert case.scores[0].name == "accuracy"
        assert case.scores[0].value == 0.9

    def test_skipped_flag_preserved(self) -> None:
        """Regression (#116): dropping `skipped` turned short-circuited
        placeholders (value=False, skipped=True) into reported failures."""
        payload = _make_payload(
            scores={
                "gate": EvalScoreEntry(value=False, passed=False),
                "judge.ok": EvalScoreEntry(value=False, passed=True, skipped=True),
            }
        )
        case = EvalCaseResult.from_test_result(_make_result(payload=payload))
        by_name = {s.name: s for s in case.scores}
        assert by_name["judge.ok"].skipped is True
        assert by_name["judge.ok"].passed is True
        assert by_name["judge.ok"] not in case.failed_scores
        assert by_name["gate"] in case.failed_scores

    def test_task_usage_copied(self) -> None:
        """Regression: writer used to drop these fields silently."""
        case = EvalCaseResult.from_test_result(_make_result())
        assert case.task_input_tokens == 100
        assert case.task_output_tokens == 200
        assert case.task_cost == pytest.approx(0.01)

    def test_judge_usage_copied(self) -> None:
        """Regression: writer used to drop these fields silently."""
        case = EvalCaseResult.from_test_result(_make_result())
        assert case.judge_call_count == 1
        assert case.judge_input_tokens == 50
        assert case.judge_output_tokens == 30
        assert case.judge_cost == pytest.approx(0.005)


class TestFromTestResultPassedDerivation:
    """`passed` is derived, not passed in - the writer no longer gets it wrong."""

    def test_passed_when_no_error_and_payload_passed(self) -> None:
        result = _make_result(payload=_make_payload(passed=True))
        assert EvalCaseResult.from_test_result(result).passed is True

    def test_failed_when_payload_not_passed(self) -> None:
        result = _make_result(payload=_make_payload(passed=False))
        assert EvalCaseResult.from_test_result(result).passed is False

    def test_failed_when_error_present(self) -> None:
        result = _make_result(
            error=RuntimeError("boom"),
            payload=_make_payload(passed=True),
        )
        assert EvalCaseResult.from_test_result(result).passed is False

    def test_is_error_reflects_fixture_error(self) -> None:
        result = _make_result(
            error=RuntimeError("fx"),
            is_fixture_error=True,
        )
        case = EvalCaseResult.from_test_result(result)
        assert case.is_error is True
        assert case.passed is False


class TestFromTestResultErrors:
    """Defensive: classmethod refuses a TestResult without eval_payload."""

    def test_missing_payload_raises(self) -> None:
        result = TestResult(
            name="n",
            node_id="x",
            is_eval=False,
            eval_payload=None,
        )
        with pytest.raises(ValueError, match="eval_payload"):
            EvalCaseResult.from_test_result(result)
