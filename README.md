![ProTest](assets/logo-term.svg)

Modern, async-first testing framework for Python 3.10+

**Explicit dependencies. Native async. Built-in parallelism.**

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
protest test_sample:session
```

## Explicit Dependencies

No magic fixture names. You declare what you need:

```python
from typing import Annotated
from protest import ProTestSession, Use, Scope, fixture

session = ProTestSession()


@fixture(scope=Scope.SESSION)
async def database():
    db = await Database.connect()
    yield db
    await db.close()


@session.test()
async def test_create_user(db: Annotated[Database, Use(database)]):
    user = await db.create_user("alice")
    assert user.name == "alice"
```

Functions without `@fixture` are treated as `FUNCTION` scope by default:

```python
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

## Installation

```bash
pip install protest
```

Or with uv:
```bash
uv add protest
```

## CLI Usage

```bash
protest module:session                    # Run tests
protest module:session -n 4               # Parallel (4 workers)
protest module:session --lf               # Re-run failed tests only
protest module:session --collect-only     # List tests without running
protest module:session --cache-clear      # Clear cache before run
protest --app-dir src module:session      # Look for module in src/
```

## API Reference

### Core Classes

#### `ProTestSession`

Main entry point. Orchestrates test execution.

```python
session = ProTestSession(
    concurrency=1,      # Default parallel workers
    autouse=[fixture1]  # Auto-resolve these fixtures at session start
)

@session.test()
def test_something(): ...

session.include_suite(my_suite)
session.use(my_plugin)
```

#### `ProTestSuite`

Groups related tests with optional max concurrency cap.

```python
from protest import ProTestSuite

api_suite = ProTestSuite(name="api", max_concurrency=8)

@api_suite.test()
async def test_endpoint(): ...

session.include_suite(api_suite)
```

### Fixtures

Fixtures are scoped based on where they are defined:
- `@session.fixture()` - Session scope (lives entire session)
- `@suite.fixture()` - Suite scope (lives while suite runs)
- Plain functions - Function scope (fresh per test)

```python
# Session-scoped fixture with teardown
@session.fixture()
async def database():
    db = await connect()
    yield db                         # Teardown after yield
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

### Scopes

| Scope | Lifecycle | Use Case |
|-------|-----------|----------|
| `SESSION` | Created once, shared across all tests | DB connections, expensive resources |
| `SUITE` | Created once per suite | Suite-specific config |
| `FUNCTION` | Fresh instance per test | Isolated test data |

**Rule:** A fixture can only depend on fixtures with equal or wider scope.
`FUNCTION` can use `SUITE`/`SESSION`. `SUITE` can use `SESSION`. `SESSION` cannot use `FUNCTION`.

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
protest module:session --lf           # Run last-failed tests
protest module:session --cache-clear  # Clear cache
```

Cache stored in `.protest/cache.json`.

## Why Not pytest?

|          | pytest             | ProTest                   |
|----------|--------------------|---------------------------|
| Fixtures | Implicit (by name) | Explicit (`Use(fixture)`) |
| Async    | Plugin required    | Native                    |
| Parallel | Plugin required    | Built-in                  |
| Cycles   | Runtime error      | Impossible by design      |

pytest is battle-tested with a huge ecosystem. Use ProTest if you want FastAPI-style
explicit dependencies and native async in your tests.


## License

MIT
