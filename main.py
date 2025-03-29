from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any, Callable, TypeVar, cast

from protest import ProTestSession, ProTestSuite, Scope, Use, Sync

# Main test session
test_session = ProTestSession()

# ====== SHARED FIXTURES ======

@test_session.fixture(scope=Scope.SESSION)
def config() -> dict[str, Any]:
    """Load test configuration."""
    print("Loading configuration")
    return {
        "database_url": "sqlite://test.db",
        "api_url": "https://api.example.com",
        "api_key": "test_key_123",
        "timeout": 5.0
    }

@test_session.fixture(scope=Scope.SESSION)
def http_client(config: dict[str, Any] = Use(config)) -> Generator[dict[str, Any], None, None]:
    """Create synchronous HTTP client."""
    print("Creating HTTP client")
    client = {
        "base_url": config["api_url"],
        "headers": {"Authorization": f"Bearer {config['api_key']}"}
    }
    yield client
    print("Closing HTTP client")

@test_session.fixture(scope=Scope.SESSION)
async def async_db_pool(config: dict[str, Any] = Use(config)) -> AsyncGenerator[str, None]:
    """Establish asynchronous database connection pool."""
    print(f"Creating async database pool: {config['database_url']}")
    await asyncio.sleep(0.1)  # Simulate connection setup
    yield f"pool:{config['database_url']}"
    await asyncio.sleep(0.1)  # Simulate connection teardown
    print("Closing async database pool")

user_suite = ProTestSuite(name="User Management")


# ====== USER SUITE FIXTURES ======

@user_suite.fixture(scope=Scope.FUNCTION)
async def user(async_db_pool: str = Use(async_db_pool)) -> AsyncGenerator[dict[str, Any], None]:
    """Create a test user."""
    print(f"Creating test user with {async_db_pool}")
    await asyncio.sleep(0.1)  # Simulate database operation
    user_data = {"id": 1, "name": "Test User", "email": "test@example.com"}
    yield user_data
    await asyncio.sleep(0.1)  # Simulate cleanup
    print(f"Deleting user {user_data['id']}")

@user_suite.fixture(scope=Scope.FUNCTION)
def user_token(user: dict[str, Any] = Use(Sync(user))) -> str:
    """Generate authentication token for user.

    This is a synchronous fixture that depends on an async fixture,
    using the Sync adapter.
    """
    print(f"Generating token for {user['name']}")
    return f"token_{user['id']}_123456"

# ====== USER SUITE TESTS ======

@user_suite.test
async def test_user_creation(user: dict[str, Any] = Use(user)) -> None:
    """Test async user creation."""
    print(f"Testing async user creation for {user['name']}")
    assert user["id"] == 1
    assert user["email"] == "test@example.com"
    await asyncio.sleep(0.1)  # Simulate test work

@user_suite.test
def test_user_authentication(user_token: str = Use(user_token)) -> None:
    """Test synchronous user authentication with token.

    This test is synchronous but depends on user_token fixture
    which itself depends on an async fixture via Sync adapter.
    """
    print(f"Testing authentication with token: {user_token}")
    assert user_token.startswith("token_1_")

# ====== API SUITE FIXTURES ======

api_suite = ProTestSuite(name="API Integration")


@api_suite.fixture(scope=Scope.FUNCTION)
async def api_client(config: dict[str, Any] = Use(config)) -> AsyncGenerator[dict[str, Any], None]:
    """Create async API client."""
    print("Creating async API client")
    await asyncio.sleep(0.1)  # Simulate client initialization
    client = {
        "base_url": config["api_url"],
        "headers": {"Authorization": f"Bearer {config['api_key']}"},
        "timeout": config["timeout"]
    }
    yield client
    await asyncio.sleep(0.1)  # Simulate client cleanup
    print("Closing async API client")

@api_suite.fixture(scope=Scope.FUNCTION)
async def mock_server() -> AsyncGenerator[str, None]:
    """Start a mock API server for testing."""
    print("Starting mock server")
    await asyncio.sleep(0.2)  # Simulate server startup
    server_url = "http://localhost:8000"
    yield server_url
    await asyncio.sleep(0.2)  # Simulate server shutdown
    print("Stopping mock server")


# ====== API SUITE TESTS ======

@api_suite.test
async def test_api_connection(
        api_client: dict[str, Any] = Use(api_client),
        mock_server: str = Use(mock_server)
) -> None:
    """Test API connection."""
    print(f"Testing API connection to {mock_server}")
    await asyncio.sleep(0.2)  # Simulate API call
    assert api_client["base_url"] == "https://api.example.com"
    assert api_client["timeout"] == 5.0

@api_suite.test(params=[
    {"endpoint": "/users", "status_code": 200},
    {"endpoint": "/products", "status_code": 200},
    {"endpoint": "/invalid", "status_code": 404}
])
async def test_api_endpoints(
        params: dict[str, Any],
        api_client: dict[str, Any] = Use(api_client),
        mock_server: str = Use(mock_server)
) -> None:
    """Test various API endpoints."""
    endpoint = params["endpoint"]
    expected_status = params["status_code"]

    print(f"Testing endpoint {endpoint} with expected status {expected_status}")
    await asyncio.sleep(0.1)  # Simulate API call

    # Simple status code validation for this example
    actual_status = 200 if endpoint.startswith("/") and endpoint != "/invalid" else 404
    assert actual_status == expected_status


# ====== DATA SUITE FIXTURES ======

data_suite = ProTestSuite(name="Data Processing")

@data_suite.fixture(scope=Scope.FUNCTION)
def sample_data() -> list[dict[str, Any]]:
    """Generate sample data for testing."""
    print("Generating sample data")
    return [
        {"id": 1, "value": 10},
        {"id": 2, "value": 20},
        {"id": 3, "value": 30},
    ]

@data_suite.fixture(scope=Scope.SUITE)
def data_processor(config: dict[str, Any] = Use(config)) -> Generator[dict[str, Any], None, None]:
    """Create data processor with configuration."""
    print("Initializing data processor")
    processor = {
        "config": config,
        "processed_count": 0
    }
    yield processor
    print(f"Shutting down data processor, processed {processor['processed_count']} items")


# ====== DATA SUITE TESTS ======

@data_suite.test
def test_data_processing(
        sample_data: list[dict[str, Any]] = Use(sample_data),
        data_processor: dict[str, Any] = Use(data_processor),
        config: dict[str, Any] = Use(config)  # Mixing session and suite fixtures
) -> None:
    """Test synchronous data processing."""
    print(f"Processing {len(sample_data)} items")

    total = sum(item["value"] for item in sample_data)
    assert total == 60

    # Update the processor state
    data_processor["processed_count"] += len(sample_data)

@data_suite.test
def test_with_async_db(
        sample_data: list[dict[str, Any]] = Use(sample_data),
        db_connection: str = Use(Sync(async_db_pool))  # Using async fixture in sync test
) -> None:
    """Test using a synchronized async database connection."""
    print(f"Testing with database connection: {db_connection}")
    assert "pool:" in db_connection
    assert len(sample_data) == 3

# Include all suites in the session
test_session.include_suite(user_suite)
test_session.include_suite(api_suite)
test_session.include_suite(data_suite)


# Add direct test to session (outside of any suite)
@test_session.test
def test_healthcheck(config: dict[str, Any] = Use(config)) -> None:
    """Basic healthcheck test at session level."""
    print("Running healthcheck")
    assert "api_key" in config
    assert config["api_url"] == "https://api.example.com"


"""
# CLI Usage Examples:

# Run all tests
protest example:test_session

# Run a specific suite
protest example:test_session --suite "User Management"

# Run a specific test
protest example:test_session --test test_healthcheck

"""