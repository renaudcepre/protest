"""Demo: Nested Suites with Fixture Inheritance.

Run with: uv run protest nested_suites:session

This demo shows how nested suites work:
- Parent suites can contain child suites
- Child suites inherit fixtures from parents
- Each suite level can have its own fixtures
- Teardown follows tree structure (children first, then parents)
"""

from collections.abc import Generator
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use

session = ProTestSession()


# =============================================================================
# SESSION FIXTURES (shared across everything)
# =============================================================================


@session.fixture()
def database() -> Generator[str, None, None]:
    print("  [SESSION] Connecting to database...")
    yield "PostgresConnection"
    print("  [SESSION] Database disconnected")


# =============================================================================
# API SUITE (top-level)
# =============================================================================

api_suite = ProTestSuite("API")
session.add_suite(api_suite)


@api_suite.fixture()
def api_client(db: Annotated[str, Use(database)]) -> Generator[str, None, None]:
    print(f"  [API SUITE] Creating API client with {db}")
    yield f"APIClient({db})"
    print("  [API SUITE] API client closed")


@api_suite.test()
def test_api_health(client: Annotated[str, Use(api_client)]) -> None:
    assert "APIClient" in client


# =============================================================================
# USERS SUITE (child of API)
# =============================================================================

users_suite = ProTestSuite("Users")
api_suite.add_suite(users_suite)  # Nested under API


@users_suite.fixture()
def admin_user(client: Annotated[str, Use(api_client)]) -> Generator[str, None, None]:
    print(f"  [USERS SUITE] Creating admin user via {client}")
    yield "admin@test.com"
    print("  [USERS SUITE] Admin user cleaned up")


@users_suite.test()
def test_list_users(client: Annotated[str, Use(api_client)]) -> None:
    assert "APIClient" in client


@users_suite.test()
def test_create_user(
    client: Annotated[str, Use(api_client)],
    admin: Annotated[str, Use(admin_user)],
) -> None:
    assert "APIClient" in client
    assert admin == "admin@test.com"


# =============================================================================
# PERMISSIONS SUITE (child of Users, grandchild of API)
# =============================================================================

permissions_suite = ProTestSuite("Permissions")
users_suite.add_suite(permissions_suite)  # Nested under Users


@permissions_suite.fixture()
def permission_set(admin: Annotated[str, Use(admin_user)]) -> str:
    print(f"  [PERMISSIONS SUITE] Loading permissions for {admin}")
    return f"Permissions({admin})"


@permissions_suite.test()
def test_admin_has_all_permissions(
    perms: Annotated[str, Use(permission_set)],
) -> None:
    assert "admin@test.com" in perms


@permissions_suite.test()
def test_permission_inheritance(
    db: Annotated[str, Use(database)],  # From session (grandparent)
    client: Annotated[str, Use(api_client)],  # From API suite (great-grandparent)
    admin: Annotated[str, Use(admin_user)],  # From Users suite (parent)
    perms: Annotated[str, Use(permission_set)],  # From this suite
) -> None:
    assert db == "PostgresConnection"
    assert "APIClient" in client
    assert admin == "admin@test.com"
    assert "Permissions" in perms


# =============================================================================
# ORDERS SUITE (sibling of Users, also child of API)
# =============================================================================

orders_suite = ProTestSuite("Orders")
api_suite.add_suite(orders_suite)


@orders_suite.fixture()
def order_service(client: Annotated[str, Use(api_client)]) -> str:
    print(f"  [ORDERS SUITE] Creating order service via {client}")
    return f"OrderService({client})"


@orders_suite.test()
def test_create_order(svc: Annotated[str, Use(order_service)]) -> None:
    assert "OrderService" in svc


@orders_suite.test()
def test_list_orders(
    client: Annotated[str, Use(api_client)],
    svc: Annotated[str, Use(order_service)],
) -> None:
    assert "APIClient" in client
    assert "OrderService" in svc


# =============================================================================
# STANDALONE SESSION TESTS
# =============================================================================


@session.test()
def test_database_connection(db: Annotated[str, Use(database)]) -> None:
    assert db == "PostgresConnection"


# =============================================================================
# Expected tree structure:
#
#   session
#   ├── database (fixture)
#   ├── test_database_connection (test)
#   └── API (suite)
#       ├── api_client (fixture, depends on database)
#       ├── test_api_health (test)
#       ├── Users (suite)
#       │   ├── admin_user (fixture, depends on api_client)
#       │   ├── test_list_users (test)
#       │   ├── test_create_user (test)
#       │   └── Permissions (suite)
#       │       ├── permission_set (fixture, depends on admin_user)
#       │       ├── test_admin_has_all_permissions (test)
#       │       └── test_permission_inheritance (test)
#       └── Orders (suite)
#           ├── order_service (fixture, depends on api_client)
#           ├── test_create_order (test)
#           └── test_list_orders (test)
#
# Execution order (roughly):
#   1. SESSION fixtures (database)
#   2. API suite fixtures (api_client)
#   3. Run API::test_api_health
#   4. Users suite fixtures (admin_user)
#   5. Run API::Users::test_list_users, test_create_user
#   6. Permissions suite fixtures (permission_set)
#   7. Run API::Users::Permissions::test_*
#   8. Teardown: Permissions -> Users -> API -> SESSION
#   9. Orders suite fixtures (order_service)
#   10. Run API::Orders::test_*
#   11. Teardown: Orders -> API (already done) -> SESSION (at end)
#
# =============================================================================
