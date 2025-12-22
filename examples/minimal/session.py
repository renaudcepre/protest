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
    print("  [session_db] setup")
    yield "session_db_value"
    print("  [session_db] teardown")


session.fixture(session_db)


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
    print(f"  [suite_client] setup (db={db})")
    yield "suite_client_value"
    print("  [suite_client] teardown")


my_suite.fixture(suite_client)


# =============================================================================
# TEST FIXTURE
# =============================================================================


@fixture()
def test_data(client: Annotated[str, Use(suite_client)]) -> Generator[str, None, None]:
    print(f"  [test_data] setup (client={client})")
    yield "test_data_value"
    print("  [test_data] teardown")



# =============================================================================
# TEST
# =============================================================================


@my_suite.test()
def test_all_fixtures(
    db: Annotated[str, Use(session_db)],
    client: Annotated[str, Use(suite_client)],
    data: Annotated[str, Use(test_data)],
) -> None:
    print(f"  [test] db={db}, client={client}, data={data}")
    assert db == "session_db_value"
    assert client == "suite_client_value"
    assert data == "test_data_value"

@my_suite.test()
def test_all_fixtures(
    db: Annotated[str, Use(session_db)],
    client: Annotated[str, Use(suite_client)],
    data: Annotated[str, Use(test_data)],
) -> None:
    print(f"  [test] db={db}, client={client}, data={data}")
    assert db == "session_db_value"
    assert client == "suite_client_value"
    assert data == "test_data_value"
