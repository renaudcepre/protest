from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Generator
from typing import Annotated, Any

from protest import ProTestSession, ProTestSuite, Sync

from src.scope import Scope
from src.use import Use

logger = logging.getLogger(__name__)

# Main test session
logger.debug("Creating main test session")
test_session = ProTestSession()

# ====== SHARED FIXTURES ======


@test_session.fixture(scope=Scope.SESSION)
def config() -> dict[str, Any]:
    """Load test configuration."""
    logger.debug("Initializing config fixture")
    return {
        "database_url": "sqlite://test.db",
        "api_url": "https://api.example.com",
        "api_key": "test_key_123",
        "timeout": 5.0,
    }


@test_session.fixture(scope=Scope.SESSION)
def http_client(config: Annotated[dict[str, Any], Use(config)]) -> Generator[dict[str, Any], None, None]:
    """Create synchronous HTTP client."""
    logger.debug("Setting up HTTP client with config")
    client = {"base_url": config["api_url"], "headers": {"Authorization": f"Bearer {config['api_key']}"}}
    logger.debug(f"HTTP client created: {client}")
    yield client
    logger.debug("HTTP client teardown")


@test_session.fixture(scope=Scope.SESSION)
async def async_db_pool(config: Annotated[dict[str, Any], Use(config)]) -> AsyncGenerator[str, None]:
    """Establish asynchronous database connection pool."""
    logger.debug(f"Setting up async DB pool with config: {config}")
    await asyncio.sleep(0.1)  # Simulate connection setup
    pool_url = f"pool:{config['database_url']}"
    logger.debug(f"Async DB pool created: {pool_url}")
    yield pool_url
    logger.debug("Cleaning up async DB pool")
    await asyncio.sleep(0.1)  # Simulate connection teardown


logger.debug("Creating User Management suite")
user_suite = ProTestSuite(name="User Management")

test_session.include_suite(user_suite)


# ====== USER SUITE FIXTURES ======


@user_suite.fixture(scope=Scope.FUNCTION)
async def user(async_db_pool: Annotated[str, Use(async_db_pool)]) -> AsyncGenerator[dict[str, Any], None]:
    """Create a test user."""
    logger.debug(f"Creating test user with DB pool: {async_db_pool}")
    await asyncio.sleep(0.1)  # Simulate database operation
    user_data = {"id": 1, "name": "Test User", "email": "test@example.com"}
    logger.debug(f"Test user created: {user_data}")
    yield user_data
    logger.debug("Cleaning up test user")
    await asyncio.sleep(0.1)  # Simulate cleanup


@user_suite.fixture(scope=Scope.FUNCTION)
def user_token(user: Annotated[dict[str, Any], Use(Sync(user))]) -> str:
    """Generate authentication token for user.

    This is a synchronous fixture that depends on an async fixture,
    using the Sync adapter.
    """
    logger.debug(f"Generating user token for user: {user}")
    token = f"token_{user['id']}_123456"
    logger.debug(f"Generated token: {token}")
    return token


# ====== USER SUITE TESTS ======


@user_suite.test
async def test_user_creation(user: Annotated[dict[str, Any], Use(user)]) -> None:
    """Test async user creation."""
    logger.debug(f"Testing user creation with user: {user}")
    assert user["id"] == 1
    assert user["email"] == "test@example.com"
    logger.debug("User creation assertions passed")
    await asyncio.sleep(0.1)  # Simulate test work


@user_suite.test
def test_user_authentication(user_token: Annotated[str, Use(user_token)]) -> None:
    """Test synchronous user authentication with token.

    This test is synchronous but depends on user_token fixture
    which itself depends on an async fixture via Sync adapter.
    """
    logger.debug(f"Testing user authentication with token: {user_token}")
    assert user_token.startswith("token_1_")
    logger.debug("User authentication assertions passed")


# ====== API SUITE FIXTURES ======

logger.debug("Creating API Integration suite")
api_suite = ProTestSuite(name="API Integration")


@api_suite.fixture(scope=Scope.FUNCTION)
async def api_client(config: Annotated[dict[str, Any], Use(config)]) -> AsyncGenerator[dict[str, Any], None]:
    """Create async API client."""
    logger.debug(f"Creating async API client with config: {config}")
    await asyncio.sleep(0.1)  # Simulate client initialization
    client = {
        "base_url": config["api_url"],
        "headers": {"Authorization": f"Bearer {config['api_key']}"},
        "timeout": config["timeout"],
    }
    logger.debug(f"Async API client created: {client}")
    yield client
    logger.debug("Cleaning up async API client")
    await asyncio.sleep(0.1)  # Simulate client cleanup


@api_suite.fixture(scope=Scope.FUNCTION)
async def mock_server() -> AsyncGenerator[str, None]:
    """Start a mock API server for testing."""
    logger.debug("Starting mock API server")
    await asyncio.sleep(0.2)  # Simulate server startup
    server_url = "http://localhost:8000"
    logger.debug(f"Mock server started at: {server_url}")
    yield server_url
    logger.debug("Shutting down mock API server")
    await asyncio.sleep(0.2)  # Simulate server shutdown


# ====== API SUITE TESTS ======


@api_suite.test
async def test_api_connection(
    api_client: Annotated[dict[str, Any], Use(api_client)], mock_server: Annotated[str, Use(mock_server)]
) -> None:
    """Test API connection."""
    logger.debug(f"Testing API connection with client: {api_client} and server: {mock_server}")
    await asyncio.sleep(0.2)  # Simulate API call
    assert api_client["base_url"] == "https://api.example.com"
    assert api_client["timeout"] == 5.0
    logger.debug("API connection assertions passed")


@api_suite.test(
    params=[
        {"endpoint": "/users", "status_code": 200},
        {"endpoint": "/products", "status_code": 200},
        {"endpoint": "/invalid", "status_code": 404},
    ]
)
async def test_api_endpoints(
    params: dict[str, Any],
    api_client: Annotated[dict[str, Any], Use(api_client)],
    mock_server: Annotated[str, Use(mock_server)],
) -> None:
    """Test various API endpoints."""
    endpoint = params["endpoint"]
    expected_status = params["status_code"]
    logger.debug(f"Testing API endpoint: {endpoint} with expected status: {expected_status}")
    logger.debug(f"Using API client: {api_client} and mock server: {mock_server}")

    await asyncio.sleep(0.1)  # Simulate API call

    # Simple status code validation for this example
    actual_status = 200 if endpoint.startswith("/") and endpoint != "/invalid" else 404
    logger.debug(f"Actual status: {actual_status}, expected: {expected_status}")
    assert actual_status == expected_status
    logger.debug("API endpoint test assertions passed")


# ====== DATA SUITE FIXTURES ======

logger.debug("Creating Data Processing suite")
data_suite = ProTestSuite(name="Data Processing")


@data_suite.fixture(scope=Scope.FUNCTION)
def sample_data() -> list[dict[str, Any]]:
    """Generate sample data for testing."""
    logger.debug("Generating sample data")
    data = [
        {"id": 1, "value": 10},
        {"id": 2, "value": 20},
        {"id": 3, "value": 30},
    ]
    logger.debug(f"Sample data generated: {data}")
    return data


@data_suite.fixture(scope=Scope.SUITE)
def data_processor(config: Annotated[dict[str, Any], Use(config)]) -> Generator[dict[str, Any], None, None]:
    """Create data processor with configuration."""
    logger.debug(f"Creating data processor with config: {config}")
    processor = {"config": config, "processed_count": 0}
    logger.debug(f"Data processor created: {processor}")
    yield processor
    logger.debug(f"Cleaning up data processor. Final state: {processor}")


# ====== DATA SUITE TESTS ======


@data_suite.test
def test_data_processing(
    sample_data: Annotated[list[dict[str, Any]], Use(sample_data)],
    data_processor: Annotated[dict[str, Any], Use(data_processor)],
    config: Annotated[dict[str, Any], Use(config)],  # Mixing session and suite fixtures
) -> None:
    """Test synchronous data processing."""
    logger.debug(f"Testing data processing with sample data: {sample_data}")
    logger.debug(f"Using data processor: {data_processor} and config: {config}")

    total = sum(item["value"] for item in sample_data)
    logger.debug(f"Calculated total: {total}")
    assert total == 60

    # Update the processor state
    data_processor["processed_count"] += len(sample_data)
    logger.debug(f"Updated processor state: {data_processor}")


@data_suite.test
def test_with_async_db(
    sample_data: Annotated[list[dict[str, Any]], Use(sample_data)],
    db_connection: Annotated[str, Use(Sync(async_db_pool))],  # Using async fixture in sync test
) -> None:
    """Test using a synchronized async database connection."""
    logger.debug(f"Testing with async DB connection: {db_connection}")
    logger.debug(f"Using sample data: {sample_data}")

    assert "pool:" in db_connection
    logger.debug("DB connection assertion passed")

    assert len(sample_data) == 3
    logger.debug("Sample data length assertion passed")


# Include all suites in the session
logger.debug("Including all suites in the test session")

test_session.include_suite(api_suite)
test_session.include_suite(data_suite)


# Add direct test to session (outside of any suite)
@test_session.test
def test_healthcheck(config: Annotated[dict[str, Any], Use(config)]) -> None:
    """Basic healthcheck test at session level."""
    logger.debug(f"Running healthcheck test with config: {config}")
    assert "api_key" in config
    assert config["api_url"] == "https://api.example.com"
    logger.debug("Healthcheck assertions passed")


"""
# CLI Usage Examples:

# Run all tests
protest example:test_session

# Run a specific suite
protest example:test_session --suite "User Management"

# Run a specific test
protest example:test_session --test test_healthcheck

"""
