# Fixtures

Fixtures provide reusable setup and teardown logic for tests.

## What is a Fixture?

A fixture is a function that provides a value to tests. It can be a simple function or include cleanup logic.

```python
@fixture()
def config():
    return {"debug": True}
```

## Scopes

Fixture scope is determined by the `scope` parameter in the decorator.

### Session Scope

Defined with `@fixture(scope=FixtureScope.SESSION)`. Lives for the entire test session.

```python
from protest import fixture, FixtureScope

@fixture(scope=FixtureScope.SESSION)
async def database():
    db = await connect()
    yield db
    await db.close()

# Bind to session
session.use_fixtures([database])
```

Use case: Expensive resources shared across all tests (database connections, HTTP clients).

### Suite Scope

Defined with `@fixture(scope=FixtureScope.SUITE)`. Lives for the duration of the suite.

```python
@fixture(scope=FixtureScope.SUITE)
def api_client(db: Annotated[Database, Use(database)]):
    return Client(db)

# Bind to suite
api_suite.use_fixtures([api_client])
```

Use case: Resources shared within a group of related tests.

### Test Scope (Default)

Use `@fixture()` decorator. Fresh instance for each test.

```python
@fixture()
def request_id():
    return str(uuid.uuid4())

# With tags:
@fixture(tags=["slow"])
def temp_file():
    path = Path("/tmp/test.txt")
    path.touch()
    yield path
    path.unlink()
```

Use case: Isolated state per test, unique IDs, temporary files.

**Note:** All fixtures must be decorated. Plain functions without `@fixture()` raise `PlainFunctionError` when used with `Use()`.

## Teardown with yield

Use `yield` to separate setup from teardown:

```python
@fixture(scope=FixtureScope.SESSION)
async def database():
    # Setup
    db = await connect()

    yield db  # Value provided to tests

    # Teardown (runs even if test fails)
    await db.close()

session.use_fixtures([database])
```

Teardown runs in reverse order (LIFO). If multiple fixtures are used, the last one set up is the first one torn down.

## Scope Rules

A fixture can only depend on fixtures with equal or wider scope:

| Fixture Scope | Can Depend On |
|---------------|---------------|
| Session | Session only |
| Suite | Session, parent suites, same suite |
| Test | Anything |

Violating this raises `ScopeMismatchError`:

```python
@fixture()
def function_scoped():
    return "per-test"

@fixture(scope=FixtureScope.SESSION)
def session_scoped(x: Annotated[str, Use(function_scoped)]):
    # ERROR: session fixture can't depend on function-scoped
    return x
```

## Fixture Tags

Tags on fixtures propagate to tests that use them:

```python
@fixture(tags=["database"])
def db():
    return Database()

@session.test()
async def test_query(db: Annotated[Database, Use(db)]):
    # This test inherits the "database" tag
    pass
```

This works transitively: if fixture A depends on fixture B with tag "x", tests using A also get tag "x".

## Autouse Fixtures

Autouse fixtures are automatically resolved at their scope start, without being explicitly requested by tests.

### Session Autouse

Use `@fixture(scope=FixtureScope.SESSION, autouse=True)` for fixtures that must run before any test:

```python
@fixture(scope=FixtureScope.SESSION, autouse=True)
def configure_logging():
    logging.basicConfig(level=logging.DEBUG)
    yield
    logging.shutdown()

session.use_fixtures([configure_logging])
```

Session autouse fixtures are resolved at `SESSION_SETUP_START`, before any test runs.

### Suite Autouse

Use `@fixture(scope=FixtureScope.SUITE, autouse=True)` for fixtures that must run when a suite starts:

```python
@fixture(scope=FixtureScope.SUITE, autouse=True)
def clear_environment():
    old = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.update(old)

api_suite.use_fixtures([clear_environment])
```

Suite autouse fixtures are resolved when the suite starts (before its first test). For nested suites, parent autouse fixtures run before child autouse fixtures.

### Test Autouse

Use `@fixture(autouse=True)` for fixtures that must run at the start of every test:

```python
@fixture(autouse=True)
def reset_state():
    global_cache.clear()
    yield
    global_cache.clear()
```

Test autouse fixtures are resolved before each test runs.

### When to Use Autouse

Use autouse when:

- The fixture has **side effects** needed by all tests (logging, environment setup)
- Tests don't need the fixture's **return value**, just its **effect**
- You want to ensure setup/teardown runs **regardless** of which tests are selected

Don't use autouse when tests need the fixture's value - use explicit `Use()` instead.
