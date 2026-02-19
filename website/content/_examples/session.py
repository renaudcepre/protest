"""Minimal example: 1 test, 3 fixtures (session, suite, test)."""

from collections.abc import Iterator
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use, fixture


# doc:focus:start
@fixture()
def session_db() -> Iterator[str]:
    yield "session_db_value"
# doc:focus:end


@fixture()
def suite_client(db: Annotated[str, Use(session_db)]) -> Iterator[str]:
    yield "suite_client_value"


@fixture()
def test_data(client: Annotated[str, Use(suite_client)]) -> Iterator[str]:
    yield "test_data_value"


session = ProTestSession()
session.bind(session_db)

my_suite = ProTestSuite("MySuite")
my_suite.bind(suite_client)

session.add_suite(my_suite)


# doc:focus:start
@my_suite.test()
def test_all_fixtures(
    db: Annotated[str, Use(session_db)],
    client: Annotated[str, Use(suite_client)],
    data: Annotated[str, Use(test_data)],
) -> None:
    assert db == "session_db_value"
    assert client == "suite_client_value"
    assert data == "test_data_value"
# doc:focus:end
