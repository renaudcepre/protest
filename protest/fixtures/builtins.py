"""Built-in fixtures provided by ProTest.

These are function-scoped by default (auto-registered on first use).
"""

from protest.execution.capture import get_current_log_records
from protest.execution.log_capture import LogCapture


def caplog() -> LogCapture:
    """Capture log records during a test."""
    records = get_current_log_records()
    return LogCapture(records)
