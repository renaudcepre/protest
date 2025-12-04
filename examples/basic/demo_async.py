"""Async fixtures demo - showcasing mixed sync/async fixtures and tests."""

import asyncio
from typing import Annotated

from protest import ProTestSession, Use
from protest.di.decorators import fixture

session = ProTestSession()


@session.fixture()
async def async_db():
    print("    [ASYNC FIXTURE] waiting for db...")
    await asyncio.sleep(0.01)
    print("    [ASYNC FIXTURE] db connected")
    return "DB Connection"


@session.fixture()
def sync_service(db: Annotated[str, Use(async_db)]):
    print(f"    [SYNC FIXTURE] creating service with '{db}'")
    return f"Service({db})"


@session.test()
async def test_async_stuff(svc: Annotated[str, Use(sync_service)]):
    print("    [ASYNC TEST] doing async work...")
    await asyncio.sleep(0.01)
    assert "DB Connection" in svc
    print("    [ASYNC TEST] done")


@session.test()
def test_sync_stuff():
    assert True


@fixture()
def sync_fixture():
    return "sync_data"


@session.test()
def test_sync_with_fixture(data: Annotated[str, Use(sync_fixture)]):
    assert data == "sync_data"
