"""Tests for RichReporter - Rich console reporter with colors."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from protest.entities import (
    HandlerInfo,
    SessionResult,
    TestItem,
    TestResult,
    TestRetryInfo,
)
from protest.events.types import Event
from protest.reporting.rich_reporter import (
    MIN_DURATION_THRESHOLD,
    RichReporter,
    _format_duration,
)


class TestFormatDuration:
    def test_sub_millisecond(self) -> None:
        assert _format_duration(0.0001) == "<1ms"

    def test_at_threshold(self) -> None:
        assert _format_duration(MIN_DURATION_THRESHOLD) == "1ms"

    def test_milliseconds(self) -> None:
        assert _format_duration(0.5) == "500ms"
        assert _format_duration(0.123) == "123ms"

    def test_seconds(self) -> None:
        assert _format_duration(2.5) == "2.50s"
        assert _format_duration(1.0) == "1.00s"

    def test_large_duration(self) -> None:
        result = _format_duration(120.5)
        assert "120.50s" in result


def _make_test_item(name: str = "test_example") -> TestItem:
    def test_func() -> None:
        pass

    test_func.__name__ = name
    test_func.__module__ = "module"
    return TestItem(func=test_func, suite=None)


class TestRichReporterBasic:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        reporter.console = MagicMock()
        return reporter

    def test_on_collection_finish_stores_count(self, reporter: RichReporter) -> None:
        items = [_make_test_item(f"test_{idx}") for idx in range(5)]
        result = reporter.on_collection_finish(items)
        assert reporter._total_tests == 5
        assert result is items

    def test_on_test_pass_prints(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_example", node_id="mod::test_example", duration=0.05
        )
        reporter.on_test_pass(result)
        reporter.console.print.assert_called()

    def test_on_test_fail_prints(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_failing",
            node_id="mod::test_failing",
            duration=0.01,
            error=AssertionError("oops"),
        )
        reporter.on_test_fail(result)
        reporter.console.print.assert_called()


class TestRichReporterTimeout:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_test_fail_with_timeout(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_slow",
            node_id="mod::test_slow",
            duration=5.0,
            error=TimeoutError("Test exceeded timeout"),
            timeout=5.0,
        )
        reporter.on_test_fail(result)
        output = reporter._output.getvalue()
        assert "TIMEOUT" in output
        assert "5" in output


class TestRichReporterOutput:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_test_fail_with_output(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_with_output",
            node_id="mod::test_with_output",
            duration=0.01,
            error=AssertionError("fail"),
            output="debug line 1\ndebug line 2",
        )
        reporter.on_test_fail(result)
        output = reporter._output.getvalue()
        assert "debug line 1" in output
        assert "debug line 2" in output


class TestRichReporterAsyncHandlers:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_waiting_handlers(self, reporter: RichReporter) -> None:
        reporter.on_waiting_handlers(3)
        output = reporter._output.getvalue()
        assert "Async handlers" in output
        assert "3" in output

    def test_on_handler_end_with_error(self, reporter: RichReporter) -> None:
        info = HandlerInfo(
            name="failing_handler",
            event=Event.SESSION_END,
            is_async=True,
            error=RuntimeError("handler failed"),
        )
        reporter.on_handler_end(info)
        output = reporter._output.getvalue()
        assert "failing_handler" in output
        assert "handler failed" in output

    def test_on_handler_end_success(self, reporter: RichReporter) -> None:
        info = HandlerInfo(
            name="success_handler",
            event=Event.SESSION_END,
            is_async=True,
            duration=0.5,
        )
        reporter.on_handler_end(info)
        output = reporter._output.getvalue()
        assert "success_handler" in output
        assert "500ms" in output

    def test_on_handler_end_sync_ignored(self, reporter: RichReporter) -> None:
        info = HandlerInfo(
            name="sync_handler",
            event=Event.SESSION_END,
            is_async=False,
            duration=0.1,
        )
        reporter.on_handler_end(info)
        output = reporter._output.getvalue()
        assert output == ""


class TestRichReporterTestStatus:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_test_skip(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_skipped",
            node_id="mod::test_skipped",
            duration=0.0,
            skip_reason="Not ready",
        )
        reporter.on_test_skip(result)
        output = reporter._output.getvalue()
        assert "test_skipped" in output
        assert "Not ready" in output

    def test_on_test_xfail(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_expected_fail",
            node_id="mod::test_expected_fail",
            duration=0.05,
            xfail_reason="Known bug",
            error=AssertionError("expected"),
        )
        reporter.on_test_xfail(result)
        output = reporter._output.getvalue()
        assert "test_expected_fail" in output
        assert "Known bug" in output

    def test_on_test_xpass(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_unexpected_pass",
            node_id="mod::test_unexpected_pass",
            duration=0.1,
            xfail_reason="Should fail",
        )
        reporter.on_test_xpass(result)
        output = reporter._output.getvalue()
        assert "test_unexpected_pass" in output
        assert "XPASS" in output

    def test_on_test_fail_fixture_error(self, reporter: RichReporter) -> None:
        result = TestResult(
            name="test_fixture_fail",
            node_id="mod::test_fixture_fail",
            duration=0.01,
            error=RuntimeError("db down"),
            is_fixture_error=True,
        )
        reporter.on_test_fail(result)
        output = reporter._output.getvalue()
        assert "FIXTURE" in output


class TestRichReporterSessionComplete:
    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_all_passed(self, reporter: RichReporter) -> None:
        result = SessionResult(passed=5, failed=0, errors=0, duration=1.23)
        reporter.on_session_complete(result)
        output = reporter._output.getvalue()
        assert "ALL PASSED" in output
        assert "5/5 passed" in output

    def test_with_failures(self, reporter: RichReporter) -> None:
        result = SessionResult(passed=3, failed=1, errors=0, duration=2.0)
        reporter.on_session_complete(result)
        output = reporter._output.getvalue()
        assert "FAILURES" in output
        assert "1 failed" in output

    def test_with_all_status_types(self, reporter: RichReporter) -> None:
        result = SessionResult(
            passed=2,
            failed=1,
            errors=1,
            skipped=1,
            xfailed=1,
            xpassed=1,
            duration=5.0,
        )
        reporter.on_session_complete(result)
        output = reporter._output.getvalue()
        assert "skipped" in output
        assert "xfailed" in output
        assert "xpassed" in output
        assert "failed" in output
        assert "errors" in output


class TestRichReporterRetry:
    """Test retry-related output."""

    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_test_retry_with_delay(self, reporter: RichReporter) -> None:
        """Retry message includes delay when > 0."""
        reporter.on_test_retry(
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
        output = reporter._output.getvalue()
        assert "test_flaky" in output
        assert "attempt 1/3" in output
        assert "retrying in 1.5s" in output
        assert "ValueError" in output

    def test_on_test_pass_with_retry(self, reporter: RichReporter) -> None:
        """Pass message includes attempt info when retried."""
        reporter.on_test_pass(
            TestResult(
                name="test_flaky",
                node_id="module::test_flaky",
                duration=0.1,
                attempt=2,
                max_attempts=3,
            )
        )
        output = reporter._output.getvalue()
        assert "test_flaky" in output
        assert "attempt 2/3" in output

    def test_on_test_fail_with_retry(self, reporter: RichReporter) -> None:
        """Fail message includes attempt count when retried."""
        reporter.on_test_fail(
            TestResult(
                name="test_flaky",
                node_id="module::test_flaky",
                duration=0.1,
                error=ValueError("final fail"),
                attempt=3,
                max_attempts=3,
            )
        )
        output = reporter._output.getvalue()
        assert "test_flaky" in output
        assert "3 attempts" in output


class TestRichReporterInterrupt:
    """Test interrupt messages."""

    @pytest.fixture
    def reporter(self) -> RichReporter:
        reporter = RichReporter()
        output = StringIO()
        reporter.console = MagicMock()
        reporter.console.print = lambda msg: output.write(str(msg) + "\n")
        reporter._output = output
        return reporter

    def test_on_session_interrupted_force(self, reporter: RichReporter) -> None:
        """Force teardown shows forcing message."""
        reporter.on_session_interrupted(force_teardown=True)
        output = reporter._output.getvalue()
        assert "Forcing teardown" in output
        assert "kill" in output.lower()


class TestRichReporterFailureSummary:
    """Test failure summary with captured output."""

    def test_failure_detail_with_output(self) -> None:
        """Failure detail shows captured output."""
        reporter = RichReporter()
        output = StringIO()

        def capture_print(msg: str) -> None:
            output.write(str(msg) + "\n")

        reporter.console = MagicMock()
        reporter.console.print = capture_print
        reporter.console.is_terminal = False

        reporter.on_test_fail(
            TestResult(
                name="test_fail",
                node_id="module::test_fail",
                duration=0.1,
                error=ValueError("boom"),
                output="captured line 1\ncaptured line 2",
            )
        )

        reporter.on_session_complete(
            SessionResult(passed=0, failed=1, errors=0, duration=1.0)
        )
        result = output.getvalue()
        assert "Captured output" in result
        assert "captured line 1" in result
        assert "captured line 2" in result
