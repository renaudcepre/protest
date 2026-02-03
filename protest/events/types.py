"""Event types for the event bus."""

from enum import Enum


class Event(Enum):
    """Events emitted during test execution."""

    COLLECTION_FINISH = "collection_finish"
    SESSION_START = "session_start"
    SESSION_SETUP_DONE = "session_setup_done"
    SESSION_TEARDOWN_START = "session_teardown_start"
    SESSION_END = "session_end"
    SESSION_COMPLETE = "session_complete"
    SUITE_START = "suite_start"
    SUITE_SETUP_DONE = "suite_setup_done"
    SUITE_TEARDOWN_START = "suite_teardown_start"
    SUITE_END = "suite_end"
    TEST_START = "test_start"
    TEST_ACQUIRED = "test_acquired"
    TEST_SETUP_DONE = "test_setup_done"
    TEST_TEARDOWN_START = "test_teardown_start"
    TEST_RETRY = "test_retry"
    TEST_PASS = "test_pass"  # noqa: S105 - false positive, not a password
    TEST_FAIL = "test_fail"
    TEST_SKIP = "test_skip"
    TEST_XFAIL = "test_xfail"
    TEST_XPASS = "test_xpass"
    WAITING_HANDLERS = "waiting_handlers"
    HANDLER_START = "handler_start"
    HANDLER_END = "handler_end"
    FIXTURE_SETUP_START = "fixture_setup_start"
    FIXTURE_SETUP_DONE = "fixture_setup_done"
    FIXTURE_TEARDOWN_START = "fixture_teardown_start"
    FIXTURE_TEARDOWN_DONE = "fixture_teardown_done"
    SESSION_INTERRUPTED = "session_interrupted"
