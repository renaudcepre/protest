"""Demo: Factory CLASS pattern with SQLAlchemy (managed=False).

Run with:
    cd examples/sqlalchemy_demo
    uv sync
    uv run protest run demo_factory_class:session

This shows the advanced pattern using custom Factory Classes:
- Full control over creation logic
- Helper methods (create_many, build, etc.)
- Inter-factory dependencies
- Errors still reported as SETUP ERROR (via SafeProxy)
"""

from dataclasses import dataclass
from typing import Annotated

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from protest import ProTestSession, ProTestSuite, Use, factory, fixture

session = ProTestSession()


# =============================================================================
# MODELS
# =============================================================================


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    company_id: Mapped[int] = mapped_column()


# =============================================================================
# FACTORY CLASSES
# =============================================================================


@dataclass
class CompanyFactory:
    """Factory class for creating Company instances."""

    db: Session
    _counter: int = 0

    def create(self, name: str | None = None) -> Company:
        self._counter += 1
        name = name or f"Company {self._counter}"
        company = Company(name=name)
        self.db.add(company)
        self.db.flush()
        return company

    def create_many(self, count: int) -> list[Company]:
        return [self.create() for _ in range(count)]


@dataclass
class UserFactory:
    """Factory class for creating User instances with company dependency."""

    db: Session
    company_factory: CompanyFactory
    _counter: int = 0

    def create(
        self,
        name: str | None = None,
        email: str | None = None,
        company: Company | None = None,
    ) -> User:
        self._counter += 1
        name = name or f"User {self._counter}"
        email = email or f"user{self._counter}@example.com"

        if company is None:
            company = self.company_factory.create()

        user = User(name=name, email=email, company_id=company.id)
        self.db.add(user)
        self.db.flush()
        return user

    def create_many(self, count: int, company: Company | None = None) -> list[User]:
        if company is None:
            company = self.company_factory.create()
        return [self.create(company=company) for _ in range(count)]


# =============================================================================
# FIXTURES
# =============================================================================


@session.fixture()
def engine():
    """Session-scoped: SQLite in-memory."""
    eng = create_engine(
        "sqlite:///file::memory:?cache=shared&uri=true",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


db_suite = ProTestSuite("Database")
session.add_suite(db_suite)


@fixture()
def db_session(engine: Annotated[object, Use(engine)]):
    """Function-scoped: fresh session per test."""
    with Session(engine) as db:
        yield db
        db.rollback()


@factory(managed=False)
def company_factory(
    db_session: Annotated[Session, Use(db_session)],
) -> CompanyFactory:
    """Non-managed factory: returns our custom CompanyFactory class."""
    return CompanyFactory(db=db_session)


@factory(managed=False)
def user_factory(
    db_session: Annotated[Session, Use(db_session)],
    company_factory: Annotated[CompanyFactory, Use(company_factory)],
) -> UserFactory:
    """Non-managed factory with dependency on another factory."""
    return UserFactory(db=db_session, company_factory=company_factory)


# =============================================================================
# TESTS
# =============================================================================


@db_suite.test()
def test_create_user_with_auto_company(
    user_factory: Annotated[UserFactory, Use(user_factory)],
) -> None:
    """User factory auto-creates a company if none provided."""
    user = user_factory.create(name="Alice")

    assert user.name == "Alice"
    assert user.company_id is not None


@db_suite.test()
def test_create_user_with_specific_company(
    company_factory: Annotated[CompanyFactory, Use(company_factory)],
    user_factory: Annotated[UserFactory, Use(user_factory)],
) -> None:
    """User can be created with a specific company."""
    acme = company_factory.create(name="ACME Corp")
    alice = user_factory.create(name="Alice", company=acme)
    bob = user_factory.create(name="Bob", company=acme)

    assert alice.company_id == acme.id
    assert bob.company_id == acme.id


@db_suite.test()
def test_create_many_users(
    user_factory: Annotated[UserFactory, Use(user_factory)],
) -> None:
    """create_many helper creates multiple users with same company."""
    users = user_factory.create_many(count=5)

    expected_count = 5
    assert len(users) == expected_count
    assert all(user.company_id == users[0].company_id for user in users)


@db_suite.test()
def test_isolation_between_tests(
    db_session: Annotated[Session, Use(db_session)],
) -> None:
    """Each test starts fresh (previous test's data rolled back)."""
    user_count = db_session.query(User).count()
    company_count = db_session.query(Company).count()

    assert user_count == 0
    assert company_count == 0


# =============================================================================
# Expected output:
#
#   🚀 Starting session
#
#   Database
#     ✓ test_create_user_with_auto_company
#     ✓ test_create_user_with_specific_company
#     ✓ test_create_many_users
#     ✓ test_isolation_between_tests
#
#   ✓ ALL PASSED │ 4/4 passed
#
# Key differences from managed factories:
# - You write a class with create(), create_many(), build(), etc.
# - ProTest injects dependencies into your factory constructor
# - You call factory.create() synchronously (no await needed!)
# - Errors in factory methods → SETUP ERROR (thanks to SafeProxy)
# =============================================================================
