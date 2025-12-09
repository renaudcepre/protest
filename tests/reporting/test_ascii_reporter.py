from __future__ import annotations

import pytest

from protest.entities import HandlerInfo, SessionResult, TestItem, TestResult
from protest.events.types import Event
from protest.reporting.ascii import (
    AsciiReporter,
    _extract_suite_from_node_id,
    _format_duration,
    _format_test_name,
)


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


class TestExtractSuiteFromNodeId:
    def test_extracts_suite_from_nested_node_id(self) -> None:
        result = _extract_suite_from_node_id("module::Suite::test_name")
        assert result == "Suite"

    def test_extracts_nested_suite_path(self) -> None:
        result = _extract_suite_from_node_id("module::Parent::Child::test_name")
        assert result == "Parent::Child"

    def test_returns_none_for_simple_node_id(self) -> None:
        result = _extract_suite_from_node_id("module::test_name")
        assert result is None

    def test_returns_none_for_single_part(self) -> None:
        result = _extract_suite_from_node_id("test_name")
        assert result is None


class TestFormatTestNameWithSuite:
    def test_includes_suite_when_include_suite_true(self) -> None:
        result = TestResult(
            name="test_foo",
            node_id="module::MySuite::test_foo",
            duration=0.1,
            suite_path="MySuite",
        )
        formatted = _format_test_name(result, include_suite=True)
        assert formatted == "MySuite::test_foo"

    def test_no_suite_when_include_suite_false(self) -> None:
        result = TestResult(
            name="test_foo",
            node_id="module::MySuite::test_foo",
            duration=0.1,
            suite_path="MySuite",
        )
        formatted = _format_test_name(result, include_suite=False)
        assert formatted == "test_foo"

    def test_nested_suite_in_name(self) -> None:
        result = TestResult(
            name="test_foo",
            node_id="module::Parent::Child::test_foo",
            duration=0.1,
            suite_path="Parent::Child",
        )
        formatted = _format_test_name(result, include_suite=True)
        assert formatted == "Parent::Child::test_foo"


def _make_test_item(name: str = "test_example") -> TestItem:
    def test_func() -> None:
        pass

    test_func.__name__ = name
    test_func.__module__ = "module"
    return TestItem(func=test_func, suite=None)


class TestAsciiReporterParallelMode:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_on_collection_finish_sets_parallel_mode(
        self, reporter: AsciiReporter
    ) -> None:
        items = [_make_test_item(f"test_{idx}") for idx in range(5)]
        reporter.on_collection_finish(items)
        assert reporter._is_parallel is True

    def test_on_collection_finish_single_item_not_parallel(
        self, reporter: AsciiReporter
    ) -> None:
        items = [_make_test_item("test_single")]
        reporter.on_collection_finish(items)
        assert reporter._is_parallel is False

    def test_suite_header_not_printed_in_parallel_mode(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        items = [_make_test_item(f"test_{idx}") for idx in range(5)]
        reporter.on_collection_finish(items)

        reporter.on_suite_start("MySuite")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAsciiReporterSessionHooks:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_on_session_setup_start(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_session_setup_start()
        captured = capsys.readouterr()
        assert "session setup" in captured.out.lower()

    def test_on_session_setup_done(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_session_setup_done(0.5)
        captured = capsys.readouterr()
        assert "500ms" in captured.out or "0.5" in captured.out

    def test_on_session_teardown_start(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_session_teardown_start()
        captured = capsys.readouterr()
        assert "teardown" in captured.out.lower()

    def test_on_session_teardown_done(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reporter.on_session_teardown_done(0.25)
        captured = capsys.readouterr()
        assert "250ms" in captured.out or "0.25" in captured.out


class TestAsciiReporterTestStatus:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_on_test_skip(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_skipped",
            node_id="mod::test_skipped",
            duration=0.0,
            skip_reason="Not implemented yet",
        )
        reporter.on_test_skip(result)
        captured = capsys.readouterr()
        assert "-- test_skipped" in captured.out
        assert "Not implemented yet" in captured.out

    def test_on_test_xfail(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_expected_fail",
            node_id="mod::test_expected_fail",
            duration=0.05,
            xfail_reason="Known bug #123",
            error=AssertionError("expected"),
        )
        reporter.on_test_xfail(result)
        captured = capsys.readouterr()
        assert "xf test_expected_fail" in captured.out
        assert "Known bug #123" in captured.out
        assert "50ms" in captured.out

    def test_on_test_xpass(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_unexpected_pass",
            node_id="mod::test_unexpected_pass",
            duration=0.1,
            xfail_reason="Was supposed to fail",
        )
        reporter.on_test_xpass(result)
        captured = capsys.readouterr()
        assert "XP test_unexpected_pass" in captured.out
        assert "UNEXPECTED PASS" in captured.out
        assert "100ms" in captured.out

    def test_on_test_fail_timeout(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = TestResult(
            name="test_slow",
            node_id="mod::test_slow",
            duration=5.0,
            error=TimeoutError("Test exceeded timeout"),
            timeout=5.0,
        )
        reporter.on_test_fail(result)
        captured = capsys.readouterr()
        assert "TO test_slow" in captured.out
        assert "TIMEOUT" in captured.out
        assert "5" in captured.out


class TestAsciiReporterSummaryParts:
    @pytest.fixture
    def reporter(self) -> AsciiReporter:
        return AsciiReporter()

    def test_summary_with_skipped(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=4, failed=0, errors=0, skipped=2, duration=1.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "2 skipped" in captured.out

    def test_summary_with_xfailed(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=3, failed=0, errors=0, xfailed=1, duration=1.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "1 xfailed" in captured.out

    def test_summary_with_xpassed(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(passed=3, failed=0, errors=0, xpassed=1, duration=1.0)
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "XX FAILURES" in captured.out
        assert "1 xpassed" in captured.out

    def test_summary_all_status_types(
        self, reporter: AsciiReporter, capsys: pytest.CaptureFixture[str]
    ) -> None:
        result = SessionResult(
            passed=2, failed=1, errors=1, skipped=1, xfailed=1, xpassed=1, duration=5.0
        )
        reporter.on_session_complete(result)
        captured = capsys.readouterr()
        assert "2/7 passed" in captured.out
        assert "1 skipped" in captured.out
        assert "1 xfailed" in captured.out
        assert "1 xpassed" in captured.out
        assert "1 failed" in captured.out
        assert "1 errors" in captured.out
