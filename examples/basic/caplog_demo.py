"""Demo: Structured Log Capture (caplog).

Run with: uv run protest run examples/basic/caplog_demo:session

This demo shows how to capture and inspect logs in tests:
- caplog.records: List of LogRecord objects
- caplog.text: Text representation for quick debugging
- caplog.at_level(): Filter logs by level
- caplog.clear(): Reset captured logs mid-test
"""

import logging
from typing import Annotated

from protest import ProTestSession, Use, caplog
from protest.execution.log_capture import LogCapture

session = ProTestSession()

logger = logging.getLogger("payment")


def process_payment(card_number: str) -> bool:
    if card_number.startswith("0000"):
        logger.error("Payment declined: invalid card")
        return False
    logger.info(f"Payment processed for card ending in {card_number[-4:]}")
    return True


@session.test()
def test_successful_payment(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """Test that successful payment logs INFO."""
    result = process_payment("4111111111111111")

    assert result is True
    assert len(logs.records) == 1
    assert logs.records[0].levelname == "INFO"
    assert "Payment processed" in logs.records[0].getMessage()


@session.test()
def test_failed_payment(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """Test that failed payment logs ERROR."""
    result = process_payment("0000111122223333")

    assert result is False
    assert len(logs.records) == 1
    assert logs.records[0].levelname == "ERROR"
    assert "Payment declined" in logs.text


@session.test()
def test_no_warnings_in_happy_path(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """Verify no warnings or errors in nominal case."""
    process_payment("4111111111111111")

    warnings_and_errors = logs.at_level("WARNING")
    assert len(warnings_and_errors) == 0


@session.test()
def test_multiple_operations(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """Test with clear() for multi-phase tests."""
    process_payment("4111111111111111")
    assert len(logs.records) == 1

    logs.clear()

    process_payment("0000111122223333")
    assert len(logs.records) == 1
    assert logs.records[0].levelname == "ERROR"


# =============================================================================
# Expected output:
#
#   --- Starting session ---
#
#   ✓ test_successful_payment
#   ✓ test_failed_payment
#   ✓ test_no_warnings_in_happy_path
#   ✓ test_multiple_operations
#
# Results: 4/4 passed
#
# Key features demonstrated:
# - Structured access to log records (levelname, getMessage())
# - Text representation for quick debugging (logs.text)
# - Level filtering (logs.at_level("WARNING"))
# - Clearing logs mid-test (logs.clear())
# - Isolation: each test sees only its own logs
# =============================================================================
