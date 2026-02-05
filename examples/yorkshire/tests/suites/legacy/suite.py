"""Legacy suite - sync-only, sequential execution.

Demonstrates:
- max_concurrency=1 for sequential test execution
- Suite-level fixture with suite.bind()
- Sync fixtures and tests (no async)
"""

import time
from collections.abc import Generator
from typing import Annotated

from protest import ProTestSuite, Use, fixture

legacy_suite = ProTestSuite(
    "Legacy",
    description="Old sync-only code, no parallel execution",
    tags=["legacy"],
    max_concurrency=1,
)


# =============================================================================
# SUITE FIXTURE (bound to legacy_suite)
# =============================================================================


@fixture()
def fax_machine() -> Generator[str, None, None]:
    """Legacy fax machine - takes time to warm up and cool down."""
    print("  [legacy] warming up fax machine...")  # noqa: T201 - debug output for demo
    time.sleep(0.05)
    yield "fax_ready"
    print("  [legacy] fax machine cooling down")  # noqa: T201 - debug output for demo


legacy_suite.bind(fax_machine)


# =============================================================================
# LEGACY TESTS (all sync, sequential)
# =============================================================================


@legacy_suite.test()
def test_send_treat_order_by_fax(fax: Annotated[str, Use(fax_machine)]) -> None:
    """Send treat order via fax - old school."""
    time.sleep(0.05)
    assert fax == "fax_ready"


@legacy_suite.test()
def test_receive_vet_appointment_by_fax(fax: Annotated[str, Use(fax_machine)]) -> None:
    """Receive vet appointment confirmation via fax."""
    time.sleep(0.05)
    assert fax == "fax_ready"


@legacy_suite.test()
def test_fax_grandma_photos(fax: Annotated[str, Use(fax_machine)]) -> None:
    """Send yorkshire photos to grandma via fax."""
    time.sleep(0.05)
    assert fax == "fax_ready"
