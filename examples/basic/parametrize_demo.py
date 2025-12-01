"""Demo of parameterized tests with ForEach and From."""

from dataclasses import dataclass
from typing import Annotated

from protest import ForEach, From, ProTestSession, ProTestSuite, Use

session = ProTestSession()


@dataclass
class UserScenario:
    username: str
    is_admin: bool
    expected_status: int

    def __repr__(self) -> str:
        return self.username


SCENARIOS = ForEach(
    [
        UserScenario("alice", True, 200),
        UserScenario("bob", False, 403),
        UserScenario("guest", False, 401),
    ],
    ids=lambda s: s.username,
)

HTTP_CODES = ForEach([200, 201, 204])


@session.test()
def test_success_codes(code: Annotated[int, From(HTTP_CODES)]) -> None:
    """Simple parameterized test with primitives."""
    assert code in range(200, 300)


@session.test()
def test_user_permissions(scenario: Annotated[UserScenario, From(SCENARIOS)]) -> None:
    """Parameterized test with dataclass."""
    if scenario.is_admin:
        assert scenario.expected_status == 200
    else:
        assert scenario.expected_status in [401, 403]


api_suite = ProTestSuite("API")
session.include_suite(api_suite)

USERS = ForEach(["alice", "bob"], ids=lambda u: u)
METHODS = ForEach(["GET", "POST"], ids=lambda m: m)


@api_suite.test()
def test_api_matrix(
    user: Annotated[str, From(USERS)],
    method: Annotated[str, From(METHODS)],
) -> None:
    """Cartesian product: 2 users × 2 methods = 4 tests."""
    print(f"Testing {method} for {user}")
    assert user in ["alice", "bob"]
    assert method in ["GET", "POST"]


@session.fixture()
def base_url() -> str:
    return "https://api.example.com"


@api_suite.test()
def test_with_fixture(
    user: Annotated[str, From(USERS)],
    url: Annotated[str, Use(base_url)],
) -> None:
    """ForEach works with fixtures."""
    assert url.startswith("https://")
    assert user in ["alice", "bob"]


if __name__ == "__main__":
    from protest.core.runner import TestRunner

    runner = TestRunner(session)
    success = runner.run()
    exit(0 if success else 1)
