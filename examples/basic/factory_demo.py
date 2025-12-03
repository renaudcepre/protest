"""Demo: Factory Errors vs Test Failures.

Run with: uv run protest run examples/basic/factory_demo:session

This demo shows how ProTest distinguishes:
- SETUP ERROR: Infrastructure problems (DB down, API unavailable)
- TEST FAIL: Your code has a bug
"""

from typing import Annotated

from protest import FixtureFactory, ProTestSession, Use

session = ProTestSession()


# =============================================================================
# FACTORY FIXTURES - Infrastructure that can fail
# =============================================================================


@session.factory()
def user(name: str, role: str = "guest") -> dict[str, str]:
    """Factory fixture with automatic teardown via yield."""
    print(f"  [setup] Creating user {name}...")
    if name == "crash":
        raise ConnectionError("Database connection lost!")
    yield {"name": name, "role": role}
    print(f"  [teardown] Deleting user {name}...")


@session.factory()
def api_response(endpoint: str) -> dict[str, str]:
    """Factory fixture that makes API requests."""
    if endpoint == "/unstable":
        raise TimeoutError("API request timed out after 30s")
    return {"status": "ok", "endpoint": endpoint}


# =============================================================================
# TESTS
# =============================================================================


@session.test()
def test_passing() -> None:
    """A simple passing test."""
    assert 1 + 1 == 2


@session.test()
async def test_user_creation(
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """This test passes - factory works fine."""
    alice = await user_factory(name="alice", role="admin")
    assert alice["name"] == "alice"
    assert alice["role"] == "admin"


@session.test()
async def test_factory_crashes(
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """This triggers a SETUP ERROR - the factory fails, not the test logic."""
    await user_factory(name="crash")  # DB "crashes" -> SETUP ERROR, not test fail


@session.test()
async def test_api_timeout(
    api_factory: Annotated[FixtureFactory[dict[str, str]], Use(api_response)],
) -> None:
    """This triggers a SETUP ERROR - API times out."""
    await api_factory(endpoint="/unstable")  # API "times out" -> SETUP ERROR


@session.test()
def test_assertion_failure() -> None:
    """This is a real TEST FAIL - bug in the test/code."""
    expected_value = 42
    actual_value = 41
    assert actual_value == expected_value, (
        f"Got {actual_value}, expected {expected_value}"
    )


@session.test()
def test_another_passing() -> None:
    """Another passing test to show mixed results."""
    data = {"key": "value"}
    assert "key" in data


# =============================================================================
# Expected output:
#
#   🚀 Starting session
#
#   ✓ test_passing
#   ✓ test_user_creation
#   ⚠ test_factory_crashes: [FIXTURE] Database connection lost!
#   ⚠ test_api_timeout: [FIXTURE] API request timed out after 30s
#   ✗ test_assertion_failure: Got 41, expected 42
#   ✓ test_another_passing
#
#   ✗ FAILURES │ 3/6 passed │ 1 failed │ 2 errors
#
# Notice:
# - ⚠ FIXTURE ERROR = Infrastructure problem (not your fault)
# - ✗ TEST FAIL = Bug in your code (your fault)
# =============================================================================
