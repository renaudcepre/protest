"""Demo: Factory fixtures with database dependency.

Run with: uv run protest run examples.basic.factory_with_db_demo:session

This shows how factory fixtures can depend on other fixtures (like a DB connection).
"""

from typing import Annotated

from protest import FixtureFactory, ProTestSession, Use

session = ProTestSession()


# =============================================================================
# FAKE DATABASE (simulates a real DB)
# =============================================================================


class FakeDB:
    """Simulates a database connection with users table."""

    def __init__(self) -> None:
        self.users: dict[int, dict[str, str]] = {}
        self._next_id = 1

    def insert_user(self, name: str, role: str) -> dict[str, str]:
        user = {"id": self._next_id, "name": name, "role": role}
        self.users[self._next_id] = user
        self._next_id += 1
        print(f"    [DB] INSERT INTO users: {user}")
        return user

    def delete_user(self, user_id: int) -> None:
        if user_id in self.users:
            print(f"    [DB] DELETE FROM users WHERE id={user_id}")
            del self.users[user_id]

    def close(self) -> None:
        print("    [DB] Connection closed")


# =============================================================================
# FIXTURES
# =============================================================================


@session.fixture()
def db() -> FakeDB:
    """Session-scoped database connection."""
    print("  [fixture] Opening DB connection...")
    database = FakeDB()
    yield database
    database.close()


@session.factory()
def user(
    db: Annotated[FakeDB, Use(db)],
    name: str,
    role: str = "guest",
) -> dict[str, str]:
    user = db.insert_user(name, role)
    yield user
    db.delete_user(user["id"])


# =============================================================================
# TESTS
# =============================================================================


@session.test()
async def test_create_single_user(
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """Create one user and verify it exists."""
    alice = await user_factory(name="alice", role="admin")

    assert alice["name"] == "alice"
    assert alice["role"] == "admin"
    assert "id" in alice


@session.test()
async def test_create_multiple_users(
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """Create multiple users - each gets a unique ID."""
    alice = await user_factory(name="alice")
    bob = await user_factory(name="bob", role="admin")

    assert alice["id"] != bob["id"]
    assert alice["role"] == "guest"
    assert bob["role"] == "admin"


@session.test()
async def test_factory_caches_by_kwargs(
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """Same kwargs = same instance (cached). Different kwargs = new instance."""
    alice1 = await user_factory(name="alice")
    alice2 = await user_factory(name="alice")
    bob = await user_factory(name="bob")

    assert alice1 is alice2
    assert alice1 is not bob


@session.test()
async def test_users_share_same_db(
    db: Annotated[FakeDB, Use(db)],
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """The factory uses the same DB instance as the test."""
    await user_factory(name="charlie")

    assert "charlie" in [user["name"] for user in db.users.values()]


# =============================================================================
# Expected output:
#
#   🚀 Starting session
#
#   [fixture] Opening DB connection...
#   ✓ test_create_single_user
#       [DB] INSERT INTO users: {id: 1, name: alice, role: admin}
#   ✓ test_create_multiple_users
#       [DB] INSERT INTO users: {id: 2, name: alice, role: guest}
#       [DB] INSERT INTO users: {id: 3, name: bob, role: admin}
#   ✓ test_factory_caches_by_kwargs
#       [DB] INSERT INTO users: {id: 4, name: alice, role: guest}  <- only once!
#       [DB] INSERT INTO users: {id: 5, name: bob, role: guest}
#   ✓ test_users_share_same_db
#       [DB] INSERT INTO users: {id: 6, name: charlie, role: guest}
#
#   [teardown] DELETE all created users (LIFO order)
#   [DB] Connection closed
#
#   ✓ SUCCESS │ 4/4 passed
# =============================================================================
