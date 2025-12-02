import io
import logging
import sys
from contextvars import ContextVar, Token
from logging import LogRecord
from typing import TextIO

_capture_buffer: ContextVar[io.StringIO | None] = ContextVar(
    "capture_buffer", default=None
)

_log_records: ContextVar[list[LogRecord] | None] = ContextVar(
    "log_records", default=None
)


class TaskAwareStream:
    def __init__(self, original_stream: TextIO) -> None:
        self._original = original_stream

    def write(self, data: str) -> int:
        buffer = _capture_buffer.get()
        if buffer is not None:
            return buffer.write(data)
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


class GlobalCapturePatch:
    def __init__(self) -> None:
        self._orig_stdout: TextIO | None = None
        self._orig_stderr: TextIO | None = None
        self._log_handler: TaskAwareLogHandler | None = None
        self._orig_log_level: int | None = None

    def __enter__(self) -> "GlobalCapturePatch":
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = TaskAwareStream(sys.stdout)
        sys.stderr = TaskAwareStream(sys.stderr)

        self._orig_log_level = logging.root.level
        logging.root.setLevel(logging.NOTSET)
        self._log_handler = TaskAwareLogHandler()
        self._log_handler.setLevel(logging.DEBUG)
        logging.root.addHandler(self._log_handler)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
        if self._log_handler is not None:
            logging.root.removeHandler(self._log_handler)
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
        if self._token is not None:
            _capture_buffer.reset(self._token)
        if self._log_token is not None:
            _log_records.reset(self._log_token)
