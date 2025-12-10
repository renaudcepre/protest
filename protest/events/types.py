"""Event types for the event bus."""

from enum import Enum


class Event(Enum):
    """Events emitted during test execution."""

    COLLECTION_FINISH = "collection_finish"
    SESSION_START = "session_start"
    SESSION_SETUP_START = "session_setup_start"
    SESSION_SETUP_DONE = "session_setup_done"
    SESSION_TEARDOWN_START = "session_teardown_start"
    SESSION_TEARDOWN_DONE = "session_teardown_done"
    SESSION_END = "session_end"
    SESSION_COMPLETE = "session_complete"
    SUITE_START = "suite_start"
    SUITE_END = "suite_end"
    SUITE_TEARDOWN_START = "suite_teardown_start"
    SUITE_TEARDOWN_DONE = "suite_teardown_done"
    TEST_START = "test_start"
    TEST_ACQUIRED = "test_acquired"
    TEST_SETUP_DONE = "test_setup_done"
    TEST_TEARDOWN_START = "test_teardown_start"
    TEST_RETRY = "test_retry"
    TEST_PASS = "test_pass"  # noqa: S105
    TEST_FAIL = "test_fail"
    TEST_SKIP = "test_skip"
    TEST_XFAIL = "test_xfail"
    TEST_XPASS = "test_xpass"
    WAITING_HANDLERS = "waiting_handlers"
    HANDLER_START = "handler_start"
    HANDLER_END = "handler_end"
    FIXTURE_SETUP = "fixture_setup"
    FIXTURE_TEARDOWN = "fixture_teardown"
    SESSION_INTERRUPTED = "session_interrupted"
