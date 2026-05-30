"""Tests for C3 — sub-millisecond duration handling.

The eval pipeline persists `EvalPayload.task_duration` (SUT-only timing).
For deterministic stubs / fast classifiers, that value is sub-millisecond
and the previous serializer (`round(_, 3)`) collapsed everything to `0.0`,
making run-over-run comparisons useless. The markdown renderer had the
matching bug — it printed `0ms` for any sub-ms task.
"""

from __future__ import annotations

from protest.evals.results_writer import _format_case_duration, _render_case
from protest.evals.types import EvalCaseResult
from protest.history.plugin import _serialize_eval_case


def _make_case(duration: float) -> EvalCaseResult:
    return EvalCaseResult(
        case_name="case",
        node_id="suite::case",
        scores=(),
        duration=duration,
        passed=True,
        inputs="in",
        output="out",
        expected_output=None,
        case_hash="h",
        eval_hash="e",
        is_error=False,
    )


class TestSerializerPrecision:
    """`_serialize_eval_case` keeps 5-decimal precision (10 µs)."""

    def test_sub_millisecond_is_not_collapsed_to_zero(self) -> None:
        case = _make_case(2.07e-05)  # 20.7 µs
        entry = _serialize_eval_case(case)
        # Previously: 0.0 (round to 3 decimals)
        # Now: 2e-05 (round to 5 decimals — 10 µs precision)
        assert entry["duration"] > 0
        assert entry["duration"] == 2e-05

    def test_distinct_sub_ms_values_remain_distinguishable(self) -> None:
        e1 = _serialize_eval_case(_make_case(1.0e-05))  # 10 µs
        e2 = _serialize_eval_case(_make_case(5.0e-05))  # 50 µs
        assert e1["duration"] != e2["duration"]

    def test_millisecond_values_unchanged(self) -> None:
        # >1ms: 5-decimal rounding produces the same numbers as 3-decimal.
        entry = _serialize_eval_case(_make_case(0.123))
        assert entry["duration"] == 0.123


class TestMarkdownDurationFormat:
    """`_format_case_duration` adapts unit to magnitude."""

    def test_microseconds_for_sub_millisecond(self) -> None:
        assert _format_case_duration(2.07e-05) == "21µs"

    def test_two_decimals_in_low_milliseconds(self) -> None:
        # 2.5 ms — keep one fractional digit so 1ms vs 2ms is visible.
        assert _format_case_duration(0.0025) == "2.50ms"

    def test_integer_milliseconds_in_mid_range(self) -> None:
        assert _format_case_duration(0.135) == "135ms"

    def test_seconds_for_one_or_more(self) -> None:
        assert _format_case_duration(2.5) == "2.50s"

    def test_renders_microseconds_in_case_header(self) -> None:
        case = _make_case(2.07e-05)
        rendered = _render_case(case)
        # Header contains the duration; previously read "(0ms)".
        assert "21µs" in rendered.splitlines()[0]
