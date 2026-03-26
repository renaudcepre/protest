"""EvalResultsWriter — writes per-case eval results as markdown files.

Listens to TEST_PASS/FAIL events, filters for eval cases, and writes
a markdown file for each case to .protest/results/<suite>_<timestamp>/.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities.events import TestResult
    from protest.evals.types import EvalCaseResult, EvalScore
    from protest.plugin import PluginContext

DEFAULT_RESULTS_DIR = Path(".protest") / "results"


class EvalResultsWriter(PluginBase):
    """Writes per-case eval result files as markdown."""

    name = "eval-results-writer"
    description = "Write eval case result files"

    def __init__(self, history_dir: Path | None = None) -> None:
        self._results_base = (
            (history_dir / "results") if history_dir else DEFAULT_RESULTS_DIR
        )
        self._run_dirs: dict[str, Path] = {}

    @classmethod
    def activate(cls, ctx: PluginContext) -> EvalResultsWriter | None:
        return None  # Wired explicitly by session

    def on_test_pass(self, result: TestResult) -> None:
        self._maybe_write(result, passed=True)

    def on_test_fail(self, result: TestResult) -> None:
        self._maybe_write(result, passed=False)

    def _maybe_write(self, result: TestResult, *, passed: bool) -> None:
        if not result.is_eval or result.eval_payload is None:
            return
        suite_name = result.suite_path.root_name if result.suite_path else "evals"
        case_result = _build_case_result(result, passed)
        self._write_case_file(case_result, suite_name)

    def _write_case_file(self, case_result: EvalCaseResult, suite_name: str) -> None:
        if suite_name not in self._run_dirs:
            self._run_dirs[suite_name] = _make_run_dir(suite_name, self._results_base)
        _write_case_file(case_result, self._run_dirs[suite_name])

    def on_eval_suite_end(self, report: Any) -> None:
        """Print results dir path for the suite."""
        from protest.evals.types import EvalSuiteReport

        if not isinstance(report, EvalSuiteReport):
            return
        run_dir = self._run_dirs.get(report.suite_name)
        if run_dir:
            print(f"  Results: {run_dir}")


def _build_case_result(result: TestResult, passed: bool) -> EvalCaseResult:
    """Build EvalCaseResult from a TestResult with eval_payload."""
    from protest.evals.types import EvalCaseResult, EvalScore

    payload = result.eval_payload
    assert payload is not None
    return EvalCaseResult(
        case_name=payload.case_name or "",
        node_id=result.node_id,
        scores=tuple(
            EvalScore(
                name=name,
                value=entry.value,
            )
            for name, entry in payload.scores.items()
        ),
        duration=payload.task_duration,
        passed=passed,
        inputs=payload.inputs,
        output=payload.output,
        expected_output=payload.expected_output,
        case_hash=payload.case_hash,
        eval_hash=payload.eval_hash,
    )


# ---------------------------------------------------------------------------
# File writing helpers
# ---------------------------------------------------------------------------


def _make_run_dir(suite_name: str, base_dir: Path | None = None) -> Path:
    """Create and return the timestamped directory for this run."""
    base = base_dir or DEFAULT_RESULTS_DIR
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_suite = re.sub(r"[^\w\-]", "_", suite_name)
    run_dir = base / f"{safe_suite}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_case_file(case: EvalCaseResult, run_dir: Path) -> None:
    """Write a markdown file for a single eval case."""
    safe_name = re.sub(r"[^\w\-]", "_", case.case_name)
    path = run_dir / f"{safe_name}.md"
    path.write_text(_render_case(case), encoding="utf-8")


def _render_case(case: EvalCaseResult) -> str:
    status = "PASS ✓" if case.passed else "FAIL ✗"
    duration = (
        f"{case.duration * 1000:.0f}ms"
        if case.duration < 1
        else f"{case.duration:.2f}s"
    )
    lines: list[str] = [
        f"# {case.case_name} — {status} ({duration})",
        "",
    ]

    lines += ["## Input", "", _format_value(case.inputs), ""]
    lines += ["## Output", "", _format_value(case.output), ""]
    lines += ["## Expected", "", _format_value(case.expected_output), ""]

    if case.scores:
        lines += ["## Scores", ""]
        for score in case.scores:
            lines.append(_format_score(score))
        lines.append("")

    return "\n".join(lines)


def _format_score(score: EvalScore) -> str:
    if score.is_metric:
        icon = "·"
    else:
        icon = "✓" if score.passed else "✗"
    return f"- **{score.name}**: {score.value} {icon}"


def _format_value(value: Any) -> str:
    if value is None:
        return "_none_"
    if isinstance(value, str):
        return value if value.strip() else "_empty string_"
    return f"```\n{value!r}\n```"
