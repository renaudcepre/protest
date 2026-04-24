"""Tests for `real_stdout()` / `real_stderr()`.

These accessors replace the previous `getattr(sys.stdout, "_original", ...)`
duck-typing. They give reporters a typed way to bypass the per-test capture
wrapper, so renaming or removing the private attribute won't silently break
reporter output.
"""

from __future__ import annotations

import io
import sys

from protest.execution.capture import (
    TaskAwareStream,
    real_stderr,
    real_stdout,
)


class TestRealStdoutUnwrapsTaskAwareStream:
    def test_returns_stdout_when_not_wrapped(self) -> None:
        assert real_stdout() is sys.stdout

    def test_unwraps_wrapped_stream(self) -> None:
        buffer = io.StringIO()
        wrapper = TaskAwareStream(buffer)
        sys.stdout = wrapper  # type: ignore[assignment]
        try:
            assert real_stdout() is buffer
        finally:
            sys.stdout = sys.__stdout__


class TestRealStderrUnwrapsTaskAwareStream:
    def test_returns_stderr_when_not_wrapped(self) -> None:
        assert real_stderr() is sys.stderr

    def test_unwraps_wrapped_stream(self) -> None:
        buffer = io.StringIO()
        wrapper = TaskAwareStream(buffer)
        sys.stderr = wrapper  # type: ignore[assignment]
        try:
            assert real_stderr() is buffer
        finally:
            sys.stderr = sys.__stderr__
