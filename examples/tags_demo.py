"""Demo of the tag system in ProTest."""

from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use


session = ProTestSession(default_reporter=True, default_cache=False)


@session.fixture(tags=["database"])
def db_connection():
    """Session-scoped database fixture tagged with 'database'."""
    return {"connected": True, "type": "postgres"}


@session.fixture(tags=["cache"])
def cache_client():
    """Session-scoped cache fixture tagged with 'cache'."""
    return {"type": "redis", "host": "localhost"}


@session.fixture()
def user_repository(db: Annotated[dict, Use(db_connection)]):
    """Repository that depends on db - inherits 'database' tag transitively."""
    return {"db": db, "table": "users"}


api_suite = ProTestSuite("API", tags=["api", "integration"])


@api_suite.fixture()
def api_client(
    db: Annotated[dict, Use(db_connection)],
    cache: Annotated[dict, Use(cache_client)],
):
    """API client that uses both db and cache - inherits both tags."""
    return {"db": db, "cache": cache, "base_url": "/api/v1"}


@api_suite.test(tags=["slow"])
async def test_api_slow_endpoint(client: Annotated[dict, Use(api_client)]):
    """Slow API test - has tags: slow, api, integration, database, cache."""
    assert client["base_url"] == "/api/v1"


@api_suite.test()
async def test_api_fast_endpoint(client: Annotated[dict, Use(api_client)]):
    """Fast API test - has tags: api, integration, database, cache."""
    assert "db" in client


unit_suite = ProTestSuite("Unit", tags=["unit"])


@unit_suite.test()
async def test_pure_logic():
    """Pure unit test - only has 'unit' tag."""
    assert 1 + 1 == 2


@unit_suite.test(tags=["math"])
async def test_math_operations():
    """Math unit test - has tags: unit, math."""
    assert 2 * 3 == 6


db_suite = ProTestSuite("Database", tags=["database"])


@db_suite.test()
async def test_db_query(repo: Annotated[dict, Use(user_repository)]):
    """DB test - has tags: database (from suite AND fixture)."""
    assert repo["table"] == "users"


session.add_suite(api_suite)
session.add_suite(unit_suite)
session.add_suite(db_suite)


if __name__ == "__main__":
    print("Run with: protest run tags_demo:session --app-dir examples")
    print("Or: protest tags list tags_demo:session --app-dir examples")
    print("Or: protest tags list -r tags_demo:session --app-dir examples")
    print("Or: protest run tags_demo:session --app-dir examples --tag database")
    print("Or: protest run tags_demo:session --app-dir examples --tag unit --exclude-tag math")
