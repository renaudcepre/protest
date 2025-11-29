import asyncio
from typing import Annotated

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.di.markers import Use

session = ProTestSession()


# 1. Fixture Async
@session.fixture()
async def async_db():
    print("    [ASYNC FIXTURE] waiting for db...")
    await asyncio.sleep(0.01)
    print("    [ASYNC FIXTURE] db connected")
    return "DB Connection"


# 2. Fixture Sync which uses an Async fixture
@session.fixture()
def sync_service(db: Annotated[str, Use(async_db)]):
    print(f"    [SYNC FIXTURE] creating service with '{db}'")
    return f"Service({db})"


# 3. Test Async
@session.test
async def test_async_stuff(svc: Annotated[str, Use(sync_service)]):
    print("    [ASYNC TEST] doing async work...")
    await asyncio.sleep(0.01)
    assert "DB Connection" in svc
    print("    [ASYNC TEST] done")


# 4. Regular sync test
@session.test
def test_sync_stuff():
    assert True


# Let's add a sync fixture for the sync test
@session.fixture(scope=Scope.FUNCTION)
def sync_fixture():
    return "sync_data"


# 5. Sync test with sync fixture
@session.test
def test_sync_with_fixture(data: Annotated[str, Use(sync_fixture)]):
    assert data == "sync_data"
