# ProTest

**Async-first testing with explicit dependency injection.**

ProTest is a Python testing framework designed for modern async applications. Instead of magic fixture names that appear from nowhere, ProTest requires you to explicitly declare what each test needs.

## Why ProTest?

- **Explicit dependencies**: No guessing where fixtures come from. You declare them with `Use(fixture)`.
- **Tree-based scoping**: Fixture scope is determined by where you decorate, not a string parameter.
- **Async-native**: Built for async from the ground up, not bolted on.
- **Built-in parallelism**: Run tests concurrently with `-n 4`.

## Quick Example

```python
from typing import Annotated
from protest import ProTestSession, Use

session = ProTestSession()

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
