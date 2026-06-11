"""Tests for `protest.console.print` - payload shape and reporter formatting.

`console.print(msg, raw=False, prefix=True)` builds a 3-tuple payload
`(msg, raw, prefix)` dispatched on USER_PRINT. Each reporter unpacks the
three flags and renders accordingly:

- default (prefix=True, raw=False): per-test bar prefix + markup
- raw=True: no prefix, no markup (debug bytes)
- prefix=False: no prefix, markup still active (suite-level lines)

The third mode is what unblocks `EvalResultsWriter.on_eval_suite_end` so
`Results: <path>` doesn't visually attach to the previous case's output.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

from protest import console
from protest.events.types import Event
from protest.reporting.ascii import AsciiReporter
from protest.reporting.rich_reporter import RichReporter


@pytest.fixture
def stdout_buffer(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    buf = io.StringIO()
    # `real_stdout()` is what reporters write to; patch at both reporter modules.
    monkeypatch.setattr("protest.reporting.ascii.real_stdout", lambda: buf)
    monkeypatch.setattr("protest.reporting.rich_reporter.real_stdout", lambda: buf)
    return buf


class TestAsciiReporterUserPrint:
    """ASCII reporter handles the 3-tuple payload."""

    def test_default_adds_bar_prefix(self, stdout_buffer: io.StringIO) -> None:
        reporter = AsciiReporter()
        reporter.on_user_print(("hello", False, True))
        assert stdout_buffer.getvalue() == "       | hello\n"

    def test_raw_mode_no_prefix_no_markup(self, stdout_buffer: io.StringIO) -> None:
        reporter = AsciiReporter()
        reporter.on_user_print(("[bold]raw[/]", True, True))
        # raw bypasses both markup-strip and prefix
        assert stdout_buffer.getvalue() == "[bold]raw[/]\n"

    def test_prefix_false_no_bar(self, stdout_buffer: io.StringIO) -> None:
        reporter = AsciiReporter()
        reporter.on_user_print(("Results: /tmp/foo", False, False))
        # No bar - visually a section line, not attached to a case.
        assert stdout_buffer.getvalue() == "Results: /tmp/foo\n"


class TestRichReporterUserPrint:
    """Rich reporter handles the 3-tuple payload."""

    def _make_reporter(self) -> RichReporter:
        # RichReporter pulls deps from the bus; we only exercise on_user_print.
        return RichReporter.__new__(RichReporter)

    def test_default_adds_bar_prefix(self, stdout_buffer: io.StringIO) -> None:
        reporter = self._make_reporter()
        reporter.on_user_print(("hello", False, True))
        assert "│" in stdout_buffer.getvalue()
        assert "hello" in stdout_buffer.getvalue()

    def test_prefix_false_no_bar(self, stdout_buffer: io.StringIO) -> None:
        reporter = self._make_reporter()
        reporter.on_user_print(("Results: /tmp/foo", False, False))
        out = stdout_buffer.getvalue()
        assert "│" not in out
        assert "Results: /tmp/foo" in out


class TestConsolePrintPayload:
    """`console.print` builds the payload and dispatches to handlers."""

    def _captured_bus(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
        captured: list[tuple] = []
        bus = MagicMock()
        handler = MagicMock()
        handler.func = lambda payload: captured.append(payload)
        bus._handlers = {Event.USER_PRINT: [handler]}
        monkeypatch.setattr("protest.console.get_event_bus", lambda: bus)
        return captured

    def test_default_payload_carries_prefix_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured = self._captured_bus(monkeypatch)
        console.print("hi")
        assert captured == [("hi", False, True)]

    def test_prefix_false_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._captured_bus(monkeypatch)
        console.print("section line", prefix=False)
        assert captured == [("section line", False, False)]

    def test_raw_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._captured_bus(monkeypatch)
        console.print("[raw]", raw=True)
        assert captured == [("[raw]", True, True)]


class TestConsolePrintHandlerErrors:
    """Handler failures must surface on stderr instead of disappearing.

    Earlier behavior: `contextlib.suppress(Exception)` swallowed any handler
    raise. A reporter bug (e.g. malformed Rich markup) made `console.print`
    silently no-op - users assumed the call did nothing.
    """

    def _bus_with_failing_handler(
        self, monkeypatch: pytest.MonkeyPatch, exc: Exception
    ) -> None:
        bus = MagicMock()
        handler = MagicMock()

        def boom(_payload: tuple) -> None:
            raise exc

        handler.func = boom
        bus._handlers = {Event.USER_PRINT: [handler]}
        monkeypatch.setattr("protest.console.get_event_bus", lambda: bus)

    def test_handler_exception_is_surfaced_on_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stderr = io.StringIO()
        monkeypatch.setattr("protest.console.real_stderr", lambda: stderr)
        self._bus_with_failing_handler(monkeypatch, RuntimeError("boom"))

        console.print("anything")

        out = stderr.getvalue()
        assert "console.print: handler raised" in out
        assert "RuntimeError" in out
        assert "boom" in out

    def test_loop_continues_when_real_stderr_itself_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense in depth: if logging the error also fails, no cascade."""

        def raising_stderr() -> object:
            raise OSError("stderr broken")

        monkeypatch.setattr("protest.console.real_stderr", raising_stderr)
        self._bus_with_failing_handler(monkeypatch, RuntimeError("boom"))

        # Must not raise - the outer suppress() is the last line of defense.
        console.print("anything")

    def test_successful_handler_does_not_touch_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stderr = io.StringIO()
        monkeypatch.setattr("protest.console.real_stderr", lambda: stderr)

        bus = MagicMock()
        handler = MagicMock()
        handler.func = lambda _payload: None  # no-op, no raise
        bus._handlers = {Event.USER_PRINT: [handler]}
        monkeypatch.setattr("protest.console.get_event_bus", lambda: bus)

        console.print("ok")
        assert stderr.getvalue() == ""
