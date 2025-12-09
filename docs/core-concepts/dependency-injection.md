# Dependency Injection

ProTest uses explicit dependency injection. You declare what a test or fixture needs using type annotations.

## The Use Marker

Dependencies are declared using `Annotated[Type, Use(fixture)]`:

```python
from typing import Annotated
from protest import ProTestSession, Use, fixture

session = ProTestSession()

@fixture()
def database():
    return Database()

@session.test()
async def test_query(db: Annotated[Database, Use(database)]):
    result = await db.query("SELECT 1")
    assert result == 1
```

The `Use` marker takes a **function reference**, not a string. This makes dependencies explicit and enables IDE navigation.

## Why Function References?

Using function references instead of string names has benefits:

1. **IDE support**: Go to definition, find usages, refactoring
2. **No typos**: Python raises `NameError` if you reference a non-existent function
3. **No cycles**: You can't reference a function before it's defined

```python
# This won't work - Python raises NameError
@session.test()
async def test_bad(x: Annotated[str, Use(undefined_fixture)]):
    pass

def undefined_fixture():
    return "oops"
```

## Fixtures Using Fixtures

Fixtures can depend on other fixtures:

```python
@session.fixture()
def config():
    return {"db_url": "postgres://localhost"}

@session.fixture()
async def database(cfg: Annotated[dict, Use(config)]):
    return await connect(cfg["db_url"])

@session.test()
async def test_query(db: Annotated[Database, Use(database)]):
    # database depends on config, which is resolved first
    pass
```

## Resolution Order

ProTest resolves dependencies automatically:

1. Analyze the test's parameters
2. For each `Use(fixture)`, recursively resolve that fixture's dependencies
3. Execute fixtures in dependency order (dependencies first)
4. Inject resolved values into the test

## Caching

Fixtures are cached according to their scope:

- **Session fixtures**: Resolved once, reused across all tests
- **Suite fixtures**: Resolved once per suite
- **Function fixtures**: Fresh for each test

If two tests both use `database`, and `database` is session-scoped, they share the same instance.

## Errors

### ScopeMismatchError

Raised when a fixture depends on a narrower scope:

```python
@fixture()  # Function scope
def per_test():
    return "fresh"

@session.fixture()  # Session scope
def shared(x: Annotated[str, Use(per_test)]):
    # ERROR: session can't depend on function-scoped
    return x
```

Fix: Either widen the dependency's scope or narrow the dependent fixture's scope.

### FixtureError

Raised when a fixture fails during execution. The error wraps the original exception and identifies which fixture failed:

```
FixtureError: Fixture 'database' failed
  Original error: ConnectionRefused: localhost:5432
```

Fixture errors are reported as **SETUP ERROR**, not test failures. This distinguishes test bugs from infrastructure issues.
