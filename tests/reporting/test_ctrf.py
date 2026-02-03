from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from jsonschema import validate

from protest.entities import SessionResult, SuitePath, TestResult
from protest.reporting.ctrf import CTRFReporter

if TYPE_CHECKING:
    from collections.abc import Callable


class TestCTRFReportStructure:
    def test_minimal_report_has_required_fields(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given an empty session, when report is generated, then it has all required CTRF fields."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()

        assert report["reportFormat"] == "CTRF"
        assert report["specVersion"] == "0.0.0"
        assert "reportId" in report
        assert "timestamp" in report
        assert report["generatedBy"] == "ProTest"

        results = report["results"]
        assert results["tool"]["name"] == "ProTest"
        assert "version" in results["tool"]

        summary = results["summary"]
        assert summary["tests"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["skipped"] == 0
        assert summary["pending"] == 0
        assert summary["other"] == 0
        assert "start" in summary
        assert "stop" in summary
        assert "duration" in summary

        assert results["tests"] == []
        assert "environment" in results


class TestCTRFTestRecording:
    @pytest.mark.parametrize(
        "test_status,handler_method,result_kwargs,expected_status,expected_raw_status",
        [
            pytest.param(
                "passed",
                "on_test_pass",
                {
                    "name": "test_example",
                    "node_id": "mod::test_example",
                    "duration": 0.150,
                },
                "passed",
                None,
                id="passed_test",
            ),
            pytest.param(
                "skipped",
                "on_test_skip",
                {
                    "name": "test_skip",
                    "node_id": "mod::test_skip",
                    "duration": 0.0,
                    "skip_reason": "not implemented",
                },
                "skipped",
                None,
                id="skipped_test",
            ),
            pytest.param(
                "xfail",
                "on_test_xfail",
                {
                    "name": "test_xfail",
                    "node_id": "mod::test_xfail",
                    "duration": 0.010,
                    "xfail_reason": "known bug",
                },
                "failed",
                "xfail",
                id="xfail_test",
            ),
            pytest.param(
                "xpass",
                "on_test_xpass",
                {
                    "name": "test_xpass",
                    "node_id": "mod::test_xpass",
                    "duration": 0.010,
                    "xfail_reason": "should fail",
                },
                "failed",
                "xpass",
                id="xpass_test",
            ),
        ],
    )
    def test_test_status_recording(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
        test_status: str,
        handler_method: str,
        result_kwargs: dict[str, Any],
        expected_status: str,
        expected_raw_status: str | None,
    ) -> None:
        """Given a test with specific status, when recorded, then CTRF status is correctly set."""
        ctrf_reporter.on_session_start()
        result = TestResult(**result_kwargs)
        getattr(ctrf_reporter, handler_method)(result)
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["name"] == result_kwargs["name"]
        assert test["status"] == expected_status
        if expected_raw_status:
            assert test["rawStatus"] == expected_raw_status
        else:
            assert "rawStatus" not in test

    def test_failed_test_with_traceback(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given a failed test with error, when recorded, then message and trace are included."""
        ctrf_reporter.on_session_start()
        error = AssertionError("expected 42, got 0")
        ctrf_reporter.on_test_fail(
            TestResult(
                name="test_math",
                node_id="mod::test_math",
                duration=0.050,
                error=error,
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["name"] == "test_math"
        assert test["status"] == "failed"
        expected_duration_ms = 50
        assert test["duration"] == expected_duration_ms
        assert "expected 42, got 0" in test["message"]
        assert "AssertionError" in test["trace"]

    @pytest.mark.parametrize(
        "error_type,result_kwargs,expected_raw_status",
        [
            pytest.param(
                "fixture_error",
                {"is_fixture_error": True, "error": RuntimeError("connection failed")},
                "error",
                id="fixture_error",
            ),
            pytest.param(
                "timeout",
                {"timeout": 5.0, "error": TimeoutError("timed out")},
                "timeout",
                id="timeout_error",
            ),
        ],
    )
    def test_special_failure_raw_status(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
        error_type: str,
        result_kwargs: dict[str, Any],
        expected_raw_status: str,
    ) -> None:
        """Given a special failure type, when recorded, then rawStatus reflects the error type."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_test_fail(
            TestResult(
                name=f"test_{error_type}",
                node_id=f"mod::test_{error_type}",
                duration=0.010,
                **result_kwargs,
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["status"] == "failed"
        assert test["rawStatus"] == expected_raw_status


class TestCTRFSuiteHandling:
    def test_suite_path_as_array(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given a test with nested suite path, when recorded, then suite is array of parts."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_test_pass(
            TestResult(
                name="test_login",
                node_id="mod::API::Auth::test_login",
                suite_path=SuitePath("API::Auth"),
                duration=0.100,
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=1, failed=0))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["suite"] == ["API", "Auth"]

    def test_suite_count_in_summary(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given tests in multiple suites, when report generated, then suite count is correct."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_test_pass(
            TestResult(
                name="test_a",
                node_id="mod::Suite1::test_a",
                suite_path=SuitePath("Suite1"),
                duration=0.010,
            )
        )
        ctrf_reporter.on_test_pass(
            TestResult(
                name="test_b",
                node_id="mod::Suite2::test_b",
                suite_path=SuitePath("Suite2"),
                duration=0.010,
            )
        )
        ctrf_reporter.on_test_pass(
            TestResult(
                name="test_c",
                node_id="mod::Suite1::test_c",
                suite_path=SuitePath("Suite1"),
                duration=0.010,
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=3, failed=0))

        report = read_ctrf_report()
        expected_suite_count = 2

        assert report["results"]["summary"]["suites"] == expected_suite_count


class TestCTRFOutput:
    def test_stdout_as_lines(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given test with multiline output, when recorded, then stdout is array of lines."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_test_fail(
            TestResult(
                name="test_output",
                node_id="mod::test_output",
                duration=0.010,
                error=AssertionError("fail"),
                output="line 1\nline 2\nline 3",
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["stdout"] == ["line 1", "line 2", "line 3"]


class TestCTRFTimestamps:
    def test_timestamps_in_milliseconds(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given a session, when report generated, then timestamps are epoch milliseconds."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        summary = report["results"]["summary"]

        expected_min_timestamp = 1_000_000_000_000
        assert summary["start"] > expected_min_timestamp
        assert summary["stop"] > expected_min_timestamp
        assert summary["stop"] >= summary["start"]

    @pytest.mark.parametrize(
        "duration_seconds,expected_ms",
        [
            pytest.param(0.001, 1, id="millisecond"),
            pytest.param(1.5, 1500, id="seconds_with_fraction"),
        ],
    )
    def test_duration_conversion(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
        duration_seconds: float,
        expected_ms: int,
    ) -> None:
        """Given test duration in seconds, when recorded, then CTRF duration is in milliseconds."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_test_pass(
            TestResult(
                name="test_duration",
                node_id="mod::test_duration",
                duration=duration_seconds,
            )
        )
        ctrf_reporter.on_session_end(SessionResult(passed=1, failed=0))

        report = read_ctrf_report()
        test = report["results"]["tests"][0]

        assert test["duration"] == expected_ms


class TestCTRFEnvironment:
    def test_environment_populated(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given a session, when report generated, then environment info is included."""
        ctrf_reporter.on_session_start()
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        env = report["results"]["environment"]

        assert "osPlatform" in env
        assert "osVersion" in env

    @patch("protest.reporting.ctrf.subprocess.run")
    def test_git_branch_included_when_available(
        self,
        mock_run: Any,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given git is available, when report generated, then branch name is included."""
        mock_run.return_value.stdout = "feature-branch\n"
        mock_run.return_value.returncode = 0

        ctrf_reporter.on_session_start()
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        env = report["results"]["environment"]

        assert env.get("branchName") == "feature-branch"


class TestCTRFFileOutput:
    def test_file_created(self, tmp_path: Path) -> None:
        """Given output path with missing directories, when session ends, then file is created."""
        output_path = tmp_path / "output" / "ctrf-report.json"
        reporter = CTRFReporter(output_path=output_path)

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        assert output_path.exists()
        report = json.loads(output_path.read_text())
        assert report["reportFormat"] == "CTRF"


class TestCTRFGitErrors:
    @pytest.mark.parametrize(
        "exception_type,exception_args",
        [
            pytest.param(FileNotFoundError, ("git not found",), id="file_not_found"),
            pytest.param("CalledProcessError", (128, "git"), id="called_process_error"),
        ],
    )
    def test_git_error_handling(
        self,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
        exception_type: type | str,
        exception_args: tuple[Any, ...],
    ) -> None:
        """Given git command fails, when report generated, then branchName is not included."""
        if exception_type == "CalledProcessError":
            exc = subprocess.CalledProcessError(*exception_args)
        else:
            exc = exception_type(*exception_args)  # type: ignore[operator]

        with patch("protest.reporting.ctrf.subprocess.run", side_effect=exc):
            ctrf_reporter.on_session_start()
            ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        env = report["results"]["environment"]

        assert "branchName" not in env


class TestCTRFVersionError:
    @patch("importlib.metadata.version")
    def test_version_returns_unknown_on_error(
        self,
        mock_version: Any,
        ctrf_reporter: CTRFReporter,
        read_ctrf_report: Callable[[], dict[str, Any]],
    ) -> None:
        """Given importlib.metadata fails, when report generated, then version is 'unknown'."""
        mock_version.side_effect = Exception("package not found")

        ctrf_reporter.on_session_start()
        ctrf_reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = read_ctrf_report()
        tool = report["results"]["tool"]

        assert tool["version"] == "unknown"


CTRF_SCHEMA_PATH = Path(__file__).parent / "ctrf.schema.json"


class TestCTRFSchemaValidation:
    @pytest.fixture
    def ctrf_schema(self) -> dict[str, Any]:
        return json.loads(CTRF_SCHEMA_PATH.read_text())

    def test_full_report_validates_against_official_schema(
        self, tmp_path: Path, ctrf_schema: dict[str, Any]
    ) -> None:
        """Given comprehensive report, when validated against CTRF schema, then no errors."""

        reporter = CTRFReporter(output_path=tmp_path / "ctrf-report.json")
        reporter.on_session_start()

        reporter.on_test_pass(
            TestResult(
                name="test_passed",
                node_id="mod::Suite::test_passed",
                suite_path=SuitePath("Suite"),
                duration=0.150,
            )
        )
        reporter.on_test_fail(
            TestResult(
                name="test_failed",
                node_id="mod::test_failed",
                duration=0.050,
                error=AssertionError("expected 1, got 2"),
                output="debug output",
            )
        )
        reporter.on_test_skip(
            TestResult(
                name="test_skipped",
                node_id="mod::test_skipped",
                duration=0.0,
                skip_reason="not implemented",
            )
        )
        reporter.on_test_xfail(
            TestResult(
                name="test_xfail",
                node_id="mod::test_xfail",
                duration=0.010,
                xfail_reason="known bug",
            )
        )
        reporter.on_test_xpass(
            TestResult(name="test_xpass", node_id="mod::test_xpass", duration=0.010)
        )
        reporter.on_test_fail(
            TestResult(
                name="test_fixture_error",
                node_id="mod::test_fixture_error",
                duration=0.005,
                error=RuntimeError("db connection failed"),
                is_fixture_error=True,
            )
        )
        reporter.on_test_fail(
            TestResult(
                name="test_timeout",
                node_id="mod::test_timeout",
                duration=5.0,
                error=TimeoutError("exceeded"),
                timeout=5.0,
            )
        )

        reporter.on_session_end(
            SessionResult(
                passed=1,
                failed=3,
                skipped=1,
                xfailed=1,
                xpassed=1,
                errors=1,
                duration=5.5,
            )
        )

        report = json.loads((tmp_path / "ctrf-report.json").read_text())

        validate(instance=report, schema=ctrf_schema)
