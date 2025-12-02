from __future__ import annotations

import pytest

from protest.entities import HandlerInfo, SessionResult, TestResult
from protest.events.types import Event
from protest.reporting.ascii import AsciiReporter, _format_duration, _format_test_name


class TestFormatDuration:
    def test_sub_millisecond(self) -> None:
        assert _format_duration(0.0001) == "<1ms"

    def test_zero(self) -> None:
        assert _format_duration(0) == "<1ms"

    def test_milliseconds(self) -> None:
        assert _format_duration(0.5) == "500ms"
        assert _format_duration(0.123) == "123ms"

    def test_one_millisecond(self) -> None:
        assert _format_duration(0.001) == "1ms"

    def test_seconds(self) -> None:
        assert _format_duration(2.5) == "2.50s"
        assert _format_duration(1.0) == "1.00s"


class TestFormatTestName:
    def test_simple_name(self) -> None:
        result = TestResult(name="test_foo", node_id="module::test_foo", duration=0.1)
        assert _format_test_name(result) == "test_foo"

    def test_with_params(self) -> None:
        result = TestResult(
            name="test_x", node_id="module::test_x[param1-param2]", duration=0.1
        )
        assert _format_test_name(result) == "test_x[param1-param2]"


class TestAsciiReporterHooks:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_on_session_start(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_session_start()
        captured = capsys.readouterr()
        assert "Starting session" in captured.out

    def test_on_suite_start(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_suite_start("MySuite")
        captured = capsys.readouterr()
        assert "MySuite" in captured.out

    def test_on_test_pass(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_example", node_id="mod::test_example", duration=0.05
        )
        reporter.on_test_pass(result)
        captured = capsys.readouterr()
        assert "OK test_example" in captured.out
        assert "50ms" in captured.out

    def test_on_test_fail(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_failing",
            node_id="mod::test_failing",
            duration=0.01,
            error=AssertionError("oops"),
        )
        reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "XX test_failing" in captured.out
        assert "oops" in captured.out

    def test_on_test_fail_with_output(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_failing",
            node_id="mod::test_failing",
            duration=0.01,
            error=AssertionError("oops"),
            output="debug line 1\ndebug line 2",
        )
        reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "| debug line 1" in captured.out
        assert "| debug line 2" in captured.out

    def test_on_test_fail_fixture_error(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_x",
            node_id="mod::test_x",
            duration=0.01,
            error=RuntimeError("db down"),
            is_fixture_error=True,
        )
        reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "!! test_x" in captured.out

    def test_on_waiting_handlers(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_waiting_handlers(3)
        captured = capsys.readouterr()
        assert "Async handlers (3)" in captured.out

    def test_on_handler_end_async_success(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        info = HandlerInfo(
            name="send_slack", event=Event.SESSION_END, is_async=True, duration=0.5
        )
        reporter.on_handler_end(info)
        captured = capsys.readouterr()
        assert "OK send_slack" in captured.out
        assert "500ms" in captured.out

    def test_on_handler_end_async_error(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        info = HandlerInfo(
            name="send_slack",
            event=Event.SESSION_END,
            is_async=True,
            error=RuntimeError("timeout"),
        )
        reporter.on_handler_end(info)
        captured = capsys.readouterr()
        assert "XX send_slack" in captured.out
        assert "timeout" in captured.out

    def test_on_handler_end_sync_ignored(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        info = HandlerInfo(
            name="sync_handler", event=Event.SESSION_END, is_async=False, duration=0.1
        )
        reporter.on_handler_end(info)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAsciiReporterSessionComplete:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_all_passed(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=5, failed=0, errors=0, duration=1.23)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "OK ALL PASSED" in captured.out
        assert "5/5 passed" in captured.out
        assert "1.23s" in captured.out

    def test_with_failures(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=3, failed=1, errors=0, duration=2.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "XX FAILURES" in captured.out
        assert "3/4 passed" in captured.out
        assert "1 failed" in captured.out

    def test_with_errors(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=3, failed=0, errors=1, duration=2.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "XX FAILURES" in captured.out
        assert "1 errors" in captured.out

    def test_with_failures_and_errors(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=2, failed=1, errors=1, duration=3.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "XX FAILURES" in captured.out
        assert "2/4 passed" in captured.out
        assert "1 failed" in captured.out
        assert "1 errors" in captured.out
