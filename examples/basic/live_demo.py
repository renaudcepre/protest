import asyncio
import logging
import time
from typing import Annotated

from protest import ForEach, From, ProTestSession, ProTestSuite, Use

log = logging.getLogger(__name__)

session = ProTestSession(concurrency=10)


@session.fixture()
def global_config():
    """Session-level fixture with slow setup/teardown."""
    log.info("Setting up global config...")
    time.sleep(1.2)
    log.info("Global config ready")
    yield {"env": "test", "debug": True}
    log.info("Tearing down global config...")
    time.sleep(1.2)
    log.info("Global config cleaned up")


api_suite = ProTestSuite("API")
api_users_suite = ProTestSuite("Users")
api_suite.add_suite(api_users_suite)

db_suite = ProTestSuite("Database")
auth_suite = ProTestSuite("Auth")

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
    log.info("Checking API health endpoint...")
    await asyncio.sleep(0.3)
    print("Health check response: {'status': 'ok'}")
    log.info("API is healthy")
    await asyncio.sleep(0.2)


@api_suite.test()
async def test_api_users():
    log.info("Fetching users list...")
    await asyncio.sleep(0.3)
    log.info("Processing 150 users")
    await asyncio.sleep(0.4)


@api_suite.test()
async def test_api_products():
    log.info("Loading product catalog...")
    await asyncio.sleep(0.3)
    log.info("Found 42 products")
    await asyncio.sleep(0.3)


@api_suite.test()
async def test_api_orders():
    log.info("Querying orders...")
    await asyncio.sleep(0.2)
    log.info("Validating order #12345")
    await asyncio.sleep(0.3)
    log.info("Order validated successfully")
    await asyncio.sleep(0.3)


@api_suite.test()
async def test_api_payments():
    log.info("Initializing payment gateway...")
    await asyncio.sleep(0.3)
    log.info("Processing payment...")
    await asyncio.sleep(0.4)
    log.info("Payment confirmed")
    await asyncio.sleep(0.3)


@api_suite.test()
async def test_api_validation():
    await asyncio.sleep(0.4)
    raise AssertionError("Invalid response format")


@db_suite.test()
async def test_db_connection(db: Annotated[dict, Use(db_connection)]):
    log.info("Testing connection pool...")
    await asyncio.sleep(0.3)
    assert db["connected"]


@db_suite.test()
async def test_db_query(db: Annotated[dict, Use(db_connection)]):
    log.info("Executing SELECT * FROM users")
    await asyncio.sleep(0.3)
    print("Query result: [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]")
    log.info("Query returned 250 rows")
    await asyncio.sleep(0.2)


@db_suite.test()
async def test_db_insert(db: Annotated[dict, Use(db_connection)]):
    log.info("INSERT INTO users VALUES (...)")
    await asyncio.sleep(0.4)


@db_suite.test()
async def test_db_update(db: Annotated[dict, Use(db_connection)]):
    log.info("UPDATE users SET status='active'")
    await asyncio.sleep(0.3)
    log.info("Updated 15 rows")
    await asyncio.sleep(0.3)


@db_suite.test()
async def test_db_delete(db: Annotated[dict, Use(db_connection)]):
    log.info("DELETE FROM sessions WHERE expired=true")
    await asyncio.sleep(0.35)


@db_suite.test(timeout=0.5)
async def test_db_slow_operation(db: Annotated[dict, Use(db_connection)]):
    await asyncio.sleep(1.2)


@auth_suite.test()
async def test_auth_login(auth: Annotated[dict, Use(auth_service)]):
    log.info("Validating credentials...")
    await asyncio.sleep(0.2)
    print("Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    log.info("Generating JWT token")
    await asyncio.sleep(0.3)


@auth_suite.test()
async def test_auth_logout(auth: Annotated[dict, Use(auth_service)]):
    log.info("Invalidating session...")
    await asyncio.sleep(0.4)


@auth_suite.test()
async def test_auth_register(auth: Annotated[dict, Use(auth_service)]):
    log.info("Checking email uniqueness...")
    await asyncio.sleep(0.2)
    log.info("Hashing password (bcrypt)")
    await asyncio.sleep(0.3)
    log.info("Sending verification email")
    await asyncio.sleep(0.2)


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


@api_users_suite.test()
async def test_list_users():
    log.info("Fetching all users...")
    await asyncio.sleep(0.3)
    print("Found 42 users")
    log.info("Users loaded")


@api_users_suite.test()
async def test_get_user():
    log.info("Fetching user by ID...")
    await asyncio.sleep(0.2)
    log.info("User found: alice@example.com")


@api_users_suite.test()
async def test_create_user():
    log.info("Creating new user...")
    await asyncio.sleep(0.4)
    print("User created: {'id': 123, 'name': 'Bob'}")


@session.test()
async def test_standalone_quick(cfg: Annotated[dict, Use(global_config)]):
    assert cfg["env"] == "test"
    await asyncio.sleep(0.3)


@session.test()
async def test_standalone_medium(cfg: Annotated[dict, Use(global_config)]):
    await asyncio.sleep(0.5)


@session.test()
async def test_standalone_slow(cfg: Annotated[dict, Use(global_config)]):
    await asyncio.sleep(0.8)


STATUS_CODES = ForEach(
    [(200, "ok"), (201, "created"), (204, "no_content"), (404, "not_found")],
    ids=lambda x: str(x[0]),
)


@api_suite.test()
async def test_api_status_codes(
    case: Annotated[tuple[int, str], From(STATUS_CODES)],
):
    status_code, expected = case
    log.info(f"Testing status {status_code}...")
    await asyncio.sleep(0.2)
    assert expected in ["ok", "created", "no_content", "not_found"]


TABLES = ForEach(["users", "orders", "products"])


@db_suite.test()
async def test_db_table_exists(
    db: Annotated[dict, Use(db_connection)],
    table: Annotated[str, From(TABLES)],
):
    log.info(f"Checking table {table}...")
    await asyncio.sleep(0.25)
    assert db["connected"]
