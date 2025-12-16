from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from protest.entities import SessionResult, TestResult, TestStartInfo, TestTeardownInfo
from protest.events.types import Event
from protest.reporting.web import (
    DEFAULT_PORT,
    WebReporter,
    _format_traceback,
    _process_request,
)
from tests.factories.test_items import make_test_item


class TestFormatTraceback:
    def test_format_traceback_returns_string(self) -> None:
        try:
            raise ValueError("test error")
        except ValueError as e:
            result = _format_traceback(e)
            assert "ValueError" in result
            assert "test error" in result
            assert "Traceback" in result

    def test_format_traceback_includes_cause(self) -> None:
        try:
            try:
                raise KeyError("original")
            except KeyError as e:
                raise ValueError("wrapped") from e
        except ValueError as e:
            result = _format_traceback(e)
            assert "ValueError" in result
            assert "KeyError" in result


class TestProcessRequest:
    def test_ws_path_returns_none(self) -> None:
        request = MagicMock()
        request.path = "/ws"
        result = _process_request(None, request)
        assert result is None

    def test_index_path_returns_html(self) -> None:
        request = MagicMock()
        request.path = "/"
        with patch("protest.reporting.web.ASSETS_DIR") as mock_dir:
            mock_html = MagicMock()
            mock_html.exists.return_value = True
            mock_html.read_bytes.return_value = b"<html>test</html>"
            mock_dir.__truediv__ = MagicMock(return_value=mock_html)

            result = _process_request(None, request)

            assert result is not None
            assert result.status_code == 200

    def test_unknown_path_returns_404(self) -> None:
        request = MagicMock()
        request.path = "/unknown"
        result = _process_request(None, request)
        assert result is not None
        assert result.status_code == 404


class TestWebReporter:
    @pytest.fixture
    def reporter(self) -> WebReporter:
        return WebReporter(port=9999)

    @pytest.fixture
    def connected_reporter(self, reporter: WebReporter) -> WebReporter:
        reporter._ws = MagicMock()
        return reporter

    def test_init_default_port(self) -> None:
        reporter = WebReporter()
        assert reporter._port == DEFAULT_PORT

    def test_init_custom_port(self) -> None:
        reporter = WebReporter(port=1234)
        assert reporter._port == 1234

    def test_set_target(self, reporter: WebReporter) -> None:
        reporter.set_target("my_module:session")
        assert reporter._session_target == "my_module:session"


class TestWebReporterSend:
    @pytest.fixture
    def reporter(self) -> WebReporter:
        reporter = WebReporter()
        reporter._ws = MagicMock()
        return reporter

    def test_send_formats_json(self, reporter: WebReporter) -> None:
        reporter._send("TEST_EVENT", {"key": "value"})
        call_args = reporter._ws.send.call_args[0][0]
        parsed = json.loads(call_args)
        assert parsed["type"] == "TEST_EVENT"
        assert parsed["payload"] == {"key": "value"}

    def test_send_without_connection_does_nothing(self) -> None:
        reporter = WebReporter()
        reporter._ws = None
        reporter._send("TEST", {})  # Should not raise

    def test_send_exception_clears_connection(self, reporter: WebReporter) -> None:
        reporter._ws.send.side_effect = Exception("connection error")
        reporter._send("TEST", {})
        assert reporter._ws is None


class TestWebReporterEventHandlers:
    @pytest.fixture
    def reporter(self) -> WebReporter:
        reporter = WebReporter()
        reporter._ws = MagicMock()
        return reporter

    def _get_sent_message(self, reporter: WebReporter) -> dict[str, Any]:
        call_args = reporter._ws.send.call_args[0][0]
        return json.loads(call_args)

    def test_on_test_acquired(self, reporter: WebReporter) -> None:
        info = TestStartInfo(name="test_foo", node_id="suite::test_foo")
        reporter.on_test_acquired(info)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_SETUP"
        assert msg["payload"]["nodeId"] == "suite::test_foo"

    def test_on_test_setup_done(self, reporter: WebReporter) -> None:
        info = TestStartInfo(name="test_foo", node_id="suite::test_foo")
        reporter.on_test_setup_done(info)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_RUNNING"
        assert msg["payload"]["nodeId"] == "suite::test_foo"

    def test_on_test_teardown_start(self, reporter: WebReporter) -> None:
        info = TestTeardownInfo(
            name="test_foo", node_id="suite::test_foo", outcome=Event.TEST_PASS
        )
        reporter.on_test_teardown_start(info)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_TEARDOWN"
        assert msg["payload"]["nodeId"] == "suite::test_foo"
        assert msg["payload"]["outcome"] == "pass"

    def test_on_test_pass(self, reporter: WebReporter) -> None:
        result = TestResult(name="test_foo", node_id="suite::test_foo", duration=0.5)
        reporter.on_test_pass(result)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_PASS"
        assert msg["payload"]["nodeId"] == "suite::test_foo"
        assert msg["payload"]["duration"] == 0.5

    def test_on_test_fail_includes_error(self, reporter: WebReporter) -> None:
        error = ValueError("something failed")
        result = TestResult(
            name="test_foo",
            node_id="suite::test_foo",
            duration=0.5,
            error=error,
        )
        reporter.on_test_fail(result)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_FAIL"
        assert msg["payload"]["message"] == "something failed"
        assert "traceback" in msg["payload"]

    def test_on_test_skip(self, reporter: WebReporter) -> None:
        result = TestResult(
            name="test_foo",
            node_id="suite::test_foo",
            duration=0.0,
            skip_reason="WIP",
        )
        reporter.on_test_skip(result)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_SKIP"
        assert msg["payload"]["message"] == "WIP"

    def test_on_test_xfail(self, reporter: WebReporter) -> None:
        result = TestResult(
            name="test_foo",
            node_id="suite::test_foo",
            duration=0.1,
            xfail_reason="Bug #123",
        )
        reporter.on_test_xfail(result)
        msg = self._get_sent_message(reporter)
        assert msg["type"] == "TEST_XFAIL"
        assert msg["payload"]["message"] == "Bug #123"

    def test_on_session_complete_closes_connection(self, reporter: WebReporter) -> None:
        ws_mock = reporter._ws  # Save reference before it's cleared
        result = SessionResult(passed=1, failed=0, errors=0, skipped=0)
        reporter.on_session_complete(result)
        ws_mock.close.assert_called_once()
        assert reporter._ws is None


class TestWebReporterResultPayload:
    @pytest.fixture
    def reporter(self) -> WebReporter:
        return WebReporter()

    def test_basic_payload(self, reporter: WebReporter) -> None:
        result = TestResult(name="test", node_id="suite::test", duration=0.1)
        payload = reporter._result_payload(result)
        assert payload == {"nodeId": "suite::test", "duration": 0.1}

    def test_payload_with_stdout(self, reporter: WebReporter) -> None:
        result = TestResult(
            name="test", node_id="suite::test", duration=0.1, output="hello"
        )
        payload = reporter._result_payload(result)
        assert payload["stdout"] == "hello"

    def test_payload_with_logs(self, reporter: WebReporter) -> None:
        reporter._test_logs["suite::test"] = ["INFO:logger:msg1", "ERROR:logger:msg2"]
        result = TestResult(name="test", node_id="suite::test", duration=0.1)
        payload = reporter._result_payload(result)
        assert "logs" in payload
        assert "INFO:logger:msg1" in payload["logs"]
        assert "ERROR:logger:msg2" in payload["logs"]
        assert "suite::test" not in reporter._test_logs  # Consumed

    def test_payload_with_error(self, reporter: WebReporter) -> None:
        error = ValueError("failed")
        result = TestResult(
            name="test", node_id="suite::test", duration=0.1, error=error
        )
        payload = reporter._result_payload(result, include_error=True)
        assert payload["message"] == "failed"
        assert "traceback" in payload

    def test_payload_without_error_flag(self, reporter: WebReporter) -> None:
        error = ValueError("failed")
        result = TestResult(
            name="test", node_id="suite::test", duration=0.1, error=error
        )
        payload = reporter._result_payload(result, include_error=False)
        assert "message" not in payload
        assert "traceback" not in payload


class TestWebReporterOnLog:
    def test_on_log_captures_messages(self) -> None:
        reporter = WebReporter()
        record = MagicMock()
        record.levelno = 20  # INFO
        record.name = "mylogger"
        record.getMessage.return_value = "test message"

        reporter._on_log("suite::test", record)

        assert "suite::test" in reporter._test_logs
        assert "INFO:mylogger:test message" in reporter._test_logs["suite::test"]

    def test_on_log_appends_to_existing(self) -> None:
        reporter = WebReporter()
        reporter._test_logs["suite::test"] = ["existing"]

        record = MagicMock()
        record.levelno = 40  # ERROR
        record.name = "logger"
        record.getMessage.return_value = "error msg"

        reporter._on_log("suite::test", record)

        assert len(reporter._test_logs["suite::test"]) == 2


class TestWebReporterOnCollectionFinish:
    def test_successful_connection(self) -> None:
        reporter = WebReporter(port=9999)
        items = [
            make_test_item("test_one", suite=None),
            make_test_item("test_two", suite=None),
        ]

        with patch("protest.reporting.web.ws_connect") as mock_connect:
            mock_ws = MagicMock()
            mock_connect.return_value = mock_ws

            result = reporter.on_collection_finish(items)

            assert result == items
            assert reporter._ws == mock_ws
            assert reporter._total_tests == 2
            mock_ws.send.assert_called_once()

    def test_connection_failure_warns(self) -> None:
        reporter = WebReporter(port=9999)
        items = [make_test_item("test_one", suite=None)]

        with patch("protest.reporting.web.ws_connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")

            with pytest.warns(UserWarning, match="Cannot connect to live server"):
                result = reporter.on_collection_finish(items)

            assert result == items
            assert reporter._ws is None

    def test_sends_session_start_payload(self) -> None:
        reporter = WebReporter(port=9999)
        reporter.set_target("mymodule:session")
        items = [make_test_item("test_foo", suite=None)]

        with patch("protest.reporting.web.ws_connect") as mock_connect:
            mock_ws = MagicMock()
            mock_connect.return_value = mock_ws

            reporter.on_collection_finish(items)

            call_args = mock_ws.send.call_args[0][0]
            msg = json.loads(call_args)
            assert msg["type"] == "SESSION_START"
            assert msg["payload"]["target"] == "mymodule:session"
            assert msg["payload"]["totalTests"] == 1
            assert len(msg["payload"]["tests"]) == 1
