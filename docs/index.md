# ProTest

**Async-first testing with explicit dependency injection.**

ProTest is a Python testing framework designed for modern async applications. Instead of implicit fixture resolution by name, ProTest requires you to explicitly declare what each test needs.

## Why ProTest?

ProTest isn't just another test runner. It's built for **modern Python**: typed, async, and explicit.

### Native I/O Concurrency

Tests run as coroutines on a single event loop. Parallel I/O tests without spawning separate processes.

```bash
protest run tests:session -n 10
```

### Explicit Injection (IDE-Ready)

**Ctrl+Click works.** Your IDE knows every type. No guessing where fixtures come from.

```python
# pytest: "db" is resolved by name — requires searching through fixtures
def test_user(db): ...

# ProTest: Ctrl+Click → Go to definition. Full type inference.
def test_user(db: Annotated[Database, Use(database)]): ...
```

### Smart Tagging (Tag Propagation)

Tag a fixture once, and **every test using it inherits the tag automatically**—even through deep dependency chains.

```python
@fixture(tags=["database"])
def db(): ...
session.bind(db)

@fixture()
def user_repo(db: Annotated[DB, Use(db)]): ...  # Inherits "database" tag
session.bind(user_repo)

@session.test()
def test_users(repo: Annotated[Repo, Use(user_repo)]): ...  # Also tagged "database"
```

```bash
protest run tests:session --no-tag database  # Skips ALL tests touching DB
```

*No manual tagging. No forgotten markers.*

### Infra vs Code Errors

Know instantly if your **code** failed or your **infrastructure** crashed.

```
✗ test_create_user: AssertionError          # Your bug - TEST FAILED
⚠ test_with_db: [FIXTURE] ConnectionError   # Infra issue - SETUP ERROR
```

*pytest reports both as FAILED, making it harder to distinguish test failures from infrastructure issues.*

### Typed Parameterization

No more string-matching that breaks when you rename arguments.

```python
# pytest: Rename "code" → runtime error
@pytest.mark.parametrize("code", [200, 201])
def test_status(code): ...

# ProTest: Rename-safe, IDE-aware, type-checked
CODES = ForEach([200, 201])

@session.test()
def test_status(code: Annotated[int, From(CODES)]): ...
```

### Tree-Based Scoping (Smart Teardown)

Resources are cleaned up **as soon as they're no longer needed**. Nested suites with predictive cleanup.

### Managed Factories

Create test data with automatic caching and cleanup. No manual teardown.

## Quick Example

```python
from typing import Annotated
from protest import ProTestSession, Use, fixture

session = ProTestSession()

@fixture()
def database():
    return {"connected": True}

@session.test()
async def test_db_connected(db: Annotated[dict, Use(database)]):
    assert db["connected"] is True
```

Run it:

```bash
protest run mymodule:session
```

## Features

- [**Sessions & Suites**](core-concepts/sessions-and-suites.md) - Organize tests hierarchically
- [**Fixtures**](core-concepts/fixtures.md) - Setup and teardown with automatic cleanup
- [**Dependency Injection**](core-concepts/dependency-injection.md) - Explicit, type-safe dependencies
- **Parallel Execution** - Speed up I/O-bound tests
- **Tags** - Filter tests by category
- **Plugins** - Extend with custom reporters and hooks

## Getting Started

New to ProTest? Start here:

1. [Installation](getting-started/installation.md)
2. [Quickstart](getting-started/quickstart.md)
3. [Running Tests](getting-started/running-tests.md)
