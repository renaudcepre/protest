![ProTest](assets/logo-term.svg)

[![CI](https://github.com/renaudcepre/protest/actions/workflows/ci.yml/badge.svg)](https://github.com/renaudcepre/protest/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/renaudcepre/protest/graph/badge.svg?token=V0MLGEE5UZ)](https://codecov.io/gh/renaudcepre/protest)

Modern, async-first testing framework for Python 3.10+

**Explicit dependencies. Native async. Built-in parallelism.**

---

## Why ProTest?

ProTest isn't just another test runner. It's built for **modern Python**: typed, async,
and explicit.

### Native I/O Concurrency

Run HTTP tests in parallel for nearly free. No heavy processes, no RAM explosion—just
asyncio.

```bash
protest run tests:session -n 10
```

*pytest-xdist spawns processes. ProTest uses coroutines.*

### Zero-Magic Injection (IDE-Ready)

**Ctrl+Click works.** Your IDE knows every type. No guessing where fixtures come from.

```python
def test_user(db: Annotated[Database, Use(database)]): ...
```

### Smart Tagging (Tag Propagation)

Tag a fixture once, and **every test using it inherits the tag automatically**—even
through deep dependency chains.

```python
@session.fixture(tags=["database"])
def db(): ...


@session.fixture()
def user_repo(db: Annotated[DB, Use(db)]): ...  # Inherits "database" tag


@session.test()
def test_users(repo: Annotated[Repo, Use(user_repo)]): ...  # Also tagged "database"
```

```bash
protest run tests:session --no-tag database  # Skips ALL tests touching DB
```

*No manual tagging. No forgotten markers.*

### Infra vs Code Errors (Error ≠ Fail)

Know instantly if your **code** failed or your **infrastructure** crashed.

```
✗ test_create_user: AssertionError       # Your bug - TEST FAILED
⚠ test_with_db: [FIXTURE] ConnectionError  # Infra issue - SETUP ERROR
```

### Typed Parameterization (`From` + `ForEach`)

No more string-matching that breaks when you rename arguments.

```python
# pytest: Rename "code" → runtime error, good luck
@pytest.mark.parametrize("code", [200, 201])
def test_status(code): ...


# ProTest: Rename-safe, IDE-aware, type-checked
CODES = ForEach([200, 201])


@session.test()
def test_status(code: Annotated[int, From(CODES)]): ...
```

### Tree-Based Scoping (Smart Teardown)

Resources are cleaned up **as soon as they're no longer needed**, not at the end. Nested
suites with predictive cleanup.

```python
session
├── api_suite  # api_client cleaned when api_suite ends
│   └── admin_suite  # admin_token cleaned when admin_suite ends
└── unit_suite  # No DB loaded if no test needs it (lazy)
```

### Managed Factories (`@factory`)

Create test data with automatic caching and cleanup. No manual teardown.

```python
@session.factory()
def user(name: str):
    user = User.create(name=name)
    yield user
    user.delete()  # Auto-cleanup for EACH created instance


@session.test()
async def test_users(user_factory: Annotated[FixtureFactory[User], Use(user)]):
    alice = await user_factory(name="alice")  # Cached
    bob = await user_factory(name="bob")  # New instance
    # Both cleaned up automatically (LIFO)
```

---

## Quick Start

```python
from protest import ProTestSession

session = ProTestSession()


def inc(x):
    return x + 1


@session.test()
def test_answer():
    assert inc(3) == 4
```

```bash
protest run test_sample:session
```

## Explicit Dependencies

No magic fixture names. You declare what you need:

```python
from typing import Annotated
from protest import ProTestSession, Use, fixture

session = ProTestSession()


@session.fixture()
async def database():
    db = await Database.connect()
    yield db
    await db.close()


@session.test()
async def test_create_user(db: Annotated[Database, Use(database)]):
    user = await db.create_user("alice")
    assert user.name == "alice"
```

Function-scoped fixtures use the `@fixture()` decorator:

```python
@fixture()
def get_test_user():
    return User(name="alice")


@session.test()
def test_user(user: Annotated[User, Use(get_test_user)]):
    assert user.name == "alice"
```

## Features

- **Explicit DI** - No guessing which fixture you're using
- **Async native** - No plugin needed, just `async def`
- **Parallel execution** - Built-in with `-n 4`
- **Scoped fixtures** - `SESSION`, `SUITE`, `FUNCTION`
- **Mix sync/async** - They just work together
- **Factory fixtures** - Return callables to create instances on-demand in tests
- **Plugin system** - Extend with custom reporters, filters
- **Last-failed mode** - Re-run only failed tests with `--lf`
- **CTRF reports** - Standardized JSON for CI/CD integration

## Installation

```bash
git clone https://github.com/renaudcepre/protest.git
cd protest
uv sync
```

## CLI Usage

```bash
protest run module:session                    # Run tests
protest run module:session -n 4               # Parallel (4 workers)
protest run module:session --lf               # Re-run failed tests only
protest run module:session --collect-only     # List tests without running
protest run module:session --cache-clear      # Clear cache before run
protest run module:session --app-dir src      # Look for module in src/
protest run module:session --ctrf-output r.json  # CTRF report for CI/CD
```

## API Reference

### Core Classes

#### `ProTestSession`

Main entry point. Orchestrates test execution.

```python
session = ProTestSession(
    concurrency=1,  # Default parallel workers
)


@session.test()
def test_something(): ...


session.add_suite(my_suite)
session.use(my_plugin)
```

#### `ProTestSuite`

Groups related tests with optional max concurrency cap.

```python
from protest import ProTestSuite

api_suite = ProTestSuite(name="api", max_concurrency=8)


@api_suite.test()
async def test_endpoint(): ...


session.add_suite(api_suite)
```

### Fixtures

Fixtures are scoped based on where they are decorated:

- `@session.fixture()` - Session scope (lives entire session)
- `@suite.fixture()` - Suite scope (lives while suite runs)
- `@fixture()` - Function scope (fresh per test)

For fixtures that should be auto-resolved at scope start (without explicit `Use()`):

- `@session.autouse()` - Auto-resolved before any test runs
- `@suite.autouse()` - Auto-resolved when suite starts

```python
# Session-scoped fixture with teardown
@session.fixture()
async def database():
    db = await connect()
    yield db  # Teardown after yield
    await db.close()


# Suite-scoped fixture
@api_suite.fixture()
def api_config():
    return load_config()


# Factory fixture - creates instances with automatic caching and teardown
@session.factory()
def user(name: str, role: str = "guest"):
    user = User.create(name=name, role=role)
    yield user
    user.delete()  # Teardown called for each created instance


# Usage: factory is injected, call it to create instances
@session.test()
async def test_multiple_users(
        user_factory: Annotated[FixtureFactory[User], Use(user)]
):
    alice = await user_factory(name="alice")
    bob = await user_factory(name="bob", role="admin")
    assert alice.name != bob.name
```

#### `Use` marker

Explicitly declare dependencies with `Annotated`:

```python
from typing import Annotated
from protest import Use


@session.test()
def test_with_deps(
        db: Annotated[Database, Use(database)],
        user: Annotated[User, Use(get_user)],
):
    ...
```

### Parameterized Tests

Use `ForEach` and `From` to run tests with multiple values:

```python
from protest import ForEach, From

CODES = ForEach([200, 201, 204])


@session.test()
def test_success_codes(code: Annotated[int, From(CODES)]):
    assert code in range(200, 300)  # Runs 3 times
```

#### Parameterized Fixtures (Inversion of Control)

In pytest, parameterized fixtures hide the iteration from the test:

```python
# pytest - the test runs twice but you can't tell by reading it
@pytest.fixture(params=["postgres", "sqlite"])
def db(request):
    return connect(request.param)


def test_queries(db): ...  # Magic: runs twice
```

In ProTest, the **test** controls the parameterization via factories:

```python
from protest import FixtureFactory, ForEach, From

ENGINES = ForEach(["postgres", "sqlite"])


@session.factory()
def database(engine_type: str):
    db = connect(engine_type)
    yield db
    db.close()


@session.test()
async def test_queries(
        engine: Annotated[str, From(ENGINES)],
        db_factory: Annotated[FixtureFactory[DB], Use(database)],
):
    db = await db_factory(engine_type=engine)  # Explicit wiring
    assert db.is_connected()
```

Benefits:

- **Visible**: `From(ENGINES)` shows the test runs multiple times
- **Explicit**: You see exactly how the fixture is configured
- **Flexible**: Other tests can use the same factory with fixed values:

```python
@session.test()
async def test_postgres_only(db_factory: Annotated[..., Use(database)]):
    db = await db_factory(engine_type="postgres")  # No loop, just postgres
```

### Scopes (Tree-Based)

The scope of a fixture is determined by **where** it's decorated, not by an enum:

```python
@session.fixture()      # Session scope - lives entire session
def database(): ...

@api_suite.fixture()    # Suite scope - lives while suite runs
def api_client(): ...

@fixture()              # Function scope - fresh per test
def payload(): ...
```

| Decorator               | Scope      | Lifecycle                             |
|-------------------------|------------|---------------------------------------|
| `@session.fixture()`    | Session    | Created once, shared across all tests |
| `@suite.fixture()`      | Suite      | Created once per suite                |
| `@fixture()`            | Function   | Fresh instance per test               |

**Rule:** A fixture can only depend on fixtures with equal or wider scope.
Function can use Suite/Session. Suite can use Session. Session cannot use Function.

### Built-in Fixtures

#### `caplog` - Log Capture

```python
from protest import caplog
from protest.entities import LogCapture


@session.test()
def test_logging(logs: Annotated[LogCapture, Use(caplog)]):
    logging.warning("Something happened")

    assert len(logs.records) == 1
    assert "Something happened" in logs.text
    assert len(logs.at_level("WARNING")) == 1
```

### Plugins

Extend ProTest by subclassing `PluginBase`:

```python
from protest import PluginBase
from protest.entities import SessionResult, TestResult


class SlackNotifier(PluginBase):
    def setup(self, session):
        self.failures = []

    def on_test_fail(self, result: TestResult):
        self.failures.append(result.name)

    async def on_session_end(self, result: SessionResult):
        if self.failures:
            await send_slack_message(f"Failed: {self.failures}")


session.use(SlackNotifier())
```

**Available hooks:**

- `setup(session)` - Called when plugin is registered
- `on_collection_finish(items)` - Filter/sort collected tests
- `on_session_start()` - Before any test runs
- `on_session_end(result)` - Tests done, async handlers can start
- `on_session_complete(result)` - All async handlers finished
- `on_suite_start(name)` / `on_suite_end(name)`
- `on_test_pass(result)` / `on_test_fail(result)`

### Cache Plugin (Built-in)

Re-run only failed tests:

```bash
protest run module:session --lf           # Run last-failed tests
protest run module:session --cache-clear  # Clear cache
```

Cache stored in `.protest/cache.json`.

## Why Not pytest?

|          | pytest             | ProTest                              |
|----------|--------------------|--------------------------------------|
| Fixtures | Implicit (by name) | Explicit (`Use(fixture)`)            |
| Params   | Hidden in fixture  | Visible in test (`From()` + factory) |
| Async    | Plugin required    | Native                               |
| Parallel | Plugin required    | Built-in                             |
| Cycles   | Runtime error      | Impossible by design                 |

pytest is battle-tested with a huge ecosystem. Use ProTest if you want FastAPI-style
explicit dependencies and native async in your tests.

## License

MIT
