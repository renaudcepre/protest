"""Event types for the event bus."""

from enum import Enum


class Event(Enum):
    """Events emitted during test execution."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_COMPLETE = "session_complete"
    SUITE_START = "suite_start"
    SUITE_END = "suite_end"
    TEST_PASS = "test_pass"  # noqa: S105
    TEST_FAIL = "test_fail"
