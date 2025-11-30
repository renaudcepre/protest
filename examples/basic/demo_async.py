import asyncio
from typing import Annotated

from protest import Scope, fixture
from protest.core.session import ProTestSession
from protest.di.markers import Use

session = ProTestSession()


@fixture(scope=Scope.SESSION)
async def async_db():
    print("    [ASYNC FIXTURE] waiting for db...")
    await asyncio.sleep(0.01)
    print("    [ASYNC FIXTURE] db connected")
    return "DB Connection"


@fixture(scope=Scope.SESSION)
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


def sync_fixture():
    return "sync_data"


@session.test()
def test_sync_with_fixture(data: Annotated[str, Use(sync_fixture)]):
    assert data == "sync_data"
