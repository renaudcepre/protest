"""EvalHistoryPlugin — persists eval run results as JSONL with model/scores."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from protest.entities import SuiteKind
from protest.history.collector import collect_env_info, collect_git_info
from protest.history.storage import (
    DEFAULT_HISTORY_DIR,
    HISTORY_FILE,
    append_entry,
    load_history,
    load_previous_run,
)
from protest.plugin import PluginBase

if TYPE_CHECKING:
    from pathlib import Path

    from protest.core.session import ProTestSession
    from protest.evals.types import EvalCaseResult, EvalSuiteReport, ModelInfo
    from protest.plugin import PluginContext


class EvalHistoryPlugin(PluginBase):
    """Persists eval results to JSONL with model/judge/scores metadata.

    Listens to EVAL_SUITE_END events (emitted by the core runner).
    """

    name = "eval-history"
    description = "Eval history tracking"

    def __init__(
        self,
        *,
        history_dir: Path | None = None,
        model: ModelInfo | None = None,
        judge: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._history_dir = history_dir or DEFAULT_HISTORY_DIR
        self._history_file = self._history_dir / HISTORY_FILE
        self._model = model
        self._judge = judge
        self._metadata = dict(metadata) if metadata else {}
        self._reports: dict[str, EvalSuiteReport] = {}

    _suite_metadata: dict[str, dict[str, Any]]

    @classmethod
    def activate(cls, ctx: PluginContext) -> EvalHistoryPlugin | None:
        return None  # Wired explicitly by session

    def setup(self, session: ProTestSession) -> None:
        """Collect per-suite metadata from session."""
        self._suite_metadata = {}
        for suite in session.suites:
            if suite.kind == SuiteKind.EVAL:
                self._suite_metadata[suite.name] = suite.suite_metadata

    def on_eval_suite_end(self, report: EvalSuiteReport) -> None:
        """Collect suite reports as they arrive."""
        self._reports[report.suite_name] = report

    def on_session_end(self, _result: Any) -> None:
        """Write all collected reports to history."""
        if not self._reports:
            return
        entry = _build_entry(
            self._reports,
            self._model,
            self._judge,
            self._metadata,
            self._suite_metadata,
        )
        append_entry(self._history_file, entry)

    def load_entries(self, n: int | None = None) -> list[dict[str, Any]]:
        """Load entries from history file."""
        return load_history(history_dir=self._history_dir, n=n, evals_only=True)


def _build_entry(
    reports: dict[str, EvalSuiteReport],
    model: ModelInfo | None,
    judge: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
    all_suite_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a complete history entry covering all suites in the session."""
    suites_data: dict[str, Any] = {}
    all_score_stats: list[Any] = []

    for suite_name, report in reports.items():
        sm = (all_suite_metadata or {}).get(suite_name, {})
        suite_model = sm.get("model") or (model.name if model else None)
        suite_provider = sm.get("provider") or (model.provider if model else None)
        suites_data[suite_name] = {
            "kind": "eval",
            "model": suite_model,
            "provider": suite_provider,
            "total_cases": report.total_count,
            "passed": report.passed_count,
            "failed": report.failed_count,
            "errored": report.errored_count,
            "pass_rate": round(report.pass_rate, 4),
            "duration": round(report.duration, 2),
            "cases": {c.case_name: _serialize_case(c) for c in report.cases},
        }
        all_score_stats.extend(report.all_score_stats())

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

    return {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "git": collect_git_info(),
        "environment": collect_env_info(),
        "metadata": dict(metadata) if metadata else {},
        "evals": {
            "model": model.name if model else None,
            "provider": model.provider if model else None,
            "judge": judge,
            "scores_summary": scores_summary,
        },
        "suites": suites_data,
    }


def _serialize_case(case: EvalCaseResult) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "passed": case.passed,
        "is_error": case.is_error,
        "duration": round(case.duration, 3),
        "scores": {s.name: s.value for s in case.scores if s.is_metric},
        "case_hash": case.case_hash,
        "eval_hash": case.eval_hash,
    }
    labels = {s.name: s.value for s in case.scores if isinstance(s.value, str)}
    if labels:
        entry["labels"] = labels
    assertions = {s.name: s.value for s in case.scores if isinstance(s.value, bool)}
    if assertions:
        entry["assertions"] = assertions
    return entry


def load_previous_eval_run(history_dir: Any = None) -> dict[str, Any] | None:
    """Load the most recent eval run from history."""
    return load_previous_run(history_dir=history_dir, evals_only=True)
