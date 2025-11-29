"""ProTest Demo - Showcasing all implemented features."""

from collections.abc import Generator
from typing import Annotated

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.di.markers import Use

from slack_notifier import FakeSlackNotifier

session = ProTestSession()
api_suite = ProTestSuite("API Tests")
unit_suite = ProTestSuite("Unit Tests")

session.use(FakeSlackNotifier(delay=0.5))


# =============================================================================
# SESSION-SCOPED FIXTURES (created once, shared across all suites)
# =============================================================================


@session.fixture(scope=Scope.SESSION)
def database() -> Generator[str, None, None]:
    print("    [SESSION setup] database connection")
    yield "db_connection"
    print("    [SESSION teardown] database disconnected")


@session.fixture(scope=Scope.SESSION)
def config() -> dict[str, str]:
    return {"env": "test", "debug": "true"}


@session.fixture(scope=Scope.SESSION)
def cache(cfg: Annotated[dict[str, str], Use(config)]) -> str:
    return f"redis://{cfg['env']}.cache.local"


# =============================================================================
# INCLUDE SUITES (must be done before defining suite fixtures)
# =============================================================================

session.include_suite(api_suite)
session.include_suite(unit_suite)


# =============================================================================
# API SUITE - SUITE-SCOPED FIXTURES (created once per suite)
# =============================================================================


@api_suite.fixture(scope=Scope.SUITE)
def api_client(db: Annotated[str, Use(database)]) -> Generator[str, None, None]:
    print("    [SUITE setup] api_client created")
    yield f"APIClient({db})"
    print("    [SUITE teardown] api_client closed")


@api_suite.fixture(scope=Scope.SUITE)
def auth_token(
    client: Annotated[str, Use(api_client)],
    cache_url: Annotated[str, Use(cache)],
) -> str:
    return f"token_for_{client}_via_{cache_url}"


# =============================================================================
# API SUITE - FUNCTION-SCOPED FIXTURES (created fresh for each test)
# =============================================================================


@api_suite.fixture(scope=Scope.FUNCTION)
def request_id() -> Generator[str, None, None]:
    import random

    req_id = f"req_{random.randint(1000, 9999)}"
    print(f"    [FUNCTION setup] request {req_id}")
    yield req_id
    print(f"    [FUNCTION teardown] request {req_id} completed")


# =============================================================================
# API SUITE TESTS
# =============================================================================


@api_suite.test
def test_api_client_creation(client: Annotated[str, Use(api_client)]) -> None:
    assert "APIClient" in client
    assert "db_connection" in client


@api_suite.test
def test_api_with_auth(token: Annotated[str, Use(auth_token)]) -> None:
    assert "token_for_" in token
    assert "cache" in token


@api_suite.test
def test_api_request(
    client: Annotated[str, Use(api_client)],
    req_id: Annotated[str, Use(request_id)],
) -> None:
    assert client.startswith("APIClient")
    assert req_id.startswith("req_")


@api_suite.test
def test_api_broken() -> None:
    raise AssertionError("Intentional failure to demo error output")


# =============================================================================
# UNIT SUITE - FUNCTION-SCOPED FIXTURES
# =============================================================================


@unit_suite.fixture(scope=Scope.FUNCTION)
def temp_file() -> Generator[str, None, None]:
    print("    [FUNCTION setup] temp file created")
    yield "/tmp/test_file.txt"
    print("    [FUNCTION teardown] temp file deleted")


@unit_suite.fixture(scope=Scope.FUNCTION)
def counter() -> int:
    return 42


# =============================================================================
# UNIT SUITE TESTS
# =============================================================================


@unit_suite.test
def test_simple_assertion() -> None:
    expected_sum = 2
    assert expected_sum == 1 + 1


@unit_suite.test
def test_with_temp_file(path: Annotated[str, Use(temp_file)]) -> None:
    assert path.endswith(".txt")


@unit_suite.test
def test_with_counter(count: Annotated[int, Use(counter)]) -> None:
    expected_count = 42
    assert count == expected_count


@unit_suite.test
def test_with_session_fixture(db: Annotated[str, Use(database)]) -> None:
    assert db == "db_connection"


# =============================================================================
# SESSION-LEVEL TESTS (not in any suite)
# =============================================================================


@session.test
def test_config_loaded(cfg: Annotated[dict[str, str], Use(config)]) -> None:
    assert cfg["env"] == "test"
    assert cfg["debug"] == "true"


@session.test
def test_cache_url(url: Annotated[str, Use(cache)]) -> None:
    assert "test.cache.local" in url
