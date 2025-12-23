# Quickstart

This guide walks you through creating your first ProTest session in under 5 minutes.

## Create a Test File

Create `tests.py`:

```python
from typing import Annotated
from protest import ProTestSession, ProTestSuite, Use, fixture

# Create a session - the root of your test hierarchy
session = ProTestSession()

# Create a suite to group related tests
api_suite = ProTestSuite("API")
session.add_suite(api_suite)


# Define a function-scoped fixture (fresh instance per test)
# Use @session.bind() for session scope, @suite.bind() for suite scope
@fixture()
def config():
    return {"api_url": "https://api.example.com"}


# Write a test that uses the fixture
@api_suite.test()
async def test_config_has_url(cfg: Annotated[dict, Use(config)]):
    assert "api_url" in cfg


@api_suite.test()
async def test_url_is_https(cfg: Annotated[dict, Use(config)]):
    assert cfg["api_url"].startswith("https://")
```

## Run the Tests

```bash
protest run tests:session
```

The format is `module:session_variable`. ProTest imports the module and looks for the session.

You should see output like:

```
API
  ✓ test_config_has_url (0.00s)
  ✓ test_url_is_https (0.00s)

2 passed in 0.01s
```

## Add a Failing Test

Let's see what a failure looks like. Add this test:

```python
@api_suite.test()
async def test_intentional_failure(cfg: Annotated[dict, Use(config)]):
    assert cfg["api_url"] == "http://wrong.com"
```

Run again:

```bash
protest run tests:session
```

ProTest shows the assertion error with context.

## Run Tests in Parallel

For I/O-bound tests, parallelism can significantly speed things up:

```bash
protest run tests:session -n 4
```

This runs up to 4 tests concurrently.

## Next Steps

- [Running Tests](running-tests.md) - CLI options and configuration
- [Sessions & Suites](../core-concepts/sessions-and-suites.md) - Organizing tests
- [Fixtures](../core-concepts/fixtures.md) - Setup, teardown, and scopes
