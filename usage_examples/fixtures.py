import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from protest import Scope, Use

from .main import session


@session.fixture(scope=Scope.SESSION)
def app_config() -> dict:
    """Global application configuration."""
    return {
        "database_url": "postgresql://test:test@localhost:5432/bookstore",
        "redis_url": "redis://localhost:6379/0",
        "api_base_url": "http://localhost:8000",
        "secret_key": "test_secret_key_12345",
        "jwt_expire_minutes": 30,
        "debug": True,
        "pool_size": 10,
    }


@session.fixture(scope=Scope.SESSION)
async def database_pool(
    config: Annotated[dict, Use(app_config)],
) -> AsyncGenerator[str, None]:
    """Database connection pool shared across all suites."""
    await asyncio.sleep(0.1)
    pool_id = f"db_pool_{hash(config['database_url']) % 1000}"
    yield pool_id
    await asyncio.sleep(0.05)


@session.fixture(scope=Scope.FUNCTION)
async def db_transaction(
    pool: Annotated[str, Use(database_pool)],
) -> AsyncGenerator[str, None]:
    """Database transaction with automatic rollback."""
    await asyncio.sleep(0.02)
    tx_id = f"tx_{hash(pool) % 100}"
    yield tx_id
    await asyncio.sleep(0.02)


@session.fixture(scope=Scope.SESSION)
async def redis_client(
    config: Annotated[dict, Use(app_config)],
) -> AsyncGenerator[str, None]:
    """Redis client shared across all suites."""
    await asyncio.sleep(0.05)
    client_id = f"redis_{hash(config['redis_url']) % 1000}"
    yield client_id
    await asyncio.sleep(0.03)


@session.fixture(scope=Scope.FUNCTION)
async def http_client(
    config: Annotated[dict, Use(app_config)],
) -> AsyncGenerator[dict, None, None]:
    """Basic HTTP client shared across multiple suites:
    - api_integration/ uses it directly
    - performance/ uses it directly
    - end_to_end/ wraps it in api_client with auth features
    """
    await asyncio.sleep(0.03)

    client = {
        "base_url": config["api_base_url"],
        "headers": {"Content-Type": "application/json"},
        "session_id": f"http_{hash(config['secret_key']) % 1000}",
    }

    yield client
    await asyncio.sleep(0.03)
