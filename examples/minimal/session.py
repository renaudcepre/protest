"""Minimal example: 1 test, 3 fixtures (session, suite, test)."""

from collections.abc import Generator
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use, fixture

session = ProTestSession()


# =============================================================================
# SESSION FIXTURE
# =============================================================================


@fixture()
def session_db() -> Generator[str, None, None]:
    yield "session_db_value"


session.bind(session_db)


# =============================================================================
# SUITE
# =============================================================================

my_suite = ProTestSuite("MySuite")
session.add_suite(my_suite)


# =============================================================================
# SUITE FIXTURE
# =============================================================================


@fixture()
def suite_client(db: Annotated[str, Use(session_db)]) -> Generator[str, None, None]:
    yield "suite_client_value"


my_suite.bind(suite_client)


# =============================================================================
# TEST FIXTURE
# =============================================================================


@fixture()
def test_data(client: Annotated[str, Use(suite_client)]) -> Generator[str, None, None]:
    yield "test_data_value"


# =============================================================================
# TEST
# =============================================================================


@my_suite.test()
def test_all_fixtures(
    db: Annotated[str, Use(session_db)],
    client: Annotated[str, Use(suite_client)],
    data: Annotated[str, Use(test_data)],
) -> None:
    assert db == "session_db_value"
    assert client == "suite_client_value"
    assert data == "test_data_value"
