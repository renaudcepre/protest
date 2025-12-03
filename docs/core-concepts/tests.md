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

## Output Capture

stdout and stderr are captured during test execution. If a test fails, the captured output is displayed in the error report.

For parallel execution, each test's output is isolated to prevent mixing.
