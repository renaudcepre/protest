from end_to_end import e2e_suite
from protest_cases import protest_suite
from unit import unit_suite

from protest import ProTestSession

session = ProTestSession()

session.include_suite(e2e_suite)
session.include_suite(unit_suite)
session.include_suite(protest_suite)


@session.test
def test_session_health() -> None:
    """Basic session health check."""
    assert True
