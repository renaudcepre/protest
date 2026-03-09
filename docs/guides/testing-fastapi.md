# Testing a FastAPI App

How to write async integration tests for a FastAPI application using ProTest, httpx, and `asgi-lifespan`.

## Async Client with Lifespan

FastAPI's `TestClient` is synchronous. For ProTest's async-first approach, `httpx.AsyncClient` with `ASGITransport` is the natural fit — but **httpx does not trigger ASGI lifespan events**.

This means if your app uses `@asynccontextmanager` lifespan (the modern FastAPI pattern for startup/shutdown), your app state won't be initialized during tests:

```python
# app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await Database.connect()
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

```python
# This will NOT work — lifespan never runs, app.state.db is missing
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport) as client:
    resp = await client.get("/users")  # 500: 'State' has no attribute 'db'
```

## The Solution: `asgi-lifespan`

The [`asgi-lifespan`](https://github.com/florimondmanca/asgi-lifespan) library is the community standard for managing ASGI lifespan in tests. It's used by projects like Datasette and Safir.

Install it:

```bash
pip install asgi-lifespan
# or
uv add asgi-lifespan
```

`LifespanManager` wraps your ASGI app, triggers the lifespan events, and gives you back an app with initialized state:

```python
from asgi_lifespan import LifespanManager

async with LifespanManager(app) as manager:
    # manager.app has lifespan state initialized
    transport = httpx.ASGITransport(app=manager.app)
    async with httpx.AsyncClient(transport=transport) as client:
        resp = await client.get("/users")  # Works!
```

## ProTest Fixture

Wrap this in a ProTest fixture with `yield` for proper setup/teardown:

```python
# tests/fixtures.py
from collections.abc import AsyncIterator

import httpx
from asgi_lifespan import LifespanManager

from protest import fixture

from myapp.app import app


@fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c
```

Bind it at the appropriate scope:

```python
# tests/session.py
from tests.fixtures import client

# SESSION scope — one client for all tests (fast, shared state)
session.bind(client)

# Or SUITE scope — fresh client per suite (isolated)
api_suite.bind(client)

# Or TEST scope (no binding) — fresh client per test (slowest, most isolated)
```

## Complete Example

### The App

```python
# myapp/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.books = {}
    yield

app = FastAPI(lifespan=lifespan)


@app.get("/books")
async def list_books(request):
    return list(request.state.books.values())


@app.post("/books", status_code=201)
async def add_book(request, book: dict):
    request.state.books[book["title"]] = book
    return book


@app.get("/books/{title}")
async def get_book(request, title: str):
    if title not in request.state.books:
        raise HTTPException(404, "Book not found")
    return request.state.books[title]
```

### The Tests

```python
# tests/fixtures.py
from collections.abc import AsyncIterator

import httpx
from asgi_lifespan import LifespanManager

from protest import fixture

from myapp.app import app


@fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c
```

```python
# tests/test_books.py
from typing import Annotated

import httpx

from protest import ProTestSuite, Use

from tests.fixtures import client

books_suite = ProTestSuite("Books", tags=["api"])


@books_suite.test()
async def test_list_books_empty(
    c: Annotated[httpx.AsyncClient, Use(client)],
) -> None:
    resp = await c.get("/books")
    assert resp.status_code == 200
    assert resp.json() == []


@books_suite.test()
async def test_add_book(
    c: Annotated[httpx.AsyncClient, Use(client)],
) -> None:
    resp = await c.post("/books", json={"title": "Dune", "author": "Herbert"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "Dune"


@books_suite.test()
async def test_get_nonexistent_book(
    c: Annotated[httpx.AsyncClient, Use(client)],
) -> None:
    resp = await c.get("/books/Ghost")
    assert resp.status_code == 404
```

```python
# tests/session.py
from protest import ProTestSession

from tests.fixtures import client
from tests.test_books import books_suite

session = ProTestSession(concurrency=4)
session.bind(client)
session.add_suite(books_suite)
```

Run:

```bash
protest run tests.session:session
```

## Alternative: Manual Lifespan (Without `asgi-lifespan`)

If you can't add a dependency, you can call your lifespan context manager directly and inject state into request scopes manually:

```python
# tests/fixtures.py
from collections.abc import AsyncIterator

import httpx

from protest import fixture

from myapp.app import app, lifespan


class _LifespanWrapper:
    """ASGI wrapper that injects lifespan state into HTTP request scopes."""

    def __init__(self, app, state):
        self.app = app
        self.state = state

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope.setdefault("state", {}).update(self.state)
        await self.app(scope, receive, send)


@fixture()
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with lifespan(app) as state:
        wrapped = _LifespanWrapper(app, state)
        transport = httpx.ASGITransport(app=wrapped)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c
```

This works but is non-standard. Prefer `asgi-lifespan` — it handles edge cases (multiple lifespans, error propagation) that a manual wrapper misses.

## Why Not `TestClient`?

FastAPI's `TestClient` (from Starlette) is synchronous and uses `requests` under the hood. It handles lifespan automatically, but:

- **Sync-only** — doesn't work with ProTest's async tests
- **Thread-based** — spawns a background thread for the event loop
- **No concurrency** — can't benefit from ProTest's parallel execution

`httpx.AsyncClient` + `asgi-lifespan` gives you native async testing that composes naturally with ProTest.

## See Also

- [Project Organization](project-organization.md) — how to structure test files
- [Fixtures](../core-concepts/fixtures.md) — scope at binding, `yield` teardown
- [Best Practices](../best-practices.md) — naming, tags, anti-patterns
