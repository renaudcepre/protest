"""Built-in fixtures provided by ProTest.

These are function-scoped by default (auto-registered on first use).
"""

from collections.abc import Generator

from protest.execution.capture import LogCaptureContext
from protest.execution.log_capture import LogCapture


def caplog() -> Generator[LogCapture, None, None]:
    """Capture log records during a test."""
    with LogCaptureContext() as records:
        yield LogCapture(records)
