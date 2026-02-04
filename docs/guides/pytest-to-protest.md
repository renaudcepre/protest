# Migrating from pytest to ProTest

This guide helps you migrate existing pytest test suites to ProTest. It covers the key conceptual differences and provides practical translation patterns.

## Philosophy Shift

| pytest | ProTest |
|--------|---------|
| Convention-based (discover `test_*.py`) | Explicit structure (Suites, Sessions) |
| Global fixtures via conftest.py | Explicit binding with `suite.bind()` |
| Implicit dependency injection | Explicit DI with `Annotated[T, Use(fixture)]` |
| Parametrize with `@pytest.mark.parametrize` | Parametrize with `ForEach` + `From` |
| Scope via `@pytest.fixture(scope=...)` | Scope via binding: `session.bind()` / `suite.bind()` |

## Quick Reference

### Test Definition

```python
# pytest
def test_something():
    assert 1 + 1 == 2

# ProTest
@suite.test()
def test_something():
    assert 1 + 1 == 2

# ProTest async (native support)
@suite.test()
async def test_something_async():
    result = await fetch_data()
    assert result is not None
```

### Fixtures

```python
# pytest - conftest.py
@pytest.fixture
def user():
    return User(name="test")

@pytest.fixture
def db():
    conn = connect()
    yield conn
    conn.close()

# pytest - test file
def test_user_in_db(user, db):
    db.save(user)
    assert db.find(user.id)
```

```python
# ProTest
from protest import fixture, Use
from typing import Annotated

@fixture()
def user():
    return User(name="test")

@fixture()
def db():
    conn = connect()
    yield conn  # teardown after yield
    conn.close()

# Bind to suite
suite.bind(user)
suite.bind(db)

# Explicit injection
@suite.test()
def test_user_in_db(
    u: Annotated[User, Use(user)],
    database: Annotated[Connection, Use(db)],
):
    database.save(u)
    assert database.find(u.id)
```

### Factories (Parametric Fixtures)

```python
# pytest - fixture with params
@pytest.fixture(params=["admin", "user", "guest"])
def role(request):
    return create_role(request.param)

# pytest - factory pattern
@pytest.fixture
def create_user():
    def _create(name, role="user"):
        return User(name=name, role=role)
    return _create

def test_user(create_user):
    admin = create_user("Alice", role="admin")
```

```python
# ProTest - factory pattern (native)
from protest import factory, FixtureFactory, Use

@factory()  # Creates FixtureFactory, not raw value
def user(name: str = "Test", role: str = "user"):
    return User(name=name, role=role)

suite.bind(user)

@suite.test()
async def test_user(
    user_factory: Annotated[FixtureFactory[User], Use(user)],
):
    # Factory is async - call it to create instances
    admin = await user_factory(name="Alice", role="admin")
    guest = await user_factory(role="guest")
```

### Parametrization

```python
# pytest
@pytest.mark.parametrize("x,y,expected", [
    (1, 2, 3),
    (2, 3, 5),
    (10, 20, 30),
])
def test_add(x, y, expected):
    assert x + y == expected

# pytest with ids
@pytest.mark.parametrize("input_file", [
    "data.json",
    "data.xml",
    "data.csv",
], ids=lambda x: x.split(".")[1])
def test_parse(input_file):
    parse(input_file)
```

```python
# ProTest
from protest import ForEach, From

ADD_CASES = ForEach(
    [(1, 2, 3), (2, 3, 5), (10, 20, 30)],
    ids=lambda t: f"{t[0]}+{t[1]}={t[2]}"
)

@suite.test()
def test_add(case: Annotated[tuple, From(ADD_CASES)]):
    x, y, expected = case
    assert x + y == expected

# Or with named parameters
INPUT_FILES = ForEach(
    ["data.json", "data.xml", "data.csv"],
    ids=lambda x: x.split(".")[1]
)

@suite.test()
def test_parse(input_file: Annotated[str, From(INPUT_FILES)]):
    parse(input_file)
```

### Fixture Scopes

```python
# pytest
@pytest.fixture(scope="session")
def expensive_resource():
    return load_heavy_data()

@pytest.fixture(scope="module")
def per_module_db():
    return create_db()

@pytest.fixture  # default: function scope
def per_test_data():
    return fresh_data()
```

```python
# ProTest - scope determined by binding
from protest import fixture, ProTestSession, ProTestSuite

session = ProTestSession()
suite = ProTestSuite("MyTests")

@fixture()
def expensive_resource():
    return load_heavy_data()

@fixture()
def per_suite_db():
    return create_db()

@fixture()  # default: TEST scope (no binding needed)
def per_test_data():
    return fresh_data()

# Scope is determined by WHERE you bind:
session.bind(expensive_resource)  # → SESSION scope
suite.bind(per_suite_db)          # → SUITE scope (equivalent to module)
# per_test_data not bound         # → TEST scope (default)
```

### Built-in Fixtures

```python
# pytest
def test_with_tmp(tmp_path):
    (tmp_path / "file.txt").write_text("hello")

def test_with_caplog(caplog):
    logging.warning("test")
    assert "test" in caplog.text

# pytest-mock plugin
def test_with_mock(mocker):
    m = mocker.patch("mymodule.func")
    m.return_value = 42
```

```python
# ProTest - built-ins
from protest import tmp_path, caplog, mocker, Mocker, Use
from protest.entities import LogCapture
from pathlib import Path

@suite.test()
def test_with_tmp(tmp: Annotated[Path, Use(tmp_path)]):
    (tmp / "file.txt").write_text("hello")

@suite.test()
def test_with_caplog(logs: Annotated[LogCapture, Use(caplog)]):
    logging.warning("test")
    assert "test" in logs.text

@suite.test()
def test_with_mock(m: Annotated[Mocker, Use(mocker)]):
    mock = m.patch("mymodule.func")
    mock.return_value = 42
```

### Skipping and Markers

```python
# pytest
@pytest.mark.skip(reason="not implemented")
def test_todo():
    pass

@pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
def test_unix_only():
    pass

@pytest.mark.slow
def test_slow_operation():
    pass
```

```python
# ProTest - use tags
@suite.test(skip="not implemented")
def test_todo():
    pass

@suite.test(tags=["slow"])
def test_slow_operation():
    pass

# Run filtered: protest run module:session --tags slow
# Exclude: protest run module:session --tags "not slow"
```

### Test Organization

```python
# pytest - file-based
# tests/
#   conftest.py
#   test_users.py
#   test_orders.py
#   integration/
#     conftest.py
#     test_api.py
```

```python
# ProTest - explicit suites
from protest import ProTestSession, ProTestSuite

# session.py
session = ProTestSession()

# Unit tests
users_suite = ProTestSuite("Users", tags=["unit"])
orders_suite = ProTestSuite("Orders", tags=["unit"])

# Integration tests
integration_suite = ProTestSuite("Integration", tags=["integration"])
api_suite = ProTestSuite("API", tags=["api"])
integration_suite.add_suite(api_suite)  # nested

# Register suites
session.add_suite(users_suite)
session.add_suite(orders_suite)
session.add_suite(integration_suite)
```

### Async Tests

```python
# pytest - requires pytest-asyncio
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await fetch_data()
    assert result

# pytest - async fixtures need plugin
@pytest.fixture
async def async_client():
    async with aiohttp.ClientSession() as session:
        yield session
```

```python
# ProTest - native async support
@suite.test()
async def test_async_operation():
    result = await fetch_data()
    assert result

# Async fixtures work naturally
@fixture()
async def async_client():
    async with aiohttp.ClientSession() as session:
        yield session
```

## Common Patterns

### Before: pytest with many fixtures

```python
# conftest.py
@pytest.fixture
def company():
    return Company(name="Acme")

@pytest.fixture
def user(company):
    return User(company=company)

@pytest.fixture
def order(user):
    return Order(user=user)

# test_orders.py
def test_order_total(order):
    order.add_item(Product(price=100))
    assert order.total == 100
```

### After: ProTest with factories

```python
# fixtures.py
@factory()
async def company(name: str = "Acme"):
    return Company(name=name)

@factory()
async def user(
    company_factory: Annotated[FixtureFactory[Company], Use(company)],
    role: str = "member",
):
    c = await company_factory()
    return User(company=c, role=role)

@factory()
async def order(
    user_factory: Annotated[FixtureFactory[User], Use(user)],
):
    u = await user_factory()
    return Order(user=u)

# suite.py
suite.bind(company)
suite.bind(user)
suite.bind(order)

@suite.test()
async def test_order_total(
    order_factory: Annotated[FixtureFactory[Order], Use(order)],
):
    o = await order_factory()
    o.add_item(Product(price=100))
    assert o.total == 100
```

### MagicMock vs mocker

```python
# OK in ProTest - creating a mock to pass as argument
from unittest.mock import MagicMock

@suite.test()
def test_with_mock_arg():
    mock_service = MagicMock()
    mock_service.process.return_value = "ok"

    result = handler(service=mock_service)  # Passing mock
    assert result == "ok"

# Better for patching - use mocker built-in
@suite.test()
def test_with_patch(m: Annotated[Mocker, Use(mocker)]):
    mock = m.patch("myapp.external_service.call")
    mock.return_value = "ok"

    result = handler()  # Uses patched module
    assert result == "ok"
```

## Running Tests

```bash
# pytest
pytest tests/
pytest tests/test_users.py
pytest tests/test_users.py::test_create_user
pytest -k "user and not slow"
pytest --lf  # last failed

# ProTest
protest run myapp.tests.session:session
protest run myapp.tests.session:session --suite Users
protest run myapp.tests.session:session --tags "unit and not slow"
protest run myapp.tests.session:session --lf
```

## Migration Checklist

1. **Create a session file** with `ProTestSession()`
2. **Convert fixtures to ProTest syntax** (`@fixture()`, `@factory()`)
3. **Create suites** to group related tests
4. **Bind fixtures** to suites with appropriate scopes
5. **Convert test functions** with explicit `Annotated[T, Use(fixture)]`
6. **Replace `@pytest.mark.parametrize`** with `ForEach` + `From`
7. **Replace built-ins** (`tmp_path`, `caplog`, `mocker`)
8. **Update CI/CD** to use `protest run` command
