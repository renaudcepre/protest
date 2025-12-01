"""Event types for the event bus."""

from enum import Enum


class Event(Enum):
    """Events emitted during test execution."""

    COLLECTION_FINISH = "collection_finish"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_COMPLETE = "session_complete"
    SUITE_START = "suite_start"
    SUITE_END = "suite_end"
    TEST_START = "test_start"
    TEST_SETUP_DONE = "test_setup_done"
    TEST_PASS = "test_pass"  # noqa: S105
    TEST_FAIL = "test_fail"
    WAITING_HANDLERS = "waiting_handlers"
    HANDLER_START = "handler_start"
    HANDLER_END = "handler_end"
