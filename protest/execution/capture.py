import io
import logging
import sys
from collections.abc import Callable
from contextlib import suppress
from contextvars import ContextVar, Token
from dataclasses import dataclass
from logging import LogRecord
from typing import TextIO

from protest.compat import Self

_capture_buffer: ContextVar[io.StringIO | None] = ContextVar(
    "capture_buffer", default=None
)

_log_records: ContextVar[list[LogRecord] | None] = ContextVar(
    "log_records", default=None
)

_current_node_id: ContextVar[str | None] = ContextVar("current_node_id", default=None)
_event_bus_ref: ContextVar[object | None] = ContextVar("event_bus_ref", default=None)


@dataclass(slots=True)
class CaptureState:
    buffer: io.StringIO | None = None
    active: bool = False


_session_setup = CaptureState()
_session_teardown = CaptureState()

_log_callbacks: list[Callable[[str, LogRecord], None]] = []
_stdout_callbacks: list[Callable[[str, str], None]] = []


def add_log_callback(callback: Callable[[str, LogRecord], None]) -> None:
    """Add a callback to be notified when a log is emitted during a test."""
    _log_callbacks.append(callback)


def remove_log_callback(callback: Callable[[str, LogRecord], None]) -> None:
    """Remove a log callback."""
    if callback in _log_callbacks:
        _log_callbacks.remove(callback)


def set_log_callback(callback: Callable[[str, LogRecord], None] | None) -> None:
    """Set a single callback (legacy API, replaces all existing callbacks)."""
    _log_callbacks.clear()
    if callback is not None:
        _log_callbacks.append(callback)


def add_stdout_callback(callback: Callable[[str, str], None]) -> None:
    """Add a callback for stdout/stderr writes. Args: (node_id, data)."""
    _stdout_callbacks.append(callback)


def remove_stdout_callback(callback: Callable[[str, str], None]) -> None:
    """Remove a stdout callback."""
    if callback in _stdout_callbacks:
        _stdout_callbacks.remove(callback)


def set_current_node_id(node_id: str | None) -> Token[str | None]:
    """Set the current test's node_id for log tracking."""
    return _current_node_id.set(node_id)


def reset_current_node_id(token: Token[str | None]) -> None:
    """Reset the current test's node_id using the token."""
    # Token may be from different context (task cancellation during threadpool).
    # Safe: value is overwritten by next set() at test start anyway.
    with suppress(ValueError):
        _current_node_id.reset(token)


def set_session_setup_capture(enabled: bool) -> None:
    """Enable/disable session setup capture buffer."""
    if enabled:
        _session_setup.buffer = io.StringIO()
    _session_setup.active = enabled


def get_session_setup_output() -> str:
    """Get captured session setup output."""
    return _session_setup.buffer.getvalue() if _session_setup.buffer else ""


def set_session_teardown_capture(enabled: bool) -> None:
    """Enable/disable session teardown capture buffer."""
    if enabled:
        _session_teardown.buffer = io.StringIO()
    _session_teardown.active = enabled


def get_session_teardown_output() -> str:
    """Get captured session teardown output."""
    return _session_teardown.buffer.getvalue() if _session_teardown.buffer else ""


def set_event_bus(bus: object) -> Token[object | None]:
    """Set event bus reference for console.print() access."""
    return _event_bus_ref.set(bus)


def reset_event_bus(token: Token[object | None]) -> None:
    """Reset event bus reference."""
    _event_bus_ref.reset(token)


def get_event_bus() -> object | None:
    """Get current event bus (for console.print)."""
    return _event_bus_ref.get()


class TaskAwareStream:
    def __init__(self, original_stream: TextIO, show_output: bool = False) -> None:
        self._original = original_stream
        self._show_output = show_output

    def write(self, data: str) -> int:
        buffer = _capture_buffer.get()
        if buffer is not None:
            node_id = _current_node_id.get()
            if node_id and _stdout_callbacks:
                for callback in _stdout_callbacks:
                    callback(node_id, data)
            buffer.write(data)
            if self._show_output:
                self._original.write(data)
            return len(data)
        if _session_setup.active and _session_setup.buffer:
            return _session_setup.buffer.write(data)
        if _session_teardown.active and _session_teardown.buffer:
            return _session_teardown.buffer.write(data)
        return self._original.write(data)

    def flush(self) -> None:
        buffer = _capture_buffer.get()
        if buffer is not None:
            buffer.flush()
        self._original.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._original, name)


class TaskAwareLogHandler(logging.Handler):
    def emit(self, record: LogRecord) -> None:
        records = _log_records.get()
        if records is not None:
            records.append(record)

        node_id = _current_node_id.get()
        if node_id and _log_callbacks:
            for callback in _log_callbacks:
                callback(node_id, record)


class GlobalCapturePatch:
    # Track the current handler for deterministic cleanup of orphaned handlers.
    # If a previous run crashed before __exit__, we can clean up the exact handler.
    _current_handler: TaskAwareLogHandler | None = None

    def __init__(self, show_output: bool = False) -> None:
        self._show_output = show_output
        self._orig_stdout: TextIO | None = None
        self._orig_stderr: TextIO | None = None
        self._log_handler: TaskAwareLogHandler | None = None
        self._orig_log_level: int | None = None

    def __enter__(self) -> Self:
        # Clean up orphaned handler from a crashed previous run.
        # This is deterministic: we only clean up the specific handler we track.
        if GlobalCapturePatch._current_handler is not None:
            if GlobalCapturePatch._current_handler in logging.root.handlers:
                logging.root.removeHandler(GlobalCapturePatch._current_handler)
            GlobalCapturePatch._current_handler = None

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = TaskAwareStream(sys.stdout, self._show_output)
        sys.stderr = TaskAwareStream(sys.stderr, self._show_output)

        self._orig_log_level = logging.root.level
        logging.root.setLevel(logging.NOTSET)

        self._log_handler = TaskAwareLogHandler()
        self._log_handler.setLevel(logging.DEBUG)
        logging.root.addHandler(self._log_handler)
        GlobalCapturePatch._current_handler = self._log_handler
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
        if self._log_handler is not None:
            logging.root.removeHandler(self._log_handler)
            if GlobalCapturePatch._current_handler is self._log_handler:
                GlobalCapturePatch._current_handler = None
        if self._orig_log_level is not None:
            logging.root.setLevel(self._orig_log_level)


def get_current_log_records() -> list[LogRecord]:
    """Get the current test's log records list."""
    records = _log_records.get()
    if records is None:
        return []
    return records


class CaptureCurrentTest:
    def __init__(self) -> None:
        self._buffer: io.StringIO | None = None
        self._token: Token[io.StringIO | None] | None = None
        self._log_records: list[LogRecord] | None = None
        self._log_token: Token[list[LogRecord] | None] | None = None

    def __enter__(self) -> io.StringIO:
        self._buffer = io.StringIO()
        self._token = _capture_buffer.set(self._buffer)
        self._log_records = []
        self._log_token = _log_records.set(self._log_records)
        return self._buffer

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        # Token may be from different context (task cancellation during threadpool).
        # Safe: each context has its own ContextVar copy, next set() overwrites anyway.
        if self._token is not None:
            with suppress(ValueError):
                _capture_buffer.reset(self._token)
        if self._log_token is not None:
            with suppress(ValueError):
                _log_records.reset(self._log_token)
