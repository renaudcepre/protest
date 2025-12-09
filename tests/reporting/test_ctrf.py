from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from protest.entities import SessionResult, TestResult
from protest.reporting.ctrf import CTRFReporter

if TYPE_CHECKING:
    from pathlib import Path


class TestCTRFReportStructure:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def test_minimal_report_has_required_fields(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = json.loads((tmp_path / "ctrf-report.json").read_text())

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
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    def test_passed_test(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_pass(
            TestResult(name="test_example", node_id="mod::test_example", duration=0.150)
        )
        reporter.on_session_end(SessionResult(passed=1, failed=0))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["name"] == "test_example"
        assert test["status"] == "passed"
        assert test["duration"] == 150
        assert "rawStatus" not in test

    def test_failed_test_with_traceback(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        error = AssertionError("expected 42, got 0")
        reporter.on_test_fail(
            TestResult(
                name="test_math",
                node_id="mod::test_math",
                duration=0.050,
                error=error,
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["name"] == "test_math"
        assert test["status"] == "failed"
        assert test["duration"] == 50
        assert "expected 42, got 0" in test["message"]
        assert "AssertionError" in test["trace"]

    def test_skipped_test(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_skip(
            TestResult(
                name="test_skip",
                node_id="mod::test_skip",
                duration=0.0,
                skip_reason="not implemented",
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=0, skipped=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["name"] == "test_skip"
        assert test["status"] == "skipped"

    def test_xfail_maps_to_failed(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_xfail(
            TestResult(
                name="test_xfail",
                node_id="mod::test_xfail",
                duration=0.010,
                xfail_reason="known bug",
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=0, xfailed=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["name"] == "test_xfail"
        assert test["status"] == "failed"
        assert test["rawStatus"] == "xfail"
        assert report["results"]["summary"]["failed"] == 1

    def test_xpass_maps_to_failed(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_xpass(
            TestResult(
                name="test_xpass",
                node_id="mod::test_xpass",
                duration=0.010,
                xfail_reason="should fail",
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=0, xpassed=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["name"] == "test_xpass"
        assert test["status"] == "failed"
        assert test["rawStatus"] == "xpass"

    def test_fixture_error_raw_status(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        reporter.on_test_fail(
            TestResult(
                name="test_db",
                node_id="mod::test_db",
                duration=0.010,
                error=RuntimeError("connection failed"),
                is_fixture_error=True,
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=0, errors=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["status"] == "failed"
        assert test["rawStatus"] == "error"

    def test_timeout_raw_status(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_fail(
            TestResult(
                name="test_slow",
                node_id="mod::test_slow",
                duration=5.0,
                error=TimeoutError("timed out"),
                timeout=5.0,
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["status"] == "failed"
        assert test["rawStatus"] == "timeout"


class TestCTRFSuiteHandling:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    def test_suite_path_as_array(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_pass(
            TestResult(
                name="test_login",
                node_id="mod::API::Auth::test_login",
                suite_path="API::Auth",
                duration=0.100,
            )
        )
        reporter.on_session_end(SessionResult(passed=1, failed=0))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["suite"] == ["API", "Auth"]

    def test_suite_count_in_summary(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        reporter.on_test_pass(
            TestResult(
                name="test_a",
                node_id="mod::Suite1::test_a",
                suite_path="Suite1",
                duration=0.010,
            )
        )
        reporter.on_test_pass(
            TestResult(
                name="test_b",
                node_id="mod::Suite2::test_b",
                suite_path="Suite2",
                duration=0.010,
            )
        )
        reporter.on_test_pass(
            TestResult(
                name="test_c",
                node_id="mod::Suite1::test_c",
                suite_path="Suite1",
                duration=0.010,
            )
        )
        reporter.on_session_end(SessionResult(passed=3, failed=0))

        report = self._get_report(tmp_path)
        expected_suite_count = 2
        assert report["results"]["summary"]["suites"] == expected_suite_count


class TestCTRFOutput:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    def test_stdout_as_lines(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_fail(
            TestResult(
                name="test_output",
                node_id="mod::test_output",
                duration=0.010,
                error=AssertionError("fail"),
                output="line 1\nline 2\nline 3",
            )
        )
        reporter.on_session_end(SessionResult(passed=0, failed=1))

        report = self._get_report(tmp_path)
        test = report["results"]["tests"][0]

        assert test["stdout"] == ["line 1", "line 2", "line 3"]


class TestCTRFTimestamps:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    def test_timestamps_in_milliseconds(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        summary = report["results"]["summary"]

        expected_min_timestamp = 1_000_000_000_000
        assert summary["start"] > expected_min_timestamp
        assert summary["stop"] > expected_min_timestamp
        assert summary["stop"] >= summary["start"]

    def test_duration_conversion(self, reporter: CTRFReporter, tmp_path: Path) -> None:
        reporter.on_session_start()
        reporter.on_test_pass(
            TestResult(name="test_fast", node_id="mod::test_fast", duration=0.001)
        )
        reporter.on_test_pass(
            TestResult(name="test_slow", node_id="mod::test_slow", duration=1.5)
        )
        reporter.on_session_end(SessionResult(passed=2, failed=0))

        report = self._get_report(tmp_path)
        tests = report["results"]["tests"]

        assert tests[0]["duration"] == 1
        expected_slow_duration_ms = 1500
        assert tests[1]["duration"] == expected_slow_duration_ms


class TestCTRFEnvironment:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    def test_environment_populated(
        self, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        env = report["results"]["environment"]

        assert "osPlatform" in env
        assert "osVersion" in env

    @patch("protest.reporting.ctrf.subprocess.run")
    def test_git_branch_included_when_available(
        self, mock_run: Any, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        mock_run.return_value.stdout = "feature-branch\n"
        mock_run.return_value.returncode = 0

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        env = report["results"]["environment"]

        assert env.get("branchName") == "feature-branch"


class TestCTRFFileOutput:
    def test_file_created(self, tmp_path: Path) -> None:
        output_path = tmp_path / "output" / "ctrf-report.json"
        reporter = CTRFReporter(output_path=output_path)

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        assert output_path.exists()
        report = json.loads(output_path.read_text())
        assert report["reportFormat"] == "CTRF"


class TestCTRFGitErrors:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    @patch("protest.reporting.ctrf.subprocess.run")
    def test_git_branch_returns_none_on_file_not_found(
        self, mock_run: Any, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        mock_run.side_effect = FileNotFoundError("git not found")

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        env = report["results"]["environment"]

        assert "branchName" not in env

    @patch("protest.reporting.ctrf.subprocess.run")
    def test_git_commit_returns_none_on_file_not_found(
        self, mock_run: Any, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        mock_run.side_effect = FileNotFoundError("git not found")

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        env = report["results"]["environment"]

        assert "commit" not in env

    @patch("protest.reporting.ctrf.subprocess.run")
    def test_git_branch_returns_none_on_called_process_error(
        self, mock_run: Any, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        import subprocess  # noqa: PLC0415

        mock_run.side_effect = subprocess.CalledProcessError(128, "git")

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        env = report["results"]["environment"]

        assert "branchName" not in env


class TestCTRFVersionError:
    @pytest.fixture
    def reporter(self, tmp_path: Path) -> CTRFReporter:
        return CTRFReporter(output_path=tmp_path / "ctrf-report.json")

    def _get_report(self, tmp_path: Path) -> dict[str, Any]:
        return json.loads((tmp_path / "ctrf-report.json").read_text())

    @patch("importlib.metadata.version")
    def test_version_returns_unknown_on_error(
        self, mock_version: Any, reporter: CTRFReporter, tmp_path: Path
    ) -> None:
        mock_version.side_effect = Exception("package not found")

        reporter.on_session_start()
        reporter.on_session_end(SessionResult(passed=0, failed=0))

        report = self._get_report(tmp_path)
        tool = report["results"]["tool"]

        assert tool["version"] == "unknown"


CTRF_SCHEMA_URL = "https://raw.githubusercontent.com/ctrf-io/ctrf/main/specification/schema-0.0.0.json"


class TestCTRFSchemaValidation:
    @pytest.fixture
    def ctrf_schema(self) -> dict[str, Any]:
        import urllib.request  # noqa: PLC0415

        with urllib.request.urlopen(CTRF_SCHEMA_URL) as response:  # noqa: S310
            return json.loads(response.read())

    def test_full_report_validates_against_official_schema(
        self, tmp_path: Path, ctrf_schema: dict[str, Any]
    ) -> None:
        from jsonschema import validate  # noqa: PLC0415

        reporter = CTRFReporter(output_path=tmp_path / "ctrf-report.json")
        reporter.on_session_start()

        reporter.on_test_pass(
            TestResult(
                name="test_passed",
                node_id="mod::Suite::test_passed",
                suite_path="Suite",
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
            TestResult(
                name="test_xpass",
                node_id="mod::test_xpass",
                duration=0.010,
            )
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
