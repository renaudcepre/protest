from typing import Annotated

import pytest

from src.entities import Scope
from src.use import Use


@pytest.mark.asyncio
async def test_automatic_cleanup(session):
    function_events = []
    session_events = []

    @session.fixture(scope=Scope.SESSION)
    def session_fixture():
        session_events.append("setup")
        yield "session_value"
        session_events.append("teardown")

    @session.fixture(scope=Scope.FUNCTION)
    def function_fixture(session_val: Annotated[str, Use(session_fixture)]):
        function_events.append("setup")
        yield f"function_with_{session_val}"
        function_events.append("teardown")

    # Define a test that manually uses the fixture
    async def test_example():
        # Manually resolve the fixtures
        fixture = await session._resolve_fixture(Use(function_fixture))
        assert fixture == "function_with_session_value"
        return "test_result"

    # Execute the test with automatic lifecycle management
    result = await session.run_test(test_example)

    # Verify that the test was executed correctly
    assert result == "test_result"

    # Verify that the function fixture was cleaned up automatically
    assert function_events == ["setup", "teardown"]
    assert "function_fixture" not in session._fixture_cache

    # The session fixture should still be in cache
    assert session_events == ["setup"]
    assert "session_fixture" in session._fixture_cache

    # Clean up the session to complete the test
    await session.cleanup_scope(Scope.SESSION)
    assert session_events == ["setup", "teardown"]
    assert "session_fixture" not in session._fixture_cache


@pytest.mark.asyncio
async def test_run_suite_and_session(session):
    """Tests the complete execution of a suite and session with automatic cleanup."""
    suite_events = {"function1": [], "function2": [], "session": []}

    @session.fixture(scope=Scope.SESSION)
    def session_fixture():
        suite_events["session"].append("setup")
        yield "session_value"
        suite_events["session"].append("teardown")

    @session.fixture(scope=Scope.FUNCTION)
    def function_fixture1(session_val: Annotated[str, Use(session_fixture)]):
        suite_events["function1"].append("setup")
        yield f"function1_{session_val}"
        suite_events["function1"].append("teardown")

    @session.fixture(scope=Scope.FUNCTION)
    def function_fixture2(session_val: Annotated[str, Use(session_fixture)]):
        suite_events["function2"].append("setup")
        yield f"function2_{session_val}"
        suite_events["function2"].append("teardown")

    # Define two tests that manually use fixtures
    async def test1():
        fixture = await session._resolve_fixture(Use(function_fixture1))
        assert fixture == "function1_session_value"
        return "test1_result"

    async def test2():
        fixture = await session._resolve_fixture(Use(function_fixture2))
        assert fixture == "function2_session_value"
        return "test2_result"

    # Execute the entire session
    results = await session.run_session([[test1, test2]])

    # Verify the results
    assert results == [["test1_result", "test2_result"]]

    # Verify that all fixtures have been properly cleaned up
    assert suite_events["function1"] == ["setup", "teardown"]
    assert suite_events["function2"] == ["setup", "teardown"]
    assert suite_events["session"] == ["setup", "teardown"]

    # Verify that the cache is empty
    assert len(session._fixture_cache) == 0
