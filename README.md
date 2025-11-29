# ProTest

Modern, async-first testing framework for Python 3.10+. Inspired by FastAPI's explicit dependency injection.

## Installation

```bash
pip install protest
```

## Quick Start

```python
from typing import Annotated
from protest import ProTestSession, ProTestSuite, Scope, Use

session = ProTestSession()
suite = ProTestSuite("User Tests")
session.include_suite(suite)

@session.fixture(scope=Scope.SESSION)
async def database():
    db = await connect_database()
    yield db
    await db.close()

@suite.fixture(scope=Scope.FUNCTION)
def api_client(db: Annotated[Database, Use(database)]):
    return APIClient(db)

@suite.test()
async def test_create_user(client: Annotated[APIClient, Use(api_client)]):
    user = await client.create_user("alice")
    assert user.name == "alice"
```

```bash
protest run myapp.tests:session
```

## Key Concepts

### Explicit Dependencies

No magic fixture names. Dependencies declared in the signature:

```python
@suite.test()
def test_something(
    db: Annotated[Database, Use(database)],
    cache: Annotated[Redis, Use(redis)],
):
    ...
```

### Fixture Scopes

| Scope | Lifetime |
|-------|----------|
| `SESSION` | Entire test run |
| `SUITE` | Single suite |
| `FUNCTION` | Single test (default) |

### Parallel Execution

```bash
protest run tests:session -n 4
```

`FUNCTION`-scoped fixtures are isolated per test. `SESSION`/`SUITE` fixtures use automatic locking.

### Sync/Async Transparency

Mix sync and async freely:

```python
@session.fixture(scope=Scope.SESSION)
async def async_db():
    return await connect()

@suite.fixture(scope=Scope.FUNCTION)
def sync_service(db: Annotated[DB, Use(async_db)]):  # Just works
    return Service(db)
```

### Generator Fixtures

Use `yield` for setup/teardown:

```python
@session.fixture(scope=Scope.SESSION)
async def database():
    db = await Database.connect()
    yield db
    await db.disconnect()
```

### Plugins

```python
from protest import PluginBase

class SlackNotifier(PluginBase):
    def on_test_fail(self, result):
        slack.post(f"FAILED: {result.name}")

session.use(SlackNotifier())
```

## CLI

```bash
protest run module:session           # Run all tests
protest run module:session -n 4      # Parallel execution
protest run module:session --app-dir ./src
```

## vs pytest

| | pytest | ProTest |
|-|--------|---------|
| Fixtures | Implicit (by name) | Explicit (`Use(fixture)`) |
| Async | Plugin | Native |
| Parallel | Plugin | Built-in |

## Examples

See [`examples/`](./examples) for complete demos.
