"""Demo: Factory Errors vs Test Failures.

Run with: uv run protest run examples/basic/factory_demo:session

This demo shows how ProTest distinguishes:
- SETUP ERROR: Infrastructure problems (DB down, API unavailable)
- TEST FAIL: Your code has a bug
"""

from collections.abc import Callable
from typing import Annotated

from protest import ProTestSession, Use

session = ProTestSession()


# =============================================================================
# FACTORY FIXTURES - Infrastructure that can fail
# =============================================================================


@session.fixture(factory=True)
def user_factory() -> Callable[..., dict[str, str]]:
    """Returns a factory that creates users. Marked as factory=True."""
    print("  [setup] Connecting to user database...")

    def create_user(name: str, role: str = "guest") -> dict[str, str]:
        if name == "crash":
            raise ConnectionError("Database connection lost!")
        return {"name": name, "role": role}

    return create_user


def api_client_factory() -> Callable[..., dict[str, str]]:
    """Returns an API client factory. Plain function = function scope."""

    def make_request(endpoint: str) -> dict[str, str]:
        if endpoint == "/unstable":
            raise TimeoutError("API request timed out after 30s")
        return {"status": "ok", "endpoint": endpoint}

    return make_request


# =============================================================================
# TESTS
# =============================================================================


@session.test()
def test_passing() -> None:
    """A simple passing test."""
    assert 1 + 1 == 2


@session.test()
def test_user_creation(
    make_user: Annotated[Callable[..., dict[str, str]], Use(user_factory)],
) -> None:
    """This test passes - factory works fine."""
    user = make_user("alice", role="admin")
    assert user["name"] == "alice"
    assert user["role"] == "admin"


@session.test()
def test_factory_crashes(
    make_user: Annotated[Callable[..., dict[str, str]], Use(user_factory)],
) -> None:
    """This triggers a SETUP ERROR - the factory fails, not the test logic."""
    make_user("crash")  # DB "crashes" -> SETUP ERROR, not test fail


@session.test()
def test_api_timeout(
    client: Annotated[Callable[..., dict[str, str]], Use(api_client_factory)],
) -> None:
    """This triggers a SETUP ERROR - API times out."""
    client("/unstable")  # API "times out" -> SETUP ERROR


@session.test()
def test_assertion_failure() -> None:
    """This is a real TEST FAIL - bug in the test/code."""
    expected_value = 42
    actual_value = 41
    assert actual_value == expected_value, f"Got {actual_value}, expected {expected_value}"


@session.test()
def test_another_passing() -> None:
    """Another passing test to show mixed results."""
    data = {"key": "value"}
    assert "key" in data


# =============================================================================
# Expected output:
#
#  --- Starting session ---
#
#   [setup] Connecting to user database...
#   ✓ test_passing
#   ✓ test_user_creation
#   ⚠ test_factory_crashes: [SETUP ERROR] Database connection lost!
#   ⚠ test_api_timeout: [SETUP ERROR] API request timed out after 30s
#   ✗ test_assertion_failure: Got 41, expected 42
#   ✓ test_another_passing
#
# Results: 4/6 passed, 1 failed, 2 errors
#
# Notice:
# - ⚠ SETUP ERROR = Infrastructure problem (not your fault)
# - ✗ TEST FAIL = Bug in your code (your fault)
# =============================================================================
