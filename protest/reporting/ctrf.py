from __future__ import annotations

import json
import platform
import subprocess
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, NotRequired, TypedDict

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from pathlib import Path

    from protest.entities import SessionResult, TestResult


class CTRFTool(TypedDict):
    name: str
    version: NotRequired[str]


class CTRFSummary(TypedDict):
    tests: int
    passed: int
    failed: int
    skipped: int
    pending: int
    other: int
    start: int
    stop: int
    duration: NotRequired[int]
    suites: NotRequired[int]


class CTRFTest(TypedDict):
    name: str
    status: str
    duration: int
    suite: NotRequired[list[str]]
    message: NotRequired[str]
    trace: NotRequired[str]
    tags: NotRequired[list[str]]
    filePath: NotRequired[str]
    rawStatus: NotRequired[str]
    stdout: NotRequired[list[str]]


class CTRFEnvironment(TypedDict, total=False):
    osPlatform: str
    osVersion: str
    branchName: str
    commit: str


class CTRFResults(TypedDict):
    tool: CTRFTool
    summary: CTRFSummary
    tests: list[CTRFTest]
    environment: NotRequired[CTRFEnvironment]


class CTRFReport(TypedDict):
    reportFormat: str
    specVersion: str
    results: CTRFResults
    reportId: NotRequired[str]
    timestamp: NotRequired[str]
    generatedBy: NotRequired[str]


class CTRFReporter(PluginBase):
    """CTRF JSON reporter for CI/CD integration."""

    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._tests: list[CTRFTest] = []
        self._start_time: int = 0
        self._suites: set[str] = set()
        self._counts = {"passed": 0, "failed": 0, "skipped": 0}

    def on_session_start(self) -> None:
        self._start_time = int(time.time() * 1000)

    def on_test_pass(self, result: TestResult) -> None:
        self._record_test(result, "passed")
        self._counts["passed"] += 1

    def on_test_fail(self, result: TestResult) -> None:
        raw_status = self._determine_raw_status(result)
        self._record_test(result, "failed", raw_status)
        self._counts["failed"] += 1

    def on_test_skip(self, result: TestResult) -> None:
        self._record_test(result, "skipped")
        self._counts["skipped"] += 1

    def on_test_xfail(self, result: TestResult) -> None:
        self._record_test(result, "failed", raw_status="xfail")
        self._counts["failed"] += 1

    def on_test_xpass(self, result: TestResult) -> None:
        self._record_test(result, "failed", raw_status="xpass")
        self._counts["failed"] += 1

    def _determine_raw_status(self, result: TestResult) -> str | None:
        if result.is_fixture_error:
            return "error"
        if result.timeout is not None and isinstance(result.error, TimeoutError):
            return "timeout"
        return None

    def _record_test(
        self,
        result: TestResult,
        status: str,
        raw_status: str | None = None,
    ) -> None:
        test: CTRFTest = {
            "name": result.name,
            "status": status,
            "duration": int(result.duration * 1000),
        }

        if result.suite_path:
            test["suite"] = result.suite_path.split("::")
            self._suites.add(result.suite_path)

        if result.error:
            test["message"] = str(result.error)
            test["trace"] = "".join(
                traceback.format_exception(
                    type(result.error), result.error, result.error.__traceback__
                )
            )

        if result.output:
            test["stdout"] = result.output.splitlines()

        if raw_status:
            test["rawStatus"] = raw_status

        self._tests.append(test)

    def on_session_end(self, result: SessionResult) -> None:
        stop_time = int(time.time() * 1000)

        report: CTRFReport = {
            "reportFormat": "CTRF",
            "specVersion": "0.0.0",
            "reportId": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "ProTest",
            "results": {
                "tool": {
                    "name": "ProTest",
                    "version": self._get_version(),
                },
                "summary": {
                    "tests": len(self._tests),
                    "passed": self._counts["passed"],
                    "failed": self._counts["failed"],
                    "skipped": self._counts["skipped"],
                    "pending": 0,
                    "other": 0,
                    "start": self._start_time,
                    "stop": stop_time,
                    "duration": stop_time - self._start_time,
                    "suites": len(self._suites),
                },
                "tests": self._tests,
                "environment": self._build_environment(),
            },
        }

        self._write_report(report)

    def _build_environment(self) -> CTRFEnvironment:
        env: CTRFEnvironment = {
            "osPlatform": platform.system().lower(),
            "osVersion": platform.release(),
        }
        branch = self._get_git_branch()
        if branch:
            env["branchName"] = branch
        commit = self._get_git_commit()
        if commit:
            env["commit"] = commit
        return env

    def _get_git_branch(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _get_git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def _get_version(self) -> str:
        try:
            from importlib.metadata import version  # noqa: PLC0415

            return version("protest")
        except Exception:
            return "unknown"

    def _write_report(self, report: CTRFReport) -> None:
        self._output_path.parent.mkdir(exist_ok=True, parents=True)
        self._output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
