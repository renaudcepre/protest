"""EvalResultsWriter — writes per-case eval results as markdown files.

Listens to TEST_PASS/FAIL events, filters for eval cases, and writes
a markdown file for each case to .protest/results/<suite>_<timestamp>/.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from protest import console
from protest.evals.types import EvalCaseResult, EvalScore, EvalSuiteReport
from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities.events import TestResult
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
    def activate(cls, ctx: PluginContext) -> EvalResultsWriter:
        return cls(history_dir=ctx.get("history_dir"))

    def on_test_pass(self, result: TestResult) -> None:
        self._maybe_write(result)

    def on_test_fail(self, result: TestResult) -> None:
        self._maybe_write(result)

    def _maybe_write(self, result: TestResult) -> None:
        if not result.is_eval or result.eval_payload is None:
            return
        suite_name = result.suite_path.root_name if result.suite_path else "evals"
        case_result = EvalCaseResult.from_test_result(result)
        self._write_case_file(case_result, suite_name)

    def _write_case_file(self, case_result: EvalCaseResult, suite_name: str) -> None:
        if suite_name not in self._run_dirs:
            self._run_dirs[suite_name] = _make_run_dir(suite_name, self._results_base)
        _write_case_file(case_result, self._run_dirs[suite_name])

    def on_eval_suite_end(self, report: Any) -> None:
        """Print results dir path for the suite."""

        if not isinstance(report, EvalSuiteReport):
            return
        run_dir = self._run_dirs.get(report.suite_name)
        if run_dir:
            console.print(f"  Results: {run_dir}", prefix=False)


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
    duration = _format_case_duration(case.duration)
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


_ONE_MILLISECOND = 0.001
_TEN_MILLISECONDS = 0.01
_ONE_SECOND = 1.0


def _format_case_duration(seconds: float) -> str:
    """Format SUT duration with adaptive units.

    Sub-ms tasks (deterministic stubs, fast classifiers) used to render as
    `0ms` because the renderer rounded to the nearest millisecond.
    """
    if seconds < _ONE_MILLISECOND:
        return f"{seconds * 1_000_000:.0f}µs"
    if seconds < _TEN_MILLISECONDS:
        return f"{seconds * 1000:.2f}ms"
    if seconds < _ONE_SECOND:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _format_score(score: EvalScore) -> str:
    icon = "·" if score.is_metric else ("✓" if score.passed else "✗")
    return f"- **{score.name}**: {score.value} {icon}"


def _format_value(value: Any) -> str:
    if value is None:
        return "_none_"
    if isinstance(value, str):
        return value if value.strip() else "_empty string_"
    return f"```\n{value!r}\n```"
