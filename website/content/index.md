---
title: ProTest
description: Async-first Python testing framework with explicit dependency injection.
---

![ProTest](/logo.svg){.h-16.sm:h-24.mx-auto.mb-2}

::div{.text-center.text-lg.text-gray-400.mb-8}
Async-first Python testing framework with explicit dependency injection.
::

## Features

- **Async-first** — Every test runs in an async context. No plugins, no hacks.
- **Explicit dependency injection** — Declare what your test needs via function parameters, like FastAPI.
- **Fixture scoping** — Session, suite, and test scopes with automatic lifecycle management.
- **Tags & filtering** — Tag tests and fixtures, filter at runtime. Tags inherit transitively.
- **Parameterized tests** — First-class `@params` decorator with clear syntax.
- **Built-in fixtures** — `caplog`, `mocker`, `Shell` and more, ready to use.
- **Rich reporting** — Beautiful terminal output with progress, diffs, and tracebacks.

## Quick example

```python
from protest import Suite, Use

suite = Suite("Auth")

@suite.fixture(scope="suite")
async def client():
    async with AsyncClient(app=app) as c:
        yield c

@suite.test("login returns a token")
async def _(client: str = Use(client)):
    response = await client.post("/login", json={"user": "admin", "pass": "secret"})
    assert response.status_code == 200
    assert "token" in response.json()
```

## Status

ProTest is in active development and not yet published on PyPI. Stay tuned for the first release.
