"""Tests for the LiveReporter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from protest.entities import TestResult, TestStartInfo
from protest.reporting.live_reporter import LiveReporter, TestPhase, _format_duration


class TestFormatDuration:
    def test_sub_millisecond(self) -> None:
        assert _format_duration(0.0001) == "<1ms"

    def test_zero(self) -> None:
        assert _format_duration(0) == "<1ms"

    def test_milliseconds(self) -> None:
        assert _format_duration(0.5) == "500ms"
        assert _format_duration(0.123) == "123ms"

    def test_seconds(self) -> None:
        assert _format_duration(2.5) == "2.50s"
        assert _format_duration(1.0) == "1.00s"


class TestLiveReporterInit:
    def test_initial_state(self) -> None:
        reporter = LiveReporter()
        assert reporter._live is None
        assert reporter._passed == 0
        assert reporter._failed == 0
        assert reporter._errors == 0
        assert reporter._skipped == 0
        assert len(reporter._active_tests) == 0


class TestLiveReporterAlwaysLive:
    @pytest.fixture
    def reporter(self) -> LiveReporter:
        return LiveReporter()

    def test_session_start_initializes_live(self, reporter: LiveReporter) -> None:
        with patch("protest.reporting.live_reporter.add_log_callback"):
            with patch("protest.reporting.live_reporter.Live") as mock_live_class:
                mock_live_instance = MagicMock()
                mock_live_class.return_value = mock_live_instance
                reporter.on_session_start()

        assert reporter._live is mock_live_instance
        mock_live_instance.start.assert_called_once()

    def test_refresh_called_on_test_pass(self, reporter: LiveReporter) -> None:
        reporter._live = MagicMock()
        reporter._active_tests = {"mod::test": MagicMock()}
        result = TestResult(name="test", node_id="mod::test", duration=0.1)
        reporter.on_test_pass(result)

        assert reporter._passed == 1
        reporter._live.update.assert_called()

    def test_refresh_called_on_test_fail(self, reporter: LiveReporter) -> None:
        reporter._live = MagicMock()
        reporter._active_tests = {"mod::test": MagicMock()}
        result = TestResult(
            name="test", node_id="mod::test", duration=0.1, error=AssertionError("oops")
        )
        reporter.on_test_fail(result)

        assert reporter._failed == 1
        reporter._live.update.assert_called()

    def test_fixture_error_counts_as_error(self, reporter: LiveReporter) -> None:
        reporter._live = MagicMock()
        reporter._active_tests = {"mod::test": MagicMock()}
        result = TestResult(
            name="test",
            node_id="mod::test",
            duration=0.1,
            error=RuntimeError("db down"),
            is_fixture_error=True,
        )
        reporter.on_test_fail(result)

        assert reporter._errors == 1
        assert reporter._failed == 0

    def test_timeout_counts_as_failed(self, reporter: LiveReporter) -> None:
        reporter._live = MagicMock()
        reporter._active_tests = {"mod::test": MagicMock()}
        result = TestResult(
            name="test",
            node_id="mod::test",
            duration=5.0,
            error=TimeoutError("Test exceeded timeout"),
            timeout=5.0,
        )
        reporter.on_test_fail(result)

        assert reporter._failed == 1
        assert reporter._errors == 0

    def test_test_phases_tracked(self, reporter: LiveReporter) -> None:
        reporter._live = MagicMock()
        reporter._collected_items = {"mod::test": MagicMock(suite_path=None)}
        info = TestStartInfo(name="test", node_id="mod::test")

        reporter.on_test_start(info)
        assert reporter._active_tests["mod::test"].phase == TestPhase.WAITING

        reporter.on_test_acquired(info)
        assert reporter._active_tests["mod::test"].phase == TestPhase.SETUP

        reporter.on_test_setup_done(info)
        assert reporter._active_tests["mod::test"].phase == TestPhase.RUNNING

        reporter.on_test_teardown_start(info)
        assert reporter._active_tests["mod::test"].phase == TestPhase.TEARDOWN

    def test_session_complete_stops_live(self, reporter: LiveReporter) -> None:
        mock_live = MagicMock()
        reporter._live = mock_live
        with patch("protest.reporting.live_reporter.remove_log_callback"):
            from protest.entities import SessionResult

            result = SessionResult(passed=1, failed=0, errors=0, duration=1.0)
            reporter.on_session_complete(result)

        mock_live.stop.assert_called_once()
        assert reporter._live is None
