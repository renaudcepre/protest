"""Demo: Parameterized Factories - The ProTest alternative to pytest's parameterized fixtures.

Run with: uv run protest run examples.basic.parameterized_factory_demo:session

In pytest, you'd write:
    @pytest.fixture(params=["postgres", "sqlite"])
    def db(request):
        return connect(request.param)

    def test_queries(db):  # Runs twice, but you can't tell by reading this
        ...

In ProTest, you invert control: the TEST decides what variations to run.
This makes the parameterization explicit and visible where it matters.
"""

from typing import Annotated

from protest import FixtureFactory, ForEach, From, ProTestSession, Use

session = ProTestSession()


ENGINES = ForEach(["postgres", "sqlite"], ids=lambda engine: engine)


class FakeDB:
    def __init__(self, engine: str) -> None:
        self.engine = engine
        self.connected = True

    def query(self, sql: str) -> list[str]:
        return [f"[{self.engine}] {sql}"]

    def close(self) -> None:
        self.connected = False
        print(f"    [{self.engine}] Connection closed")


@session.factory()
def database(engine_type: str) -> FakeDB:
    """Configurable database factory - the TEST decides which engine to use."""
    print(f"    [setup] Connecting to {engine_type}...")
    db = FakeDB(engine_type)
    yield db
    db.close()


@session.test()
async def test_queries_all_engines(
    engine: Annotated[str, From(ENGINES)],
    db_factory: Annotated[FixtureFactory[FakeDB], Use(database)],
) -> None:
    """Test runs for each engine: postgres, sqlite.

    Unlike pytest, you SEE the parameterization right here in the test signature.
    The From(ENGINES) tells you this test runs multiple times.
    The db_factory(engine_type=engine) shows exactly how the fixture is configured.
    """
    db = await db_factory(engine_type=engine)

    result = db.query("SELECT 1")

    assert db.connected
    assert engine in result[0]


@session.test()
async def test_postgres_only(
    db_factory: Annotated[FixtureFactory[FakeDB], Use(database)],
) -> None:
    """This test uses the same factory but ONLY tests postgres.

    In pytest, you'd need a separate fixture or complex skip logic.
    In ProTest, just don't use ForEach - call the factory directly.
    """
    db = await db_factory(engine_type="postgres")

    assert db.engine == "postgres"


USERS = ForEach(["alice", "bob", "charlie"])
ROLES = ForEach(["admin", "guest"])


@session.factory()
def user(name: str, role: str) -> dict[str, str]:
    print(f"    [setup] Creating user {name} ({role})")
    yield {"name": name, "role": role}
    print(f"    [teardown] Deleting user {name}")


@session.test()
async def test_user_permissions_matrix(
    name: Annotated[str, From(USERS)],
    role: Annotated[str, From(ROLES)],
    user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
) -> None:
    """Cartesian product: 3 users × 2 roles = 6 test runs.

    Each combination is explicit in the test signature.
    The factory receives exactly the parameters you pass.
    """
    current_user = await user_factory(name=name, role=role)

    assert current_user["name"] == name
    assert current_user["role"] == role

    if role == "admin":
        assert current_user["role"] == "admin"
