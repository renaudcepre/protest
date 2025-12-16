from __future__ import annotations

import pytest

from protest.entities import (
    FixtureInfo,
    HandlerInfo,
    SessionResult,
    TestResult,
    TestRetryInfo,
)
from protest.events.types import Event
from protest.reporting.ascii import (
    AsciiReporter,
    _extract_suite_from_node_id,
    _format_duration,
    _format_test_name,
)
from tests.factories.test_items import make_test_item


@pytest.fixture
def ascii_reporter() -> AsciiReporter:
    """Provide a fresh AsciiReporter for each test."""
    return AsciiReporter()


class TestFormatDuration:
    @pytest.mark.parametrize(
        "duration,expected",
        [
            pytest.param(0.0001, "<1ms", id="sub_millisecond"),
            pytest.param(0, "<1ms", id="zero"),
            pytest.param(0.001, "1ms", id="one_millisecond"),
            pytest.param(0.5, "500ms", id="half_second"),
            pytest.param(0.123, "123ms", id="fractional_ms"),
            pytest.param(2.5, "2.50s", id="seconds"),
            pytest.param(1.0, "1.00s", id="one_second"),
        ],
    )
    def test_format_duration(self, duration: float, expected: str) -> None:
        """Given a duration in seconds, when formatted, then output matches expected format."""
        assert _format_duration(duration) == expected


class TestFormatTestName:
    @pytest.mark.parametrize(
        "name,node_id,expected",
        [
            pytest.param("test_foo", "module::test_foo", "test_foo", id="simple"),
            pytest.param(
                "test_x",
                "module::test_x[param1-param2]",
                "test_x[param1-param2]",
                id="with_params",
            ),
        ],
    )
    def test_format_test_name(self, name: str, node_id: str, expected: str) -> None:
        """Given a TestResult, when formatted, then name includes params if present."""
        result = TestResult(name=name, node_id=node_id, duration=0.1)
        assert _format_test_name(result) == expected


class TestAsciiReporterHooks:
    def test_on_session_start(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a session, when started, then 'Starting session' is printed."""
        ascii_reporter.on_session_start()
        captured = capsys.readouterr()
        assert "Starting session" in captured.out

    def test_on_suite_start(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a suite, when started, then suite name is printed."""
        ascii_reporter.on_suite_start("MySuite")
        captured = capsys.readouterr()
        assert "MySuite" in captured.out

    def test_on_test_pass(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a passing test, when reported, then 'OK' marker and duration are shown."""
        result = TestResult(
            name="test_example", node_id="mod::test_example", duration=0.05
        )
        ascii_reporter.on_test_pass(result)
        captured = capsys.readouterr()
        assert "OK test_example" in captured.out
        assert "50ms" in captured.out

    def test_on_test_fail(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a failing test, when reported, then 'XX' marker and error message are shown."""
        result = TestResult(
            name="test_failing",
            node_id="mod::test_failing",
            duration=0.01,
            error=AssertionError("oops"),
        )
        ascii_reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "XX test_failing" in captured.out
        assert "oops" in captured.out

    def test_on_test_fail_with_output(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a failing test with captured output, when reported, then output lines are shown."""
        result = TestResult(
            name="test_failing",
            node_id="mod::test_failing",
            duration=0.01,
            error=AssertionError("oops"),
            output="debug line 1\ndebug line 2",
        )
        ascii_reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "| debug line 1" in captured.out
        assert "| debug line 2" in captured.out

    def test_on_test_fail_fixture_error(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a fixture error, when reported, then '!!' marker is shown."""
        result = TestResult(
            name="test_x",
            node_id="mod::test_x",
            duration=0.01,
            error=RuntimeError("db down"),
            is_fixture_error=True,
        )
        ascii_reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "!! test_x" in captured.out

    def test_on_waiting_handlers(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given async handlers pending, when reported, then count is shown."""
        ascii_reporter.on_waiting_handlers(3)
        captured = capsys.readouterr()
        assert "Async handlers (3)" in captured.out

    @pytest.mark.parametrize(
        "is_async,error,expected_marker,expected_text",
        [
            pytest.param(True, None, "OK", "500ms", id="async_success"),
            pytest.param(
                True, RuntimeError("timeout"), "XX", "timeout", id="async_error"
            ),
        ],
    )
    def test_on_handler_end_async(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        is_async: bool,
        error: Exception | None,
        expected_marker: str,
        expected_text: str,
    ) -> None:
        """Given an async handler, when completed, then marker and status are shown."""
        info = HandlerInfo(
            name="send_slack",
            event=Event.SESSION_END,
            is_async=is_async,
            duration=0.5,
            error=error,
        )
        ascii_reporter.on_handler_end(info)
        captured = capsys.readouterr()
        assert f"{expected_marker} send_slack" in captured.out
        assert expected_text in captured.out

    def test_on_handler_end_sync_ignored(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a sync handler, when completed, then nothing is printed."""
        info = HandlerInfo(
            name="sync_handler", event=Event.SESSION_END, is_async=False, duration=0.1
        )
        ascii_reporter.on_handler_end(info)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAsciiReporterSessionComplete:
    @pytest.mark.parametrize(
        "passed,failed,errors,expected_marker,expected_parts",
        [
            pytest.param(5, 0, 0, "OK ALL PASSED", ["5/5 passed"], id="all_passed"),
            pytest.param(
                3, 1, 0, "XX FAILURES", ["3/4 passed", "1 failed"], id="with_failures"
            ),
            pytest.param(3, 0, 1, "XX FAILURES", ["1 errors"], id="with_errors"),
            pytest.param(
                2,
                1,
                1,
                "XX FAILURES",
                ["2/4 passed", "1 failed", "1 errors"],
                id="failures_and_errors",
            ),
        ],
    )
    def test_session_complete_summary(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        passed: int,
        failed: int,
        errors: int,
        expected_marker: str,
        expected_parts: list[str],
    ) -> None:
        """Given session results, when completed, then summary shows correct status."""
        result = SessionResult(
            passed=passed, failed=failed, errors=errors, duration=1.0
        )
        ascii_reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert expected_marker in captured.out
        for part in expected_parts:
            assert part in captured.out


class TestExtractSuiteFromNodeId:
    @pytest.mark.parametrize(
        "node_id,expected",
        [
            pytest.param("module::Suite::test_name", "Suite", id="single_suite"),
            pytest.param(
                "module::Parent::Child::test_name", "Parent::Child", id="nested_suite"
            ),
            pytest.param("module::test_name", None, id="no_suite"),
            pytest.param("test_name", None, id="single_part"),
        ],
    )
    def test_extract_suite(self, node_id: str, expected: str | None) -> None:
        """Given a node_id, when extracted, then suite path is correct."""
        result = _extract_suite_from_node_id(node_id)
        assert result == expected


class TestFormatTestNameWithSuite:
    @pytest.mark.parametrize(
        "suite_path,include_suite,expected",
        [
            pytest.param("MySuite", True, "MySuite::test_foo", id="include_suite"),
            pytest.param("MySuite", False, "test_foo", id="exclude_suite"),
            pytest.param(
                "Parent::Child", True, "Parent::Child::test_foo", id="nested_suite"
            ),
        ],
    )
    def test_format_with_suite(
        self, suite_path: str, include_suite: bool, expected: str
    ) -> None:
        """Given a TestResult with suite, when formatted, then suite is included based on flag."""
        result = TestResult(
            name="test_foo",
            node_id=f"module::{suite_path}::test_foo",
            duration=0.1,
            suite_path=suite_path,
        )
        formatted = _format_test_name(result, include_suite=include_suite)
        assert formatted == expected


class TestAsciiReporterParallelMode:
    def test_on_collection_finish_sets_parallel_mode(
        self, ascii_reporter: AsciiReporter
    ) -> None:
        """Given multiple tests collected, when collection finishes, then parallel mode is enabled."""
        item_count = 5
        items = [make_test_item(f"test_{idx}") for idx in range(item_count)]
        ascii_reporter.on_collection_finish(items)
        assert ascii_reporter._is_parallel is True

    def test_on_collection_finish_single_item_not_parallel(
        self, ascii_reporter: AsciiReporter
    ) -> None:
        """Given single test collected, when collection finishes, then parallel mode is disabled."""
        items = [make_test_item("test_single")]
        ascii_reporter.on_collection_finish(items)
        assert ascii_reporter._is_parallel is False

    def test_suite_header_not_printed_in_parallel_mode(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given parallel mode, when suite starts, then header is not printed."""
        item_count = 5
        items = [make_test_item(f"test_{idx}") for idx in range(item_count)]
        ascii_reporter.on_collection_finish(items)

        ascii_reporter.on_suite_start("MySuite")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAsciiReporterSessionHooks:
    @pytest.mark.parametrize(
        "hook_method,hook_args,expected_text",
        [
            pytest.param(
                "on_session_setup_start", (), "session setup", id="setup_start"
            ),
            pytest.param(
                "on_session_teardown_start", (), "teardown", id="teardown_start"
            ),
        ],
    )
    def test_session_lifecycle_hooks(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        hook_method: str,
        hook_args: tuple,
        expected_text: str,
    ) -> None:
        """Given a lifecycle hook, when called, then expected text is printed."""
        getattr(ascii_reporter, hook_method)(*hook_args)
        captured = capsys.readouterr()
        assert expected_text in captured.out.lower()

    @pytest.mark.parametrize(
        "hook_method,duration,expected_duration_str",
        [
            pytest.param("on_session_setup_done", 0.5, "500ms", id="setup_done"),
            pytest.param("on_session_teardown_done", 0.25, "250ms", id="teardown_done"),
        ],
    )
    def test_session_done_hooks(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        hook_method: str,
        duration: float,
        expected_duration_str: str,
    ) -> None:
        """Given a done hook with duration, when called, then duration is printed."""
        getattr(ascii_reporter, hook_method)(duration)
        captured = capsys.readouterr()
        assert expected_duration_str in captured.out


class TestAsciiReporterTestStatus:
    @pytest.mark.parametrize(
        "handler_method,result_kwargs,expected_marker,expected_texts",
        [
            pytest.param(
                "on_test_skip",
                {
                    "name": "test_skipped",
                    "node_id": "mod::test_skipped",
                    "duration": 0.0,
                    "skip_reason": "Not implemented",
                },
                "--",
                ["test_skipped", "Not implemented"],
                id="skip",
            ),
            pytest.param(
                "on_test_xfail",
                {
                    "name": "test_xfail",
                    "node_id": "mod::test_xfail",
                    "duration": 0.05,
                    "xfail_reason": "Known bug",
                    "error": AssertionError("expected"),
                },
                "xf",
                ["test_xfail", "Known bug", "50ms"],
                id="xfail",
            ),
            pytest.param(
                "on_test_xpass",
                {
                    "name": "test_xpass",
                    "node_id": "mod::test_xpass",
                    "duration": 0.1,
                    "xfail_reason": "Was supposed to fail",
                },
                "XP",
                ["test_xpass", "UNEXPECTED PASS", "100ms"],
                id="xpass",
            ),
        ],
    )
    def test_test_status_display(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        handler_method: str,
        result_kwargs: dict,
        expected_marker: str,
        expected_texts: list[str],
    ) -> None:
        """Given a test with special status, when reported, then marker and info are shown."""
        result = TestResult(**result_kwargs)
        getattr(ascii_reporter, handler_method)(result)
        captured = capsys.readouterr()
        assert f"{expected_marker} " in captured.out
        for text in expected_texts:
            assert text in captured.out

    def test_on_test_fail_timeout(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Given a timeout failure, when reported, then 'TO' marker and TIMEOUT are shown."""
        result = TestResult(
            name="test_slow",
            node_id="mod::test_slow",
            duration=5.0,
            error=TimeoutError("Test exceeded timeout"),
            timeout=5.0,
        )
        ascii_reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "TO test_slow" in captured.out
        assert "TIMEOUT" in captured.out
        assert "5" in captured.out


class TestAsciiReporterSummaryParts:
    @pytest.mark.parametrize(
        "result_kwargs,expected_texts",
        [
            pytest.param(
                {"passed": 4, "failed": 0, "errors": 0, "skipped": 2, "duration": 1.0},
                ["2 skipped"],
                id="with_skipped",
            ),
            pytest.param(
                {"passed": 3, "failed": 0, "errors": 0, "xfailed": 1, "duration": 1.0},
                ["1 xfailed"],
                id="with_xfailed",
            ),
            pytest.param(
                {"passed": 3, "failed": 0, "errors": 0, "xpassed": 1, "duration": 1.0},
                ["XX FAILURES", "1 xpassed"],
                id="with_xpassed",
            ),
            pytest.param(
                {
                    "passed": 2,
                    "failed": 1,
                    "errors": 1,
                    "skipped": 1,
                    "xfailed": 1,
                    "xpassed": 1,
                    "duration": 5.0,
                },
                [
                    "2/7 passed",
                    "1 skipped",
                    "1 xfailed",
                    "1 xpassed",
                    "1 failed",
                    "1 errors",
                ],
                id="all_status_types",
            ),
        ],
    )
    def test_summary_parts(
        self,
        ascii_reporter: AsciiReporter,
        capsys: pytest.CaptureFixture[str],
        result_kwargs: dict,
        expected_texts: list[str],
    ) -> None:
        """Given session results, when summary printed, then all status parts are shown."""
        result = SessionResult(**result_kwargs)
        ascii_reporter.on_session_complete(result)
        captured = capsys.readouterr()
        for text in expected_texts:
            assert text in captured.out


class TestAsciiReporterAutouse:
    """Test on_fixture_setup with autouse."""

    def test_on_fixture_setup_autouse(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Autouse fixture displays setup message."""
        ascii_reporter.on_fixture_setup(
            FixtureInfo(name="my_autouse_fixture", scope="session", autouse=True)
        )
        captured = capsys.readouterr()
        assert "autouse" in captured.out
        assert "my_autouse_fixture" in captured.out
        assert "session" in captured.out

    def test_on_fixture_setup_not_autouse(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-autouse fixture does not display message."""
        ascii_reporter.on_fixture_setup(
            FixtureInfo(name="regular_fixture", scope="suite", autouse=False)
        )
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAsciiReporterRetry:
    """Test retry-related output."""

    def test_on_test_retry_with_delay(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Retry message includes delay when > 0."""
        ascii_reporter.on_test_retry(
            TestRetryInfo(
                name="test_flaky",
                node_id="module::test_flaky",
                suite_path=None,
                attempt=1,
                max_attempts=3,
                error=ValueError("boom"),
                delay=1.5,
            )
        )
        captured = capsys.readouterr()
        assert "RY" in captured.out
        assert "test_flaky" in captured.out
        assert "attempt 1/3" in captured.out
        assert "retrying in 1.5s" in captured.out
        assert "ValueError" in captured.out

    def test_on_test_pass_with_retry(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Pass message includes attempt info when retried."""
        ascii_reporter.on_test_pass(
            TestResult(
                name="test_flaky",
                node_id="module::test_flaky",
                duration=0.1,
                attempt=2,
                max_attempts=3,
            )
        )
        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "test_flaky" in captured.out
        assert "[attempt 2/3]" in captured.out

    def test_on_test_fail_with_retry(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Fail message includes attempt count when retried."""
        ascii_reporter.on_test_fail(
            TestResult(
                name="test_flaky",
                node_id="module::test_flaky",
                duration=0.1,
                error=ValueError("final fail"),
                attempt=3,
                max_attempts=3,
            )
        )
        captured = capsys.readouterr()
        assert "XX" in captured.out
        assert "test_flaky" in captured.out
        assert "[3 attempts]" in captured.out


class TestAsciiReporterInterrupt:
    """Test interrupt messages."""

    def test_on_session_interrupted_soft(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Soft interrupt shows stopping message."""
        ascii_reporter.on_session_interrupted(force_teardown=False)
        captured = capsys.readouterr()
        assert "Stopping" in captured.out
        assert "force teardown" in captured.out.lower()

    def test_on_session_interrupted_force(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Force teardown shows forcing message."""
        ascii_reporter.on_session_interrupted(force_teardown=True)
        captured = capsys.readouterr()
        assert "Forcing teardown" in captured.out
        assert "kill" in captured.out.lower()


class TestAsciiReporterFailureSummary:
    """Test failure summary output."""

    def test_failure_summary_with_failures(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Failure summary shows FAILURES section with traceback and output."""
        ascii_reporter.on_test_fail(
            TestResult(
                name="test_fail",
                node_id="module::test_fail",
                duration=0.1,
                error=ValueError("something went wrong"),
                output="captured output line 1\ncaptured output line 2",
            )
        )
        capsys.readouterr()  # Clear the on_test_fail output

        ascii_reporter.on_session_complete(
            SessionResult(passed=0, failed=1, errors=0, duration=1.0)
        )
        captured = capsys.readouterr()
        assert "=== FAILURES ===" in captured.out
        assert "test_fail" in captured.out
        assert "ValueError" in captured.out
        assert "Captured output" in captured.out
        assert "captured output line 1" in captured.out

    def test_failure_summary_with_errors(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Failure summary shows ERRORS section for fixture errors."""
        ascii_reporter.on_test_fail(
            TestResult(
                name="test_error",
                node_id="module::Suite::test_error",
                duration=0.1,
                error=RuntimeError("fixture exploded"),
                is_fixture_error=True,
                output="error output",
            )
        )
        capsys.readouterr()  # Clear the on_test_fail output

        ascii_reporter.on_session_complete(
            SessionResult(passed=0, failed=0, errors=1, duration=1.0)
        )
        captured = capsys.readouterr()
        assert "=== ERRORS ===" in captured.out
        assert "test_error" in captured.out
        assert "!!" in captured.out  # Error prefix


class TestAsciiReporterCompleteInterrupted:
    """Test session complete with interrupted status."""

    def test_session_complete_interrupted(
        self, ascii_reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Session complete with interrupted shows INTERRUPTED status."""
        ascii_reporter.on_session_complete(
            SessionResult(
                passed=5,
                failed=0,
                errors=0,
                skipped=1,
                duration=2.5,
                interrupted=True,
            )
        )
        captured = capsys.readouterr()
        assert "INTERRUPTED" in captured.out
        assert "5/6 passed" in captured.out
        assert "1 skipped" in captured.out
