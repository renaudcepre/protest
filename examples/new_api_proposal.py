# ============================================================
# ProTest - Proposed New API with Tree-based Scoping
# ============================================================
#
# Scope is determined by WHERE you decorate:
#   @session.fixture()  -> Lives for entire session
#   @suite.fixture()    -> Lives while suite runs
#   @fixture()          -> Fresh instance per test (function scope)
#
# ============================================================

from collections.abc import Callable
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use
from protest.di.decorators import fixture

# ============================================================
# Example 1: Simple project (flat)
# ============================================================

session = ProTestSession()


@session.fixture()
def database():
    """Session-scoped: shared across ALL tests."""
    db = connect()
    yield db
    db.close()


@fixture()
def fresh_user():
    """Function-scoped: fresh instance per test."""
    return User(name="alice")


@session.test()
def test_create(
    db: Annotated[DB, Use(database)],  # Shared (session)
    user: Annotated[User, Use(fresh_user)],  # Fresh per test
):
    db.save(user)
    assert db.get(user.id) == user


# ============================================================
# Example 2: Nested suites
# ============================================================

session = ProTestSession()


@session.fixture()
def database():
    yield connect()


# --- API Suite ---
api_suite = ProTestSuite("api")
session.add_suite(api_suite)


@api_suite.fixture()
def api_client(db: Annotated[DB, Use(database)]):
    """Suite-scoped: lives while api_suite runs."""
    return APIClient(db)


# --- Users Suite (child of API) ---
users_suite = ProTestSuite("users")
api_suite.add_suite(users_suite)


@users_suite.fixture()
def admin_user():
    """Suite-scoped: lives while users_suite runs."""
    return User(role="admin")


@fixture()
def user_payload():
    """Function-scoped: fresh per test."""
    return {"name": "alice", "email": "alice@test.com"}


@users_suite.test()
def test_create_user(
    client: Annotated[APIClient, Use(api_client)],  # From grandparent
    admin: Annotated[User, Use(admin_user)],  # From parent
    payload: Annotated[dict, Use(user_payload)],  # Fresh per test
):
    response = client.post("/users", payload)
    assert response.status == 201


@users_suite.test()
def test_get_user(
    client: Annotated[APIClient, Use(api_client)],  # Same instance as above
    admin: Annotated[User, Use(admin_user)],  # Same instance as above
):
    response = client.get(f"/users/{admin.id}")
    assert response.status == 200


# ============================================================
# Example 3: Realistic multi-file structure
# ============================================================

# --- conftest.py ---

session = ProTestSession()


@session.fixture()
def database():
    yield connect()


@session.fixture()
def redis_cache():
    cache = Redis()
    yield cache
    cache.flushall()


# Suite architecture
unit_suite = ProTestSuite("unit", max_concurrency=8)
integration_suite = ProTestSuite("integration", max_concurrency=2)
e2e_suite = ProTestSuite("e2e", max_concurrency=1)

session.add_suite(unit_suite)
session.add_suite(integration_suite)
session.add_suite(e2e_suite)

# Sub-suites for unit tests
users_unit = ProTestSuite("users")
orders_unit = ProTestSuite("orders")
payments_unit = ProTestSuite("payments")

unit_suite.add_suite(users_unit)
unit_suite.add_suite(orders_unit)
unit_suite.add_suite(payments_unit)


# --- tests/unit/users/test_create.py ---


@fixture()
def user_factory():
    """Fresh factory per test."""

    def create(name: str, **kwargs) -> User:
        return User(name=name, **kwargs)

    return create


@fixture()
def mock_email_service():
    """Fresh mock per test."""
    return Mock(spec=EmailService)


@users_unit.test()
def test_create_user_sends_email(
    factory: Annotated[Callable, Use(user_factory)],
    email: Annotated[Mock, Use(mock_email_service)],
):
    user = factory(name="bob")
    send_welcome_email(user, email)
    email.send.assert_called_with(user.email)


@users_unit.test()
def test_create_user_validates_email(factory: Annotated[Callable, Use(user_factory)]):
    with pytest.raises(ValidationError):
        factory(name="bob", email="invalid")


# --- tests/integration/test_api.py ---


@integration_suite.fixture()
def seeded_db(db: Annotated[DB, Use(database)]):
    """Suite-scoped: seeded once for all integration tests."""
    db.seed(users=10, orders=50)
    yield db
    db.truncate()


@integration_suite.test()
def test_user_orders(db: Annotated[DB, Use(seeded_db)]):
    user = db.get_user(1)
    assert len(user.orders) > 0


@integration_suite.test()
def test_order_total(db: Annotated[DB, Use(seeded_db)]):
    order = db.get_order(1)
    assert order.total > 0


# --- tests/e2e/test_checkout.py ---


@e2e_suite.fixture()
def browser():
    """Suite-scoped: one browser for all e2e tests."""
    driver = Chrome()
    yield driver
    driver.quit()


@fixture()
def checkout_page(b: Annotated[Chrome, Use(browser)]):
    """Fresh page state per test."""
    b.get("/checkout")
    return CheckoutPage(b)


@e2e_suite.test()
def test_checkout_flow(page: Annotated[CheckoutPage, Use(checkout_page)]):
    page.add_item("widget")
    page.fill_payment(card="4242...")
    page.submit()
    assert page.confirmation_visible()


# ============================================================
# Example 4: Fixture inheritance through tree
# ============================================================

session = ProTestSession()


@session.fixture()
def config():
    return {"env": "test", "debug": True}


api_suite = ProTestSuite("api")
session.add_suite(api_suite)


@api_suite.fixture()
def api_config(cfg: Annotated[dict, Use(config)]):
    """Extends parent config with API-specific settings."""
    return {**cfg, "base_url": "http://localhost:8000"}


v1_suite = ProTestSuite("v1")
v2_suite = ProTestSuite("v2")
api_suite.add_suite(v1_suite)
api_suite.add_suite(v2_suite)


@v1_suite.fixture()
def v1_client(cfg: Annotated[dict, Use(api_config)]):
    return Client(f"{cfg['base_url']}/v1")


@v2_suite.fixture()
def v2_client(cfg: Annotated[dict, Use(api_config)]):
    return Client(f"{cfg['base_url']}/v2")


@v1_suite.test()
def test_v1_users(client: Annotated[Client, Use(v1_client)]):
    assert client.get("/users").status == 200


@v2_suite.test()
def test_v2_users(client: Annotated[Client, Use(v2_client)]):
    # v2 has pagination
    resp = client.get("/users")
    assert "next_cursor" in resp.json()


# ============================================================
# Example 5: Async support (unchanged)
# ============================================================

session = ProTestSession()


@session.fixture()
async def async_database():
    db = await AsyncDB.connect()
    yield db
    await db.close()


@fixture()
async def async_user():
    """Fresh per test, async."""
    return await User.create(name="alice")


@session.test()
async def test_async_create(
    db: Annotated[AsyncDB, Use(async_database)], user: Annotated[User, Use(async_user)]
):
    await db.save(user)
    found = await db.get(user.id)
    assert found.name == "alice"


# ============================================================
# Summary: API
# ============================================================
#
# Tree-based scoping:
#   @session.fixture()   -> Session scope
#   @suite.fixture()     -> Suite scope (lives while suite runs)
#   @fixture()           -> Function scope (fresh per test)
#
# BENEFITS:
#   - No Scope enum to remember
#   - Scope is visual: WHERE you decorate = HOW LONG it lives
#   - Nested suites naturally supported
#   - Fixture inheritance through tree
#   - Cleaner teardown (follows tree structure)
#   - Explicit: all fixtures must be decorated
#
# ============================================================
