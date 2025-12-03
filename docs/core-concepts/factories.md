# Factories & Parameterized Tests

Factories create configurable fixture instances. Combined with parameterization, they replace pytest's `@pytest.fixture(params=[...])` pattern.

## Factory Fixtures

A factory is a fixture that accepts arguments and can be called multiple times:

```python
from protest import FixtureFactory, Use

@session.factory()
def user(name: str, role: str = "guest"):
    print(f"Creating user {name}")
    yield {"name": name, "role": role}
    print(f"Deleting user {name}")

@session.test()
async def test_users(
    user_factory: Annotated[FixtureFactory[dict], Use(user)]
):
    alice = await user_factory(name="alice", role="admin")
    bob = await user_factory(name="bob")

    assert alice["role"] == "admin"
    assert bob["role"] == "guest"
```

Key points:

- Use `@session.factory()` or `@suite.factory()` for scoped factories
- Use `@fixture()` with `managed=True` (default) for function-scoped factories
- The test receives a `FixtureFactory[T]`, not the value directly
- Call the factory with `await` - it's always async
- Each call can pass different arguments

## Factory Features

### Automatic Caching

Same arguments return the same instance:

```python
@session.test()
async def test_caching(user_factory: Annotated[FixtureFactory[dict], Use(user)]):
    alice1 = await user_factory(name="alice")
    alice2 = await user_factory(name="alice")
    bob = await user_factory(name="bob")

    assert alice1 is alice2  # Same instance (cached)
    assert alice1 is not bob  # Different args = different instance
```

### Automatic Teardown

Factories with `yield` get automatic cleanup in LIFO order:

```python
@session.factory()
def user(name: str, role: str = "guest"):
    user = db.create_user(name, role)
    yield user
    db.delete_user(user.id)  # Cleanup runs for each created instance
```

If a test creates `alice` then `bob`, teardown runs `bob` first, then `alice`.

### Dependencies

Factories can depend on other fixtures:

```python
@session.fixture()
def database():
    return Database()

@session.factory()
def user(
    db: Annotated[Database, Use(database)],
    name: str,
    role: str = "guest"
):
    user = db.insert_user(name, role)
    yield user
    db.delete_user(user.id)
```

## Parameterized Tests

Use `ForEach` and `From` to run tests with multiple values:

```python
from protest import ForEach, From

HTTP_CODES = ForEach([200, 201, 204])

@session.test()
def test_success_codes(code: Annotated[int, From(HTTP_CODES)]):
    assert code in range(200, 300)
```

This runs 3 tests: one for each code.

### Custom IDs

Provide readable names for test output:

```python
SCENARIOS = ForEach(
    [{"user": "alice", "expect": 200}, {"user": "bob", "expect": 403}],
    ids=lambda s: s["user"]
)

@session.test()
def test_permissions(scenario: Annotated[dict, From(SCENARIOS)]):
    # Output shows: test_permissions[alice], test_permissions[bob]
    pass
```

### Cartesian Product

Multiple `From` parameters create all combinations:

```python
USERS = ForEach(["alice", "bob"])
METHODS = ForEach(["GET", "POST"])

@session.test()
def test_api(
    user: Annotated[str, From(USERS)],
    method: Annotated[str, From(METHODS)]
):
    # Runs 4 times: alice+GET, alice+POST, bob+GET, bob+POST
    pass
```

## Parameterized Factories

This is the ProTest alternative to pytest's parameterized fixtures.

### The pytest way (implicit)

```python
# pytest - iteration hidden in fixture
@pytest.fixture(params=["postgres", "sqlite"])
def db(request):
    return connect(request.param)

def test_queries(db):  # Runs twice, but you can't tell by reading this
    pass
```

### The ProTest way (explicit)

```python
ENGINES = ForEach(["postgres", "sqlite"])

@session.factory()
def database(engine_type: str):
    db = connect(engine_type)
    yield db
    db.close()

@session.test()
async def test_queries(
    engine: Annotated[str, From(ENGINES)],
    db_factory: Annotated[FixtureFactory[DB], Use(database)]
):
    db = await db_factory(engine_type=engine)
    assert db.is_connected()
```

Benefits:

- **Visible**: `From(ENGINES)` shows the test runs multiple times
- **Explicit**: You see exactly how the fixture is configured
- **Flexible**: Other tests can use the same factory without the loop:

```python
@session.test()
async def test_postgres_only(
    db_factory: Annotated[FixtureFactory[DB], Use(database)]
):
    db = await db_factory(engine_type="postgres")  # No loop
```

## Error Handling

Factory errors are reported as **SETUP ERROR**, not test failures:

```
⚠ test_create_user: [FIXTURE] ConnectionError: Database unavailable
```

This distinguishes infrastructure problems from test bugs.