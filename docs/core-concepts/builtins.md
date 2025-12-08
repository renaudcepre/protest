# Built-in Fixtures

ProTest provides built-in fixtures for common testing needs. These are ready to use without any setup.

## caplog

Captures log records during a test.

```python
from typing import Annotated
from protest import ProTestSession, Use, caplog
from protest.entities import LogCapture
import logging

session = ProTestSession()

@session.test()
def test_logging(logs: Annotated[LogCapture, Use(caplog)]):
    logging.warning("Something happened")

    assert len(logs.records) == 1
    assert "Something happened" in logs.text
    assert logs.at_level("WARNING")[0].getMessage() == "Something happened"
```

### LogCapture API

| Property/Method | Description |
|-----------------|-------------|
| `records` | List of `LogRecord` objects |
| `text` | Formatted string of all logs |
| `at_level(level)` | Filter records at or above level |
| `clear()` | Clear captured records |

## mocker

Provides a clean mocking API with automatic cleanup. No more `with patch(...)` indentation hell.

```python
from typing import Annotated
from protest import ProTestSession, Use, Mocker, mocker

session = ProTestSession()

@session.test()
async def test_payment(m: Annotated[Mocker, Use(mocker)]):
    # Patch a function
    mock_stripe = m.patch("services.stripe.charge")
    mock_stripe.return_value = {"status": "success"}

    # Patch an object's method
    mock_email = m.patch.object(email_service, "send")

    await process_payment()

    mock_stripe.assert_called_once()
    mock_email.assert_called()
    # Automatic cleanup at test end - no stopall() needed
```

### Why mocker instead of unittest.mock?

**Problem 1: Indentation Hell**

```python
# Without mocker - nested context managers
def test_order():
    with patch("services.stripe.charge") as mock_charge:
        with patch("services.email.send") as mock_email:
            with patch("services.inventory.reserve") as mock_inventory:
                # Actual test buried here
                process_order()
```

**Problem 2: Decorator Conflicts**

`@patch` injects arguments positionally, which conflicts with ProTest's DI system:

```python
# DON'T DO THIS - will break
@patch("services.stripe.charge")
@session.test()
def test_order(mock_charge, db: Annotated[DB, Use(database)]):
    # Who injects what? Chaos.
    pass
```

**Solution: mocker fixture**

```python
# Clean, flat, explicit
@session.test()
def test_order(
    m: Annotated[Mocker, Use(mocker)],
    db: Annotated[DB, Use(database)]
):
    mock_charge = m.patch("services.stripe.charge")
    # ...
```

### Mocker API

#### Patching

| Method | Description |
|--------|-------------|
| `patch(target, **kwargs)` | Patch a module path string |
| `patch.object(obj, attr, **kwargs)` | Patch an attribute on an object |
| `patch.dict(d, values, clear=False)` | Patch a dictionary |

```python
# Patch a function
mock = m.patch("myapp.services.send_email")

# Patch a method on an instance
mock = m.patch.object(my_service, "fetch_data")

# Patch environment variables
m.patch.dict(os.environ, {"API_KEY": "test-key"})

# Patch and clear a dict
m.patch.dict(os.environ, {"ONLY_THIS": "value"}, clear=True)
```

#### Spying

`spy()` calls the **real method** but tracks all calls:

```python
@session.test()
def test_audit_logging(m: Annotated[Mocker, Use(mocker)]):
    # Modern style (recommended) - IDE-friendly, Ctrl+Click works
    spy = m.spy(audit_service.log_action)

    # Classic style - still supported
    # spy = m.spy(audit_service, "log_action")

    # Real log_action() is called
    process_user_action()

    # But we can verify it was called correctly
    spy.assert_called_once_with(action="login", user_id=42)

    # Access the actual return value
    assert spy.spy_return == {"logged": True}
```

#### Stubs

Quick callables for testing callbacks:

```python
@session.test()
def test_callback(m: Annotated[Mocker, Use(mocker)]):
    on_complete = m.stub("on_complete")
    on_complete.return_value = "done"

    run_job(callback=on_complete)

    on_complete.assert_called_once()

@session.test()
async def test_async_callback(m: Annotated[Mocker, Use(mocker)]):
    on_complete = m.async_stub("on_complete")

    await run_async_job(callback=on_complete)

    on_complete.assert_awaited_once()
```

#### Autospec

Create mocks that respect the original signature:

```python
@session.test()
def test_with_autospec(m: Annotated[Mocker, Use(mocker)]):
    mock_service = m.create_autospec(MyService, instance=True)
    mock_service.process.return_value = "result"

    # This works
    mock_service.process(data="test")

    # This raises TypeError - wrong signature!
    # mock_service.process(wrong_arg=123)
```

#### Control Methods

| Method | Description |
|--------|-------------|
| `stop(mock)` | Stop a specific patch |
| `stopall()` | Stop all patches (called automatically) |
| `resetall()` | Reset all mocks (clear call counts) |

```python
@session.test()
def test_phases(m: Annotated[Mocker, Use(mocker)]):
    mock = m.patch("myapp.external_api")

    # Phase 1
    mock.return_value = "phase1"
    do_something()
    mock.assert_called()

    # Reset for phase 2
    m.resetall()

    # Phase 2
    mock.return_value = "phase2"
    do_something_else()
    assert mock.call_count == 1  # Reset worked
```

### Type Hints

For better IDE support, use the exported type aliases:

```python
from protest import Mocker, MockType, AsyncMockType, Use, mocker

@session.test()
def test_typed(m: Annotated[Mocker, Use(mocker)]):
    mock: MockType = m.patch("myapp.service")
    async_mock: AsyncMockType = m.async_stub()
```
