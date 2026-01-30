# Fixtures

Fixtures provide reusable setup and teardown logic for tests.

## What is a Fixture?

A fixture is a function decorated with `@fixture()` that provides a value to tests.

```python
from protest import fixture

@fixture()
def config():
    return {"debug": True}
```

## Scope at Binding

**Important:** Fixture scope is determined by WHERE you bind it, not by the decorator.

The `@fixture()` decorator only marks a function as a fixture. The scope is set when you bind the fixture to a session or suite.

### Session Scope

Bind to session with `session.bind()`. Lives for the entire test session.

```python
from protest import fixture, ProTestSession

@fixture()
async def database():
    db = await connect()
    yield db
    await db.close()

session = ProTestSession()
session.bind(database)  # → SESSION scope
```

Use case: Expensive resources shared across all tests (database connections, HTTP clients).

### Suite Scope

Bind to suite with `suite.bind()`. Lives for the duration of the suite.

```python
from protest import fixture, ProTestSuite

@fixture()
def api_client(db: Annotated[Database, Use(database)]):
    return Client(db)

api_suite = ProTestSuite("API")
api_suite.bind(api_client)  # → SUITE scope
```

Use case: Resources shared within a group of related tests.

### Test Scope (Default)

Don't bind the fixture. Fresh instance for each test.

```python
@fixture()
def request_id():
    return str(uuid.uuid4())

# No binding → TEST scope (default)
```

Use case: Isolated state per test, unique IDs, temporary files.

## Summary

| Binding | Scope | Caching |
|---------|-------|---------|
| `session.bind(fn)` | SESSION | One instance for entire session |
| `suite.bind(fn)` | SUITE | One instance per suite execution |
| No binding | TEST | Fresh instance per test |

## Teardown with yield

Use `yield` to separate setup from teardown:

```python
@fixture()
async def database():
    # Setup
    db = await connect()

    yield db  # Value provided to tests

    # Teardown (runs even if test fails)
    await db.close()

session.bind(database)
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
def per_test_data():
    return "per-test"

@fixture()
def shared_resource(x: Annotated[str, Use(per_test_data)]):
    return x

session.bind(shared_resource)  # ERROR: session can't depend on test-scoped
```

## Fixture Tags

Tags are declared on the decorator and propagate to tests:

```python
@fixture(tags=["database"])
def db():
    return Database()

session.bind(db)

@session.test()
async def test_query(db: Annotated[Database, Use(db)]):
    # This test inherits the "database" tag
    pass
```

This works transitively: if fixture A depends on fixture B with tag "x", tests using A also get tag "x".

## Autouse Fixtures

Autouse fixtures are automatically resolved at their scope start, without being explicitly requested by tests. The `autouse=True` flag is passed to `bind()`.

### Session Autouse

```python
@fixture()
def configure_logging():
    logging.basicConfig(level=logging.DEBUG)
    yield
    logging.shutdown()

session.bind(configure_logging, autouse=True)
```

Session autouse fixtures are resolved at `SESSION_SETUP_START`, before any test runs.

### Suite Autouse

```python
@fixture()
def clear_environment():
    old = os.environ.copy()
    os.environ.clear()
    yield
    os.environ.update(old)

api_suite.bind(clear_environment, autouse=True)
```

Suite autouse fixtures are resolved when the suite starts (before its first test).

### When to Use Autouse

Use autouse when:

- The fixture has **side effects** needed by all tests (logging, environment setup)
- Tests don't need the fixture's **return value**, just its **effect**
- You want to ensure setup/teardown runs **regardless** of which tests are selected

Don't use autouse when tests need the fixture's value - use explicit `Use()` instead.

## Plain Functions

All fixtures must be decorated with `@fixture()`. Plain functions raise `PlainFunctionError` when used with `Use()`:

```python
def not_a_fixture():  # Missing @fixture()!
    return "value"

@session.test()
def test_error(x: Annotated[str, Use(not_a_fixture)]):
    pass  # PlainFunctionError!
```
