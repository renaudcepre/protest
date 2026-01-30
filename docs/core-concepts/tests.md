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
from protest import Use, fixture

@fixture()
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

## Skip

Mark tests to be skipped:

```python
# Simple skip
@session.test(skip=True)
def test_not_ready():
    pass  # Never runs

# With reason
@session.test(skip="Waiting for API v2")
def test_new_feature():
    pass
```

### Skip Object

For advanced use, import the `Skip` dataclass:

```python
from protest import Skip

@session.test(skip=Skip(reason="Blocked by #123"))
def test_blocked():
    pass
```

## Expected Failure (xfail)

Mark tests expected to fail:

```python
# Simple xfail
@session.test(xfail=True)
def test_known_bug():
    assert False  # XFAIL, not FAIL

# With reason
@session.test(xfail="Bug #456")
def test_reported_issue():
    raise ValueError()
```

### Xfail Object

```python
from protest import Xfail

# strict=True (default): unexpected pass is a failure (XPASS → FAIL)
@session.test(xfail=Xfail(reason="Flaky", strict=True))
def test_strict():
    pass  # FAIL (unexpected pass)

# strict=False: unexpected pass is OK (XPASS → PASS)
@session.test(xfail=Xfail(reason="Flaky", strict=False))
def test_lenient():
    pass  # PASS (OK)
```

## Retry

Retry failed tests automatically:

```python
# Simple retry (3 attempts)
@session.test(retry=3)
async def test_flaky_api():
    await call_external_api()

# With delay between retries
from protest import Retry

@session.test(retry=Retry(times=3, delay=1.0))
async def test_with_backoff():
    await call_api()

# Only retry specific exceptions
@session.test(retry=Retry(times=2, on=ConnectionError))
async def test_network():
    await fetch_data()

# Multiple exception types
@session.test(retry=Retry(times=2, on=(ConnectionError, TimeoutError)))
async def test_resilient():
    await risky_operation()
```

### Retry Behavior

- `times`: Maximum number of attempts (including the first)
- `delay`: Seconds to wait between retries (default: 0)
- `on`: Exception type(s) to retry on (default: `Exception`)

## Behavior Interactions

When combining options:

| Combination | Behavior |
|-------------|----------|
| `skip + xfail` | Skip takes priority (test not executed) |
| `skip + retry` | Skip takes priority |
| `xfail + retry` | Retry first, then xfail/xpass evaluation |
| `timeout + retry` | Timeout triggers retry |

## Output Capture

stdout and stderr are captured during test execution. If a test fails, the captured output is displayed in the error report.

For parallel execution, each test's output is isolated to prevent mixing.
