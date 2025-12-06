"""Filtering demo - demonstrates suite, keyword, and tag filtering.

Run with different filters to see how they work:

    # Run all tests
    protest run filtering_demo:session

    # Suite filter - run only API tests
    protest run filtering_demo:session::API

    # Suite filter - run only nested Users tests
    protest run filtering_demo:session::API::Users

    # Keyword filter - tests containing "create"
    protest run filtering_demo:session -k create

    # Keyword filter - multiple patterns (OR logic)
    protest run filtering_demo:session -k create -k delete

    # Tag filter - only slow tests
    protest run filtering_demo:session -t slow

    # Tag filter - exclude slow tests
    protest run filtering_demo:session --no-tag slow

    # Combine filters (intersection)
    protest run filtering_demo:session::API -k user -t slow

    # With --collect-only to see what matches
    protest run filtering_demo:session::API -k user --collect-only
"""

from protest import ProTestSession, ProTestSuite

session = ProTestSession()

api_suite = ProTestSuite("API", tags=["api"])
users_suite = ProTestSuite("Users")
orders_suite = ProTestSuite("Orders")

api_suite.add_suite(users_suite)
api_suite.add_suite(orders_suite)
session.add_suite(api_suite)

db_suite = ProTestSuite("Database", tags=["database"])
session.add_suite(db_suite)


@session.test()
def test_standalone() -> None:
    """A test not in any suite."""
    pass


@api_suite.test()
def test_api_health() -> None:
    """API health check."""
    pass


@users_suite.test(tags=["slow"])
def test_list_users() -> None:
    """List all users (slow)."""
    pass


@users_suite.test()
def test_create_user() -> None:
    """Create a user."""
    pass


@users_suite.test()
def test_delete_user() -> None:
    """Delete a user."""
    pass


@orders_suite.test(tags=["slow"])
def test_list_orders() -> None:
    """List all orders (slow)."""
    pass


@orders_suite.test()
def test_create_order() -> None:
    """Create an order."""
    pass


@db_suite.test(tags=["slow"])
def test_db_migration() -> None:
    """Run database migration (slow)."""
    pass


@db_suite.test()
def test_db_connection() -> None:
    """Test database connection."""
    pass


if __name__ == "__main__":
    from protest import run_session

    run_session(session)
