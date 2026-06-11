"""HistoryPlugin - persists test and eval run results as JSONL."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from protest.entities import SuiteKind
from protest.evals.suite import EvalSuite
from protest.history import storage
from protest.history.collector import collect_env_info, collect_git_info
from protest.history.storage import (
    HISTORY_FILE,
    SCHEMA_VERSION,
    append_entry,
    load_previous_run,
)
from protest.plugin import PluginBase

if TYPE_CHECKING:
    from pathlib import Path

    from protest.core.session import ProTestSession
    from protest.entities.events import TestResult
    from protest.evals.types import EvalCaseResult, EvalSuiteReport
    from protest.plugin import PluginContext


class HistoryPlugin(PluginBase):
    """Persists test and eval results to JSONL for run-over-run tracking.

    Always-on plugin. When history is disabled on the session, all handlers
    are no-ops. Handles both test results (on_test_pass/fail) and eval
    results (on_eval_suite_end).
    """

    name = "history"
    description = "Run history tracking"

    def __init__(self, history_dir: Path | None = None) -> None:
        self._history_dir = history_dir or storage.DEFAULT_HISTORY_DIR
        self._history_file = self._history_dir / HISTORY_FILE
        # Test data
        self._test_suites: dict[str, dict[str, dict[str, Any]]] = {}
        self._suite_kinds: dict[str, SuiteKind] = {}
        # Bucket name for tests without a suite_path; resolved during setup
        # to the first non-eval suite name, or kept as the literal fallback.
        self._default_suite_name: str | None = None
        # Eval data
        self._eval_reports: dict[str, EvalSuiteReport] = {}
        self._eval_suite_metadata: dict[str, dict[str, Any]] = {}
        self._eval_judge_info: dict[str, dict[str, Any]] = {}
        # Session state
        self._enabled: bool = False
        self._metadata: dict[str, Any] = {}

    @classmethod
    def activate(cls, ctx: PluginContext) -> HistoryPlugin | None:
        if ctx.get("no_history", False):
            return None
        return cls(history_dir=ctx.get("history_dir"))

    def setup(self, session: ProTestSession) -> None:
        self._enabled = session.history
        self._metadata = dict(session.metadata)
        if session.history_dir:
            self._history_dir = session.history_dir
            self._history_file = self._history_dir / HISTORY_FILE
        for suite in session.suites:
            self._suite_kinds[suite.name] = suite.kind
            if suite.kind == SuiteKind.EVAL:
                self._eval_suite_metadata[suite.name] = suite.suite_metadata
                if isinstance(suite, EvalSuite) and suite.judge is not None:
                    self._eval_judge_info[suite.name] = {
                        "name": suite.judge.name,
                        "provider": suite.judge.provider,
                    }
            elif self._default_suite_name is None:
                self._default_suite_name = suite.name

    # -- Test event handlers --------------------------------------------------

    def on_test_pass(self, result: TestResult) -> None:
        if not self._enabled or result.is_eval:
            return
        self._record_test(result, passed=True)

    def on_test_fail(self, result: TestResult) -> None:
        if not self._enabled or result.is_eval:
            return
        self._record_test(result, passed=False)

    def _record_test(self, result: TestResult, *, passed: bool) -> None:
        suite_name = (
            result.suite_path.root_name
            if result.suite_path
            else (self._default_suite_name or "tests")
        )
        if suite_name not in self._test_suites:
            self._test_suites[suite_name] = {}
        self._test_suites[suite_name][result.name] = {
            "passed": passed,
            "duration": round(result.duration, 5),
        }

    # -- Eval event handlers --------------------------------------------------

    def on_eval_suite_end(self, report: EvalSuiteReport) -> None:
        if not self._enabled:
            return
        self._eval_reports[report.suite_name] = report

    # -- Session end: write combined entry ------------------------------------

    def on_session_end(self, result: Any) -> None:
        if not self._enabled:
            return
        if not self._test_suites and not self._eval_reports:
            return

        suites_data: dict[str, Any] = {}

        # Test suites
        for suite_name, cases in self._test_suites.items():
            total = len(cases)
            passed = sum(1 for c in cases.values() if c["passed"])
            kind = self._suite_kinds.get(suite_name)
            suites_data[suite_name] = {
                "kind": kind.value if kind is not None else "test",
                "total_cases": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(passed / total, 4) if total else 0,
                "duration": round(sum(c["duration"] for c in cases.values()), 2),
                "cases": cases,
            }

        # Eval suites
        all_score_stats: list[Any] = []
        for suite_name, report in self._eval_reports.items():
            sm = self._eval_suite_metadata.get(suite_name, {})
            suites_data[suite_name] = {
                "kind": "eval",
                "model": sm.get("model"),
                "provider": sm.get("provider"),
                "total_cases": report.total_count,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "errored": report.errored_count,
                "pass_rate": round(report.pass_rate, 4),
                "duration": round(report.duration, 2),
                "cases": {c.case_name: _serialize_eval_case(c) for c in report.cases},
            }
            all_score_stats.extend(report.all_score_stats())

        # Build evals summary (non-null only if we have eval data)
        evals_summary = None
        if self._eval_reports:
            # Derive top-level model from first eval suite (or None if mixed)
            models = {
                sm.get("model")
                for sm in self._eval_suite_metadata.values()
                if sm.get("model")
            }
            top_model = models.pop() if len(models) == 1 else None
            providers = {
                sm.get("provider")
                for sm in self._eval_suite_metadata.values()
                if sm.get("provider")
            }
            top_provider = providers.pop() if len(providers) == 1 else None

            # Aggregate judge info (first one found, or None)
            judge_dict = None
            if self._eval_judge_info:
                first_judge = next(iter(self._eval_judge_info.values()))
                judge_dict = first_judge

            scores_summary = {
                s.name: {
                    "mean": round(s.mean, 4),
                    "median": round(s.median, 4),
                    "p5": round(s.p5, 4),
                    "p95": round(s.p95, 4),
                    "min": round(s.min, 4),
                    "max": round(s.max, 4),
                    "count": s.count,
                }
                for s in all_score_stats
            }

            evals_summary = {
                "model": top_model,
                "provider": top_provider,
                "judge": judge_dict,
                "scores_summary": scores_summary,
            }

        entry: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": str(uuid.uuid4()),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "git": collect_git_info(),
            "environment": collect_env_info(),
            "metadata": self._metadata,
            "evals": evals_summary,
            "suites": suites_data,
        }
        append_entry(self._history_file, entry)


def _serialize_eval_case(case: EvalCaseResult) -> dict[str, Any]:
    """Serialize an eval case result for JSONL storage.

    Skipped scores are excluded: a ShortCircuit skip produces
    `EvalScore(value=False, skipped=True)` - serializing it as an assertion
    would look like a real failure in `history --compare` diffs.

    `case.duration` here is `EvalPayload.task_duration` (SUT-only timing,
    set by the eval wrapper), not the full TestResult duration shown by live
    reporters. Persisted at 10 µs precision so sub-ms SUTs don't all hash
    down to 0.0 across runs.
    """
    entry: dict[str, Any] = {
        "passed": case.passed,
        "is_error": case.is_error,
        "duration": round(case.duration, 5),
        "scores": {
            s.name: s.value for s in case.scores if s.is_metric and not s.skipped
        },
        "case_hash": case.case_hash,
        "eval_hash": case.eval_hash,
    }
    labels = {
        s.name: s.value
        for s in case.scores
        if isinstance(s.value, str) and not s.skipped
    }
    if labels:
        entry["labels"] = labels
    assertions = {
        s.name: s.value
        for s in case.scores
        if isinstance(s.value, bool) and not s.skipped
    }
    if assertions:
        entry["assertions"] = assertions
    return entry


def load_previous_eval_run(history_dir: Any = None) -> dict[str, Any] | None:
    """Load the most recent eval run from history."""
    return load_previous_run(history_dir=history_dir, evals_only=True)
