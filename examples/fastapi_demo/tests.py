"""FastAPI async tests - showcasing parallel HTTP calls."""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
from fastapi.testclient import TestClient

from app import app
from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.di.markers import Use

session = ProTestSession()


@session.fixture(scope=Scope.SESSION)
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for the FastAPI app."""
    print("  [FIXTURE] Creating async client...")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client
    print("  [FIXTURE] Async client closed")


@session.fixture(scope=Scope.SESSION)
def sync_client() -> TestClient:
    """Sync HTTP client for comparison."""
    return TestClient(app)


@session.test
async def test_health(client: Annotated[httpx.AsyncClient, Use(async_client)]) -> None:
    """Simple async health check."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@session.test
async def test_get_user(client: Annotated[httpx.AsyncClient, Use(async_client)]) -> None:
    """Test single user fetch."""
    response = await client.get("/users/1")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"


@session.test
async def test_parallel_user_fetches(
    client: Annotated[httpx.AsyncClient, Use(async_client)],
) -> None:
    """Fetch 3 users in parallel - should take ~100ms, not 300ms."""
    start = time.perf_counter()

    responses = await asyncio.gather(
        client.get("/users/1"),
        client.get("/users/2"),
        client.get("/users/3"),
    )

    duration = time.perf_counter() - start

    assert all(resp.status_code == 200 for resp in responses)
    names = [resp.json()["name"] for resp in responses]
    assert names == ["Alice", "Bob", "Charlie"]

    print(f"  [PARALLEL] 3 users fetched in {duration:.3f}s (should be ~0.1s)")
    max_expected_duration = 0.2
    assert duration < max_expected_duration, f"Parallel calls took {duration:.3f}s, expected < 0.2s"


@session.test
async def test_parallel_mixed_endpoints(
    client: Annotated[httpx.AsyncClient, Use(async_client)],
) -> None:
    """Fetch users and products in parallel."""
    start = time.perf_counter()

    responses = await asyncio.gather(
        client.get("/users/1"),
        client.get("/users/2"),
        client.get("/products/1"),
        client.get("/products/2"),
    )

    duration = time.perf_counter() - start

    assert all(resp.status_code == 200 for resp in responses)
    print(f"  [PARALLEL] 4 mixed endpoints in {duration:.3f}s")

    max_expected_duration = 0.2
    assert duration < max_expected_duration


@session.test
async def test_parallel_slow_endpoints(
    client: Annotated[httpx.AsyncClient, Use(async_client)],
) -> None:
    """3 slow endpoints (500ms each) in parallel - should take ~500ms, not 1500ms."""
    start = time.perf_counter()

    responses = await asyncio.gather(
        client.get("/slow"),
        client.get("/slow"),
        client.get("/slow"),
    )

    duration = time.perf_counter() - start

    assert all(resp.status_code == 200 for resp in responses)
    assert all(resp.json() == {"status": "done"} for resp in responses)

    print(f"  [PARALLEL] 3 slow endpoints in {duration:.3f}s (should be ~0.5s)")
    max_expected_duration = 0.7
    assert duration < max_expected_duration, f"Should be ~0.5s, got {duration:.3f}s"


@session.test
def test_sync_for_comparison(
    client: Annotated[TestClient, Use(sync_client)],
) -> None:
    """Sync test - just to show we can mix sync/async."""
    response = client.get("/health")
    assert response.status_code == 200