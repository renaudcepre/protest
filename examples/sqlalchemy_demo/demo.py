"""Demo: Factory fixtures with SQLAlchemy.

Run with:
    cd examples/sqlalchemy_demo
    uv sync
    uv run protest run demo:session

This shows a realistic setup:
- Engine: session-scoped (one connection pool for all tests)
- DB Session: function-scoped (fresh transaction per test, rolled back)
- User factory: creates users in the current transaction
"""

from typing import Annotated

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from protest import FixtureFactory, ProTestSession, ProTestSuite, Use, factory, fixture

session = ProTestSession()


# =============================================================================
# MODELS
# =============================================================================


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(50), default="guest")


# =============================================================================
# FIXTURES
# =============================================================================


@session.fixture()
def engine():
    """Session-scoped: SQLite in-memory with shared cache for all connections."""
    print("\n  [engine] Creating in-memory SQLite engine...")
    eng = create_engine(
        "sqlite:///file::memory:?cache=shared&uri=true",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    print("  [engine] Disposing engine...")
    eng.dispose()


db_suite = ProTestSuite("Database")
session.add_suite(db_suite)


@fixture()
def db_session(engine: Annotated[object, Use(engine)]):
    """Function-scoped: fresh session per test, rollback after."""
    print("    [db_session] Opening new session + transaction...")
    with Session(engine) as db:
        yield db
        print("    [db_session] Rolling back transaction...")
        db.rollback()


@factory()
def user(
    db_session: Annotated[Session, Use(db_session)],
    name: str,
    email: str | None = None,
    role: str = "guest",
) -> User:
    email = email or f"{name.lower()}@example.com"
    new_user = User(name=name, email=email, role=role)
    db_session.add(new_user)
    db_session.flush()
    return new_user


# =============================================================================
# TESTS
# =============================================================================


@db_suite.test()
async def test_create_single_user(
    db_session: Annotated[Session, Use(db_session)],
    user_factory: Annotated[FixtureFactory[User], Use(user)],
) -> None:
    """Create one user and verify it's in the DB."""
    alice = await user_factory(name="Alice", role="admin")

    result = db_session.execute(select(User).where(User.id == alice.id))
    fetched = result.scalar_one()

    assert fetched.name == "Alice"
    assert fetched.role == "admin"
    assert fetched.email == "alice@example.com"


@db_suite.test()
async def test_create_multiple_users(
    db_session: Annotated[Session, Use(db_session)],
    user_factory: Annotated[FixtureFactory[User], Use(user)],
) -> None:
    """Create multiple users in the same transaction."""
    alice = await user_factory(name="Alice")
    bob = await user_factory(name="Bob", email="bob@company.com", role="admin")

    count = db_session.query(User).count()
    expected_count = 2
    assert count == expected_count
    assert alice.id != bob.id


@db_suite.test()
async def test_isolation_between_tests(
    db_session: Annotated[Session, Use(db_session)],
) -> None:
    """Each test starts with an empty DB (previous test rolled back)."""
    count = db_session.query(User).count()
    expected_count = 0
    assert count == expected_count


# =============================================================================
# Expected output:
#
#   🚀 Starting session
#
#   [engine] Creating in-memory SQLite engine...
#
#   Database
#     [db_session] Opening new session + transaction...
#     ✓ test_create_single_user
#       [user_factory] Created user 1: Alice <alice@example.com>
#     [db_session] Rolling back transaction...
#
#     [db_session] Opening new session + transaction...
#     ✓ test_create_multiple_users
#       [user_factory] Created user 1: Alice <alice@example.com>
#       [user_factory] Created user 2: Bob <bob@company.com>
#     [db_session] Rolling back transaction...
#
#     [db_session] Opening new session + transaction...
#     ✓ test_isolation_between_tests  <- DB is empty, rollback worked!
#     [db_session] Rolling back transaction...
#
#   [engine] Disposing engine...
#
#   ✓ ALL PASSED │ 3/3 passed
# =============================================================================
