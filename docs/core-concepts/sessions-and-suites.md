# Sessions & Suites

ProTest organizes tests in a hierarchy: **Session** → **Suites** → **Tests**.

## ProTestSession

A session is the root of your test hierarchy. You typically have one session per project, or one per major component in a monorepo.

```python
from protest import ProTestSession

session = ProTestSession()
```

### Session Options

```python
session = ProTestSession(
    concurrency=4,              # Default parallelism (overridden by -n)
    default_reporter=True,      # Use built-in Rich/ASCII reporter
    default_cache=True,         # Enable --lf support
)
```

### Session-Level Tests

You can register tests directly on the session:

```python
@session.test()
async def test_something():
    assert True
```

These tests don't belong to any suite.

## ProTestSuite

Suites group related tests together. They also define a scope boundary for fixtures.

```python
from protest import ProTestSuite

api_suite = ProTestSuite("API")
session.add_suite(api_suite)

@api_suite.test()
async def test_endpoint():
    assert True
```

### Suite Options

```python
api_suite = ProTestSuite(
    "API",
    max_concurrency=2,          # Cap parallelism for this suite
    tags=["integration"],       # Tags inherited by all tests in suite
)
```

## Nested Suites

Suites can contain other suites, creating a hierarchy:

```python
api_suite = ProTestSuite("API")
users_suite = ProTestSuite("Users")
orders_suite = ProTestSuite("Orders")

api_suite.add_suite(users_suite)
api_suite.add_suite(orders_suite)

session.add_suite(api_suite)
```

This creates the structure:

```
Session
└── API
    ├── Users
    └── Orders
```

### Full Path

Each suite has a `full_path` property showing its position in the hierarchy:

```python
users_suite.full_path  # "API::Users"
orders_suite.full_path # "API::Orders"
```

### Fixture Inheritance

Child suites can access fixtures from parent suites:

```python
@api_suite.fixture()
def api_client():
    return Client()

@users_suite.test()
async def test_get_user(client: Annotated[Client, Use(api_client)]):
    # api_client is available here because Users is inside API
    pass
```

## Execution Order

1. Session fixtures are resolved once at start
2. Suites run in registration order
3. Within each suite:
    - Suite fixtures are resolved once
    - Tests run (potentially in parallel)
    - Suite fixtures are torn down
4. Session fixtures are torn down at end

Teardown follows LIFO order: children before parents.
