from protest.entities import LogCapture
from protest.execution.capture import get_current_log_records


def caplog() -> LogCapture:
    """Capture log records during a test."""
    records = get_current_log_records()
    return LogCapture(records)
