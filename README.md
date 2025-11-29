<p align="center">
  <img src="https://raw.githubusercontent.com/rcepre/protest/main/docs/assets/logo.png" alt="ProTest" width="300">
</p>

<p align="center">
  <em>Modern, async-first testing framework for Python 3.12+</em>
</p>

<p align="center">
  <a href="https://pypi.org/project/protest"><img src="https://img.shields.io/pypi/v/protest?color=%2334D058" alt="PyPI version"></a>
  <a href="https://pypi.org/project/protest"><img src="https://img.shields.io/pypi/pyversions/protest" alt="Python versions"></a>
  <a href="https://github.com/rcepre/protest/blob/main/LICENSE"><img src="https://img.shields.io/github/license/rcepre/protest" alt="License"></a>
</p>

---

**ProTest** is a modern testing framework built from scratch for async Python applications. Inspired by FastAPI's explicit dependency injection and pytest's simplicity.

## Why ProTest?

- **Async-native**: Built around `asyncio` from the ground up. No more `pytest-asyncio` quirks.
- **Explicit dependencies**: No magic fixture names. Use `Annotated[Type, Use(fixture)]` for clear, type-safe injection.
- **Parallel execution**: Run tests concurrently with proper fixture isolation.
- **Zero legacy**: Fresh codebase, modern Python 3.12+ features, no accumulated technical debt.

## Installation

```bash
pip install protest
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add protest
```

## Quick Start

```python
from protest import ProTestSession, ProTestSuite, Scope, Use
from typing import Annotated

# Create a session (like FastAPI app)
session = ProTestSession()

# Create a suite (like APIRouter)
api_suite = ProTestSuite("API Tests")
session.include_suite(api_suite)

# Define fixtures with explicit scopes
@session.fixture(scope=Scope.SESSION)
async def database():
    db = await connect_database()
    yield db
    await db.close()

@api_suite.fixture(scope=Scope.FUNCTION)
def api_client(db: Annotated[Database, Use(database)]):
    return APIClient(db)

# Write tests with explicit dependencies
@api_suite.test()
async def test_user_creation(client: Annotated[APIClient, Use(api_client)]):
    user = await client.create_user("alice")
    assert user.name == "alice"

@api_suite.test()
async def test_user_retrieval(client: Annotated[APIClient, Use(api_client)]):
    user = await client.get_user(1)
    assert user is not None
```

Run your tests:

```bash
protest run myapp.tests:session
```

## Key Features

### Explicit Dependency Injection

No more guessing which fixtures are available. Dependencies are declared in the function signature:

```python
from typing import Annotated
from protest import Use

@suite.test()
def test_with_deps(
    db: Annotated[Database, Use(database)],
    cache: Annotated[Redis, Use(redis_client)],
):
    # Both fixtures are explicitly requested
    ...
```

**Benefit**: Your IDE knows exactly what's injected. Refactoring is safe.

### Fixture Scopes

Control fixture lifecycle with three scopes:

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `SESSION` | Entire test run | Database connections, expensive resources |
| `SUITE` | Single test suite | Suite-specific setup |
| `FUNCTION` | Single test | Fresh state per test (default) |

```python
@session.fixture(scope=Scope.SESSION)
async def shared_database():
    # Created once, shared across all tests
    ...

@suite.fixture(scope=Scope.SUITE)
def suite_cache():
    # Created once per suite
    ...

@suite.fixture(scope=Scope.FUNCTION)
def fresh_data():
    # Created fresh for each test
    ...
```

### Parallel Execution

Run tests concurrently with a single flag:

```bash
protest run tests:session -n 4
```

ProTest ensures:
- `FUNCTION`-scoped fixtures are isolated per test
- `SESSION`/`SUITE` fixtures are thread-safe with automatic locking
- Teardown happens in correct order

```python
# Control concurrency per suite
fast_suite = ProTestSuite("Fast Tests", concurrency=10)
db_suite = ProTestSuite("Database Tests", concurrency=1)  # Sequential
```

### Sync/Async Transparency

Mix sync and async freely. ProTest handles the bridging:

```python
@session.fixture(scope=Scope.SESSION)
async def async_database():
    return await connect()

@suite.fixture(scope=Scope.FUNCTION)
def sync_processor(db: Annotated[DB, Use(async_database)]):
    # Sync fixture depending on async fixture - just works
    return Processor(db)

@suite.test()
async def test_async(proc: Annotated[Processor, Use(sync_processor)]):
    # Async test using sync fixture - just works
    result = await proc.process_async()
    assert result.ok
```

### Generator Fixtures (Setup/Teardown)

Use `yield` for automatic cleanup:

```python
@session.fixture(scope=Scope.SESSION)
async def database():
    db = await Database.connect()
    yield db  # Tests run here
    await db.disconnect()  # Cleanup guaranteed

@suite.fixture(scope=Scope.FUNCTION)
def temp_file():
    path = create_temp_file()
    yield path
    os.unlink(path)  # Always cleaned up, even on failure
```

### Extensible Plugin System

Create plugins by extending `PluginBase`:

```python
from protest import PluginBase
from protest.events.data import TestResult, SessionResult

class SlackNotifier(PluginBase):
    def on_session_complete(self, result: SessionResult):
        if result.failed > 0:
            slack.post(f"Tests failed: {result.failed}/{result.passed + result.failed}")

    def on_test_fail(self, result: TestResult):
        slack.post(f"FAILED: {result.name}")

# Register plugin
session = ProTestSession()
session.use(SlackNotifier())
```

Available hooks:
- `on_session_start()` / `on_session_end(result)` / `on_session_complete(result)`
- `on_suite_start(name)` / `on_suite_end(name)`
- `on_test_pass(result)` / `on_test_fail(result)`

## CLI Reference

```bash
# Run all tests
protest run module:session

# Run with parallelism
protest run module:session -n 4

# Specify app directory
protest run tests:session --app-dir ./src
```

## Comparison with pytest

| Feature | pytest | ProTest |
|---------|--------|---------|
| Fixture injection | Implicit (by name) | Explicit (`Use(fixture)`) |
| Async support | Plugin (`pytest-asyncio`) | Native |
| Parallel execution | Plugin (`pytest-xdist`) | Built-in |
| Fixture discovery | Magic (`conftest.py`) | Explicit registration |
| Python version | 3.8+ | 3.12+ |

ProTest is **not** a pytest replacement for all cases. Use pytest if you need:
- Massive plugin ecosystem
- Legacy Python support
- Established community patterns

Use ProTest if you want:
- Modern, explicit architecture
- First-class async support
- Clean, typed codebase

## Examples

Check the [`examples/`](./examples) directory:

- **[basic/](./examples/basic)**: Full feature demonstration
- **[fastapi_demo/](./examples/fastapi_demo)**: Testing a FastAPI application

## Requirements

- Python 3.12+
- No runtime dependencies (just stdlib)

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contributing

Contributions welcome! Please read our contributing guidelines first.

---

<p align="center">
  <em>Built with focus on explicitness and modern Python.</em>
</p>