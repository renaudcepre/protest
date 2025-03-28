from __future__ import annotations
import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

from protest import Use, ProTestSession, ProTestSuite, Scope

# Session principale
test_session = ProTestSession()

# Suite de tests
test_suite = ProTestSuite(name="Test Suite")

# ====== FIXTURES ======

@test_session.fixture(scope=Scope.SESSION)
def config() -> dict[str, Any]:
    """Configuration de base."""
    print("Loading config")
    return {"api_key": "test_key"}

@test_session.fixture(scope=Scope.SESSION)
def db(config: dict[str, Any] = Use(config)) -> Generator[str, None, None]:
    """Connexion DB."""
    print(f"Connecting to DB")
    yield "db_connection"
    print("Closing DB")

@test_session.fixture(scope=Scope.FUNCTION)
def user(db: str = Use(db)) -> Generator[dict[str, Any], None, None]:
    """Utilisateur de test."""
    print(f"Creating user with {db}")
    yield {"id": 1, "name": "Test User"}
    print("Deleting user")

# ====== FIXTURES ASYNCHRONES ======

@test_session.fixture(scope=Scope.SESSION)
async def async_db(config: dict[str, Any] = Use(config)) -> AsyncGenerator[str, None]:
    """Pool de connexions async."""
    print("Creating async pool")
    await asyncio.sleep(0.1)
    yield "async_pool"
    await asyncio.sleep(0.1)
    print("Closing async pool")

@test_session.fixture(scope=Scope.FUNCTION)
async def async_user(async_db: str = Use(async_db)) -> AsyncGenerator[dict[str, Any], None]:
    """Utilisateur async."""
    print("Creating async user")
    await asyncio.sleep(0.1)
    yield {"id": 2, "name": "Async User"}
    await asyncio.sleep(0.1)
    print("Deleting async user")

# ====== TESTS ======

@test_suite.test
def test_sync(user: dict = Use(user)) -> None:
    """Test synchrone simple."""
    print(f"Testing sync with {user['name']}")
    assert True

@test_suite.test
async def test_async(async_user: dict = Use(async_user)) -> None:
    """Test asynchrone simple."""
    print(f"Testing async with {async_user['name']}")
    await asyncio.sleep(0.1)
    assert True

@test_suite.test(params=[
    {"name": "Test 1"},
    {"name": "Test 2"},
    {"name": "Test 3"}
])
def test_parametrized(params: dict[str, Any], user: dict = Use(user)) -> None:
    """Test paramétré simple."""
    print(f"Testing {params['name']}")
    assert True

# Inclusion de la suite
test_session.include_suite(test_suite)

if __name__ == "__main__":
    test_session.run()

"""
# CLI Usage Examples:

# Run all tests
protest main:test_session

# Run a specific suite
protest main:test_session --suite test_product_suite

# Run a specific test
protest main:test_session --test test_healthcheck

...
"""
