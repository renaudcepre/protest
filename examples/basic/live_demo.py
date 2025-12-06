import asyncio
import time
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use

session = ProTestSession(concurrency=10)

api_suite = ProTestSuite("API", max_concurrency=4)
db_suite = ProTestSuite("Database", max_concurrency=1)
auth_suite = ProTestSuite("Auth", max_concurrency=2)

session.add_suite(api_suite)
session.add_suite(db_suite)
session.add_suite(auth_suite)


@db_suite.fixture()
def db_connection():
    time.sleep(0.8)
    yield {"connected": True}
    time.sleep(0.7)


@auth_suite.fixture()
def auth_service():
    time.sleep(0.6)
    yield {"authenticated": True}
    time.sleep(0.5)


@api_suite.test()
async def test_api_health():
    await asyncio.sleep(0.5)


@api_suite.test()
async def test_api_users():
    await asyncio.sleep(0.7)


@api_suite.test()
async def test_api_products():
    await asyncio.sleep(0.6)


@api_suite.test()
async def test_api_orders():
    await asyncio.sleep(0.8)


@api_suite.test()
async def test_api_payments():
    await asyncio.sleep(1.0)


@api_suite.test()
async def test_api_validation():
    await asyncio.sleep(0.4)
    raise AssertionError("Invalid response format")


@db_suite.test()
async def test_db_connection(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(0.3)
    assert db["connected"]


@db_suite.test()
async def test_db_query(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(0.5)


@db_suite.test()
async def test_db_insert(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(0.4)


@db_suite.test()
async def test_db_update(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(0.6)


@db_suite.test()
async def test_db_delete(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(0.35)


@db_suite.test(timeout=0.5)
async def test_db_slow_operation(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(1.2)


@auth_suite.test()
async def test_auth_login(auth: Annotated[dict, Use(auth_service)]):
    await asyncio.sleep(0.5)


@auth_suite.test()
async def test_auth_logout(auth: Annotated[dict, Use(auth_service)]):
    await asyncio.sleep(0.4)


@auth_suite.test()
async def test_auth_register(auth: Annotated[dict, Use(auth_service)]):
    await asyncio.sleep(0.7)


@auth_suite.test()
async def test_auth_password_reset(auth: Annotated[dict, Use(auth_service)]):
    await asyncio.sleep(0.6)


@auth_suite.test()
async def test_auth_token_refresh(auth: Annotated[dict, Use(auth_service)]):
    await asyncio.sleep(0.5)


@auth_suite.test(skip="Not implemented yet")
async def test_auth_2fa():
    await asyncio.sleep(0.5)


@auth_suite.test(xfail="Known issue #123")
async def test_auth_session_timeout():
    await asyncio.sleep(0.4)
    raise AssertionError("Session doesn't timeout correctly")


@session.test()
async def test_standalone_quick():
    await asyncio.sleep(0.3)


@session.test()
async def test_standalone_medium():
    await asyncio.sleep(0.5)


@session.test()
async def test_standalone_slow():
    await asyncio.sleep(0.8)
