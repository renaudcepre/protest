from typing import Annotated, Any

import pytest

from src.entities import Scope
from src.use import Use


def test_fixture_registration(session):
    """Test that fixtures are correctly registered."""

    @session.fixture(scope=Scope.SESSION)
    def fixture_parent():
        return "parent_value"

    @session.fixture(scope=Scope.FUNCTION)
    def fixture_child(parent: Annotated[Any, Use(fixture_parent)]):
        return f"child_with_{parent}"

    # Check fixtures are registered
    assert "fixture_parent" in session.fixtures
    assert "fixture_child" in session.fixtures

    # Check scopes are correct
    assert session.fixtures["fixture_parent"].scope == Scope.SESSION
    assert session.fixtures["fixture_child"].scope == Scope.FUNCTION

    # Check dependencies
    assert len(session.fixtures["fixture_parent"].dependencies) == 0
    assert len(session.fixtures["fixture_child"].dependencies) == 1
    assert "parent" in session.fixtures["fixture_child"].dependencies
    assert session.fixtures["fixture_child"].dependencies["parent"].name == "fixture_parent"


@pytest.mark.asyncio
async def test_fixture_resolution(session):
    """Test that fixtures are correctly resolved."""

    @session.fixture(scope=Scope.SESSION)
    def fixture_parent():
        return "parent_value"

    @session.fixture(scope=Scope.FUNCTION)
    def fixture_child(parent: Annotated[Any, Use(fixture_parent)]):
        return f"child_with_{parent}"

    # Resolve child fixture
    child_use = Use(fixture_child)
    child_value = await session._resolve_fixture(child_use)
    assert child_value == "child_with_parent_value"

    # Check cache
    assert "fixture_parent" in session._fixture_cache
    assert "fixture_child" in session._fixture_cache
    assert session._fixture_cache["fixture_parent"].value == "parent_value"
    assert session._fixture_cache["fixture_child"].value == "child_with_parent_value"


@pytest.mark.asyncio
async def test_generator_fixtures(session):
    """Test generator fixtures with setup/teardown."""
    setup_events = []

    @session.fixture(scope=Scope.SESSION)
    def generator_fixture():
        setup_events.append("TEST")
        yield "generator_value"
        setup_events.remove("TEST")

    # Resolve the generator fixture
    gen_use = Use(generator_fixture)
    gen_value = await session._resolve_fixture(gen_use)

    assert gen_value == "generator_value"
    assert setup_events == ["TEST"]

    # Clean up the generator fixture
    await session._cleanup_fixture("generator_fixture")
    assert setup_events == []
    assert "generator_fixture" not in session._fixture_cache


@pytest.mark.asyncio
async def test_async_fixtures(session):
    """Test async fixtures."""

    @session.fixture(scope=Scope.SESSION)
    async def async_fixture():
        return "async_value"

    @session.fixture(scope=Scope.FUNCTION)
    async def async_generator_fixture():
        yield "async_gen_value"

    async_gen_value = await session._resolve_fixture(Use(async_generator_fixture))
    assert async_gen_value == "async_gen_value"


@pytest.mark.asyncio
async def test_fixture_dependency_chain(session):
    @session.fixture(scope=Scope.SESSION)
    def fixture_a():
        return "a_value"

    @session.fixture(scope=Scope.SESSION)
    def fixture_b(a: Annotated[str, Use(fixture_a)]):
        return f"b_with_{a}"

    @session.fixture(scope=Scope.FUNCTION)
    def fixture_c(b: Annotated[str, Use(fixture_b)]):
        return f"c_with_{b}"

    # Resolve fixture c, which depends on b, which depends on a
    c_use = Use(fixture_c)
    c_value = await session._resolve_fixture(c_use)

    assert c_value == "c_with_b_with_a_value"
    assert "fixture_a" in session._fixture_cache
    assert "fixture_b" in session._fixture_cache
    assert "fixture_c" in session._fixture_cache


@pytest.mark.asyncio
async def test_automatic_lifecycle(session):
    session_fixtures = []
    function_fixtures = []

    @session.fixture(scope=Scope.SESSION)
    def session_fixture():
        session_fixtures.append("setup")
        yield "session_value"
        session_fixtures.append("teardown")

    @session.fixture(scope=Scope.FUNCTION)
    def function_fixture(session_val: Annotated[str, Use(session_fixture)]):
        function_fixtures.append("setup")
        yield f"function_with_{session_val}"
        function_fixtures.append("teardown")

    func_use = Use(function_fixture)
    func_value = await session._resolve_fixture(func_use)

    assert func_value == "function_with_session_value"
    assert session_fixtures == ["setup"]
    assert function_fixtures == ["setup"]
    assert "session_fixture" in session._fixture_cache
    assert "function_fixture" in session._fixture_cache

    await session._cleanup_fixture("function_fixture")
    assert function_fixtures == ["setup", "teardown"]
    assert "function_fixture" not in session._fixture_cache
    assert "session_fixture" in session._fixture_cache

    await session._cleanup_fixture("session_fixture")
    assert session_fixtures == ["setup", "teardown"]
    assert "session_fixture" not in session._fixture_cache
