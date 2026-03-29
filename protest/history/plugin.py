"""HistoryPlugin — persists test run results as JSONL."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from protest.history.collector import collect_env_info, collect_git_info
from protest.history.storage import DEFAULT_HISTORY_DIR, HISTORY_FILE, append_entry
from protest.plugin import PluginBase

if TYPE_CHECKING:
    from pathlib import Path

    from protest.entities.events import SessionResult, TestResult
    from protest.plugin import PluginContext


class HistoryPlugin(PluginBase):
    """Persists test results to JSONL for run-over-run tracking."""

    name = "history"
    description = "Test history tracking"

    def __init__(self, history_dir: Path | None = None) -> None:
        self._history_dir = history_dir or DEFAULT_HISTORY_DIR
        self._history_file = self._history_dir / HISTORY_FILE
        self._suites: dict[str, dict[str, dict[str, Any]]] = {}
        self._suite_kinds: dict[str, str] = {}
        self._default_suite_name: str = "tests"
        self._history_enabled: bool = False
        self._metadata: dict[str, Any] = {}

    @classmethod
    def activate(cls, ctx: PluginContext) -> HistoryPlugin | None:
        return None  # Wired explicitly by session

    def setup(self, session: Any) -> None:
        self._history_enabled = getattr(session, "history", False)
        self._metadata = dict(getattr(session, "metadata", None) or {})
        for suite in getattr(session, "suites", []):
            self._suite_kinds[suite.name] = getattr(suite, "kind", "test")
            if not self._default_suite_name or self._default_suite_name == "tests":
                self._default_suite_name = suite.name

    def on_test_pass(self, result: TestResult) -> None:
        if result.is_eval:
            return
        self._record(result, passed=True)

    def on_test_fail(self, result: TestResult) -> None:
        if result.is_eval:
            return
        self._record(result, passed=False)

    def on_session_end(self, _result: SessionResult) -> None:
        if not self._history_enabled or not self._suites:
            return

        suites_data: dict[str, Any] = {}
        for suite_name, cases in self._suites.items():
            total = len(cases)
            passed = sum(1 for c in cases.values() if c["passed"])
            suites_data[suite_name] = {
                "kind": self._suite_kinds.get(suite_name, "test"),
                "total_cases": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round(passed / total, 4) if total else 0,
                "duration": round(sum(c["duration"] for c in cases.values()), 2),
                "cases": cases,
            }

        entry: dict[str, Any] = {
            "run_id": str(uuid.uuid4()),
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "git": collect_git_info(),
            "environment": collect_env_info(),
            "metadata": self._metadata,
            "evals": None,
            "suites": suites_data,
        }
        append_entry(self._history_file, entry)

    def _record(self, result: TestResult, *, passed: bool) -> None:
        suite_name = self._get_suite_name(result)
        if suite_name not in self._suites:
            self._suites[suite_name] = {}
        self._suites[suite_name][result.name] = {
            "passed": passed,
            "duration": round(result.duration, 3),
        }

    def _get_suite_name(self, result: TestResult) -> str:
        if result.suite_path:
            return result.suite_path.root_name
        return self._default_suite_name
