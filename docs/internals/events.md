# Events

All events emitted during test execution. Events are defined in `protest/events/types.py`.

## Session Lifecycle

| Event                    | Data                    | When                                      |
|--------------------------|-------------------------|-------------------------------------------|
| `COLLECTION_FINISH`      | `list[TestItem]`        | After collection, before execution        |
| `SESSION_START`          | None                    | Before any test runs                      |
| `SESSION_SETUP_DONE`     | `SessionSetupInfo`      | After session fixtures resolved           |
| `SESSION_TEARDOWN_START` | None                    | Before session fixture teardown           |
| `SESSION_END`            | `SessionResult`         | After teardown complete                   |
| `SESSION_COMPLETE`       | `SessionResult`         | After all async handlers finished         |
| `SESSION_INTERRUPTED`    | `bool` (force_teardown) | On Ctrl+C                                 |

## Suite Lifecycle

| Event                  | Data               | When                                   |
|------------------------|--------------------|----------------------------------------|
| `SUITE_START`          | `SuiteStartInfo`   | Before suite's first test              |
| `SUITE_SETUP_DONE`     | `SuiteSetupInfo`   | After suite fixtures resolved          |
| `SUITE_TEARDOWN_START` | `str` (suite_path) | Before suite fixture teardown          |
| `SUITE_END`            | `SuiteResult`      | After teardown complete                |

## Test Lifecycle

| Event                 | Data               | When                                 |
|-----------------------|--------------------|--------------------------------------|
| `TEST_START`          | `TestStartInfo`    | Test queued for execution            |
| `TEST_ACQUIRED`       | `TestStartInfo`    | Test acquired execution slot         |
| `TEST_SETUP_DONE`     | `TestStartInfo`    | Fixtures resolved, before test body  |
| `TEST_TEARDOWN_START` | `TestTeardownInfo` | After test body, before teardown     |
| `TEST_RETRY`          | `TestRetryInfo`    | Test failed, will retry              |

## Test Outcomes

| Event        | Data         | When                          |
|--------------|--------------|-------------------------------|
| `TEST_PASS`  | `TestResult` | Test passed                   |
| `TEST_FAIL`  | `TestResult` | Test failed                   |
| `TEST_SKIP`  | `TestResult` | Test skipped                  |
| `TEST_XFAIL` | `TestResult` | Expected failure              |
| `TEST_XPASS` | `TestResult` | Unexpected pass (xfail test)  |

## Fixture Lifecycle

| Event                    | Data          | When                    |
|--------------------------|---------------|-------------------------|
| `FIXTURE_SETUP_START`    | `FixtureInfo` | Before fixture setup    |
| `FIXTURE_SETUP_DONE`     | `FixtureInfo` | After fixture setup     |
| `FIXTURE_TEARDOWN_START` | `FixtureInfo` | Before fixture teardown |
| `FIXTURE_TEARDOWN_DONE`  | `FixtureInfo` | After fixture teardown  |

## Meta Events

| Event              | Data          | When                      |
|--------------------|---------------|---------------------------|
| `HANDLER_START`    | `HandlerInfo` | Before handler executes   |
| `HANDLER_END`      | `HandlerInfo` | After handler completes   |
| `WAITING_HANDLERS` | `int` (count) | Waiting for async handlers|

## Event Sequence

```
COLLECTION_FINISH (emit_and_collect)
SESSION_START
│
│  ┌─────────────────────────────────────── for each session fixture
│  │ FIXTURE_SETUP_START (scope=session)
│  │ FIXTURE_SETUP_DONE (scope=session)
│  └───────────────────────────────────────
│
SESSION_SETUP_DONE
│
├─ SUITE_START ("API") ◄─────────────────── for each suite
│  │
│  │  ┌──────────────────────────────────── for each suite fixture
│  │  │ FIXTURE_SETUP_START (scope=suite)
│  │  │ FIXTURE_SETUP_DONE (scope=suite)
│  │  └────────────────────────────────────
│  │
│  │ SUITE_SETUP_DONE
│  │
│  ├─ TEST_START ◄───────────────────────── for each test
│  │  │ TEST_ACQUIRED
│  │  │  ┌───────────────────────────────── for each test fixture
│  │  │  │ FIXTURE_SETUP_START (scope=test)
│  │  │  │ FIXTURE_SETUP_DONE (scope=test)
│  │  │  └─────────────────────────────────
│  │  │ TEST_SETUP_DONE
│  │  │ ... test body ...
│  │  │ TEST_TEARDOWN_START
│  │  │  ┌───────────────────────────────── for each test fixture (LIFO)
│  │  │  │ FIXTURE_TEARDOWN_START
│  │  │  │ FIXTURE_TEARDOWN_DONE
│  │  │  └─────────────────────────────────
│  │  └─ TEST_PASS / TEST_FAIL / TEST_SKIP
│  │
│  │ SUITE_TEARDOWN_START
│  │  ┌──────────────────────────────────── for each suite fixture (LIFO)
│  │  │ FIXTURE_TEARDOWN_START
│  │  │ FIXTURE_TEARDOWN_DONE
│  │  └────────────────────────────────────
│  └─ SUITE_END
│
SESSION_TEARDOWN_START
│  ┌─────────────────────────────────────── for each session fixture (LIFO)
│  │ FIXTURE_TEARDOWN_START
│  │ FIXTURE_TEARDOWN_DONE
│  └───────────────────────────────────────
│
SESSION_END
WAITING_HANDLERS (if pending)
SESSION_COMPLETE
```

**Notes:**

- Fixture teardown is LIFO (last setup = first teardown)
- Tests may run in parallel (events interleaved)
- Non-autouse fixtures are setup on first use, then cached

## Data Classes

All defined in `protest/entities/events.py`.

### TestResult

```python
@dataclass(frozen=True, slots=True)
class TestResult:
    name: str
    node_id: str = ""
    suite_path: str | None = None
    error: Exception | None = None
    duration: float = 0
    output: str = ""
    is_fixture_error: bool = False
    skip_reason: str | None = None
    xfail_reason: str | None = None
    timeout: float | None = None
    attempt: int = 1
    max_attempts: int = 1
    previous_errors: tuple[Exception, ...] = ()
```

### SessionResult

```python
@dataclass(frozen=True, slots=True)
class SessionResult:
    passed: int
    failed: int
    errors: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration: float = 0
    setup_duration: float = 0
    teardown_duration: float = 0
    interrupted: bool = False
```

### SuiteResult

```python
@dataclass(frozen=True, slots=True)
class SuiteResult:
    name: str
    duration: float = 0
    setup_duration: float = 0
    teardown_duration: float = 0
```

### SessionSetupInfo

```python
@dataclass(frozen=True, slots=True)
class SessionSetupInfo:
    duration: float
```

### SuiteSetupInfo

```python
@dataclass(frozen=True, slots=True)
class SuiteSetupInfo:
    name: str
    duration: float
```

### TestStartInfo

```python
@dataclass(frozen=True, slots=True)
class TestStartInfo:
    name: str
    node_id: str
```

### TestTeardownInfo

```python
@dataclass(frozen=True, slots=True)
class TestTeardownInfo:
    name: str
    node_id: str
    outcome: Event  # TEST_PASS, TEST_FAIL, etc.
```

### TestRetryInfo

```python
@dataclass(frozen=True, slots=True)
class TestRetryInfo:
    name: str
    node_id: str
    suite_path: str | None
    attempt: int
    max_attempts: int
    error: Exception
    delay: float
```

### FixtureInfo

```python
@dataclass(frozen=True, slots=True)
class FixtureInfo:
    name: str
    scope: FixtureScope  # SESSION, SUITE, TEST
    scope_path: str | None = None
    duration: float = 0
    autouse: bool = False
```

### HandlerInfo

```python
@dataclass(frozen=True, slots=True)
class HandlerInfo:
    name: str
    event: Event
    is_async: bool
    duration: float = 0
    error: Exception | None = None
```

## See Also

- [Event Bus](event-bus.md) - Bus architecture
- [Plugins](plugins.md) - Writing plugins
