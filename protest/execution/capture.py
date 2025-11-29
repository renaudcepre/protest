import io
import sys
from contextvars import ContextVar, Token
from typing import TextIO

_capture_buffer: ContextVar[io.StringIO | None] = ContextVar(
    "capture_buffer", default=None
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


class GlobalCapturePatch:
    def __init__(self) -> None:
        self._orig_stdout: TextIO | None = None
        self._orig_stderr: TextIO | None = None

    def __enter__(self) -> "GlobalCapturePatch":
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = TaskAwareStream(sys.stdout)  # type: ignore[assignment]
        sys.stderr = TaskAwareStream(sys.stderr)  # type: ignore[assignment]
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr


class CaptureCurrentTest:
    def __init__(self) -> None:
        self._buffer: io.StringIO | None = None
        self._token: Token[io.StringIO | None] | None = None

    def __enter__(self) -> io.StringIO:
        self._buffer = io.StringIO()
        self._token = _capture_buffer.set(self._buffer)
        return self._buffer

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._token is not None:
            _capture_buffer.reset(self._token)
