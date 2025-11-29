from typing import Annotated

from protest.core.runner import TestRunner
from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.di.markers import Use

session = ProTestSession()
api_suite = ProTestSuite("API Tests")
unit_suite = ProTestSuite("Unit Tests")


@session.fixture(scope=Scope.SESSION)
def database() -> str:
    print("  [setup] database connection")
    return "db_connection"


@session.fixture(scope=Scope.SESSION)
def config() -> dict[str, str]:
    return {"env": "test", "debug": "true"}


session.include_suite(api_suite)
session.include_suite(unit_suite)


@api_suite.fixture(scope=Scope.SUITE)
def api_client(db: Annotated[str, Use(database)]) -> str:
    print("  [setup] api_client")
    return f"client({db})"


@api_suite.test
def test_api_get(client: Annotated[str, Use(api_client)]) -> None:
    assert "client" in client


@api_suite.test
def test_api_post(client: Annotated[str, Use(api_client)]) -> None:
    assert client == "client(db_connection)"


@api_suite.test
def test_api_broken() -> None:
    assert False, "This test should fail"


@unit_suite.fixture(scope=Scope.FUNCTION)
def temp_data() -> str:
    return "temp"


@unit_suite.test
def test_unit_simple() -> None:
    assert True


@unit_suite.test
def test_unit_with_fixture(data: Annotated[str, Use(temp_data)]) -> None:
    assert data == "temp"


@session.test
def test_session_level(cfg: Annotated[dict[str, str], Use(config)]) -> None:
    assert cfg["env"] == "test"


if __name__ == "__main__":
    runner = TestRunner(session)
    success = runner.run()
    exit(0 if success else 1)
