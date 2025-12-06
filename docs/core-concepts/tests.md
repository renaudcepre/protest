# Tests

Tests are functions decorated with `@session.test()` or `@suite.test()`.

## Basic Test

```python
@session.test()
async def test_simple():
    assert 1 + 1 == 2
```

## Async and Sync

Both async and sync tests are supported:

```python
@session.test()
async def test_async():
    await some_async_operation()
    assert True

@session.test()
def test_sync():
    result = some_sync_operation()
    assert result == expected
```

Sync tests are automatically wrapped to run in the async event loop.

## Test with Fixtures

Tests declare their dependencies using type annotations:

```python
from typing import Annotated
from protest import Use

def database():
    return Database()

@session.test()
async def test_with_db(db: Annotated[Database, Use(database)]):
    assert db.is_connected()
```

See [Dependency Injection](dependency-injection.md) for details.

## Tags

Tags categorize tests for filtering:

```python
@session.test(tags=["slow", "integration"])
async def test_full_workflow():
    pass
```

Run only tagged tests:

```bash
protest run tests:session --tag integration
```

### Tag Inheritance

Tests inherit tags from:

1. Their suite (and parent suites)
2. Fixtures they use (transitively)

```python
api_suite = ProTestSuite("API", tags=["api"])

@fixture(tags=["database"])
def db():
    return Database()

@api_suite.test()
async def test_api_call(db: Annotated[Database, Use(db)]):
    # This test has tags: {"api", "database"}
    pass
```

## Test Naming

By default, the test name is the function name. Test output shows:

```
Suite
  ✓ test_function_name (0.01s)
```

## Timeout

Limit test execution time with the `timeout` parameter (in seconds):

```python
@session.test(timeout=5.0)
async def test_api_call():
    """Fails if takes longer than 5 seconds."""
    await slow_api_call()

@suite.test(timeout=0.5)
def test_sync():
    """Works with sync tests too."""
    time.sleep(1)  # Will timeout
```

### Behavior

- Timeout applies to the test body only (after fixture setup, before teardown)
- On timeout, the test fails with `TimeoutError`
- Sync tests: the executor thread continues but the test is marked as failed
- Negative timeout raises `ValueError` at decoration time

### With xfail

If a test is expected to timeout:

```python
@session.test(xfail="Known slow", timeout=0.1)
async def test_slow_operation():
    await very_slow_operation()  # XFAIL, not FAIL
```

### With skip

Skipped tests never run, so timeout doesn't apply:

```python
@session.test(skip="Not ready", timeout=0.001)
async def test_not_ready():
    await something()  # Never executed
```

## Output Capture

stdout and stderr are captured during test execution. If a test fails, the captured output is displayed in the error report.

For parallel execution, each test's output is isolated to prevent mixing.
