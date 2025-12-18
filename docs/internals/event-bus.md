# Event Bus

The Event Bus is ProTest's central communication mechanism. It decouples test execution
from reporting, filtering, and plugins.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         TestRunner                              │
│  emit(TEST_PASS, result)                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                          EventBus                               │
│                                                                 │
│  _handlers: dict[Event, list[_RegisteredHandler]]               │
│  _pending_tasks: set[asyncio.Task]                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         ┌────────┐    ┌────────┐    ┌────────┐
         │Reporter│    │ Cache  │    │  CTRF  │
         │Plugin  │    │Plugin  │    │Reporter│
         └────────┘    └────────┘    └────────┘
```

**Key files:**

- `protest/events/bus.py` - EventBus implementation
- `protest/events/types.py` - Event enum
- `protest/plugin.py` - PluginBase class

## Two Emission Patterns

### `emit()` - Fire-and-Forget

Used for notifications where handlers don't modify data.

```python
await bus.emit(Event.TEST_PASS, result)
```

**Behavior:**

| Handler Type | Execution                                                        |
|--------------|------------------------------------------------------------------|
| Sync         | Runs in threadpool, `emit()` **waits** for completion            |
| Async        | Runs as background task, `emit()` **continues** without waiting  |

```
emit(TEST_PASS, result)
│
├─ sync handler 1 ────► runs in threadpool, emit() waits ⏳
├─ sync handler 2 ────► runs in threadpool, emit() waits ⏳
├─ async handler 1 ───► fire-and-forget 🔥
├─ async handler 2 ───► fire-and-forget 🔥
│
└─ emit() returns (async handlers may still be running)
```

Async handlers are tracked in `_pending_tasks`. Call `wait_pending()` before session end
to ensure all handlers complete.

### `emit_and_collect()` - Chained Pipeline

Used when handlers can modify data (e.g., filtering test collection).

```python
filtered_items = await bus.emit_and_collect(Event.COLLECTION_FINISH, items)
```

**Behavior:**

- All handlers run **sequentially** (sync and async)
- Each handler receives the previous handler's output
- Returning `None` passes data unchanged
- Exceptions are logged but don't break the chain

```
emit_and_collect(COLLECTION_FINISH, items)
│
├─ TagFilter(items) ──────► returns filtered_1
├─ KeywordFilter(filtered_1) ► returns filtered_2
├─ CachePlugin(filtered_2) ──► returns filtered_3
│
└─ returns filtered_3
```

## Event Types

Events are defined in `protest/events/types.py`:

### Session Lifecycle

| Event                 | Data                    | When                                    |
|-----------------------|-------------------------|-----------------------------------------|
| `COLLECTION_FINISH`   | `list[TestItem]`        | After test collection, before execution |
| `SESSION_START`       | None                    | Before any test runs                    |
| `SESSION_END`         | `SessionResult`         | After all tests, teardown complete      |
| `SESSION_COMPLETE`    | `SessionResult`         | After `wait_pending()`                  |
| `SESSION_INTERRUPTED` | `bool` (force_teardown) | On Ctrl+C                               |

### Suite Lifecycle

| Event         | Data               | When                               |
|---------------|--------------------|------------------------------------|
| `SUITE_START` | `str` (suite_path) | Before suite's first test          |
| `SUITE_END`   | `SuiteResult`      | After suite's last test + teardown |

### Test Lifecycle

| Event                 | Data               | When                                     |
|-----------------------|--------------------|------------------------------------------|
| `TEST_START`          | `TestStartInfo`    | Test queued for execution                |
| `TEST_ACQUIRED`       | `TestStartInfo`    | Test acquired execution slot             |
| `TEST_SETUP_DONE`     | `TestStartInfo`    | Fixtures resolved, before test body      |
| `TEST_TEARDOWN_START` | `TestTeardownInfo` | After test body, before fixture teardown |
| `TEST_RETRY`          | `TestRetryInfo`    | Test failed, will retry                  |

### Test Outcomes

| Event        | Data         | When                                       |
|--------------|--------------|--------------------------------------------|
| `TEST_PASS`  | `TestResult` | Test passed                                |
| `TEST_FAIL`  | `TestResult` | Test failed                                |
| `TEST_SKIP`  | `TestResult` | Test skipped                               |
| `TEST_XFAIL` | `TestResult` | Expected failure (test failed as expected) |
| `TEST_XPASS` | `TestResult` | Unexpected pass (xfail test passed)        |

### Fixture Lifecycle

| Event                    | Data          | When                    |
|--------------------------|---------------|-------------------------|
| `FIXTURE_SETUP_START`    | `FixtureInfo` | Before fixture setup    |
| `FIXTURE_SETUP_DONE`     | `FixtureInfo` | After fixture setup     |
| `FIXTURE_TEARDOWN_START` | `FixtureInfo` | Before fixture teardown |
| `FIXTURE_TEARDOWN_DONE`  | `FixtureInfo` | After fixture teardown  |

### Meta Events

| Event              | Data          | When                       |
|--------------------|---------------|----------------------------|
| `HANDLER_START`    | `HandlerInfo` | Before a handler executes  |
| `HANDLER_END`      | `HandlerInfo` | After a handler completes  |
| `WAITING_HANDLERS` | `int` (count) | Waiting for async handlers |

## Event Sequence

Typical test run sequence:

```
COLLECTION_FINISH (emit_and_collect)
SESSION_START
│
│  ┌─────────────────────────────────────── for each session-scoped fixture
│  │ FIXTURE_SETUP_START (scope=session)
│  │ FIXTURE_SETUP_DONE (scope=session)
│  └───────────────────────────────────────
│
├─ SUITE_START ("API") ◄─────────────────── for each suite
│  │
│  │  ┌──────────────────────────────────── for each suite-scoped fixture
│  │  │ FIXTURE_SETUP_START (scope=suite)
│  │  │ FIXTURE_SETUP_DONE (scope=suite)
│  │  └────────────────────────────────────
│  │
│  ├─ TEST_START ◄───────────────────────── for each test in suite
│  │  │ TEST_ACQUIRED
│  │  │  ┌───────────────────────────────── for each test-scoped fixture
│  │  │  │ FIXTURE_SETUP_START (scope=test)
│  │  │  │ FIXTURE_SETUP_DONE (scope=test)
│  │  │  └─────────────────────────────────
│  │  │ TEST_SETUP_DONE
│  │  │ ... test body runs ...
│  │  │ TEST_TEARDOWN_START
│  │  │  ┌───────────────────────────────── for each test-scoped fixture (LIFO)
│  │  │  │ FIXTURE_TEARDOWN_START (scope=test)
│  │  │  │ FIXTURE_TEARDOWN_DONE (scope=test)
│  │  │  └─────────────────────────────────
│  │  └─ TEST_PASS / TEST_FAIL / TEST_SKIP
│  │
│  │  ┌──────────────────────────────────── for each suite-scoped fixture (LIFO)
│  │  │ FIXTURE_TEARDOWN_START (scope=suite)
│  │  │ FIXTURE_TEARDOWN_DONE (scope=suite)
│  │  └────────────────────────────────────
│  └─ SUITE_END
│
│  ┌─────────────────────────────────────── for each session-scoped fixture (LIFO)
│  │ FIXTURE_TEARDOWN_START (scope=session)
│  │ FIXTURE_TEARDOWN_DONE (scope=session)
│  └───────────────────────────────────────
│
SESSION_END
WAITING_HANDLERS (if async handlers pending)
SESSION_COMPLETE
```

**Notes:**

- Fixture teardown is LIFO (last setup = first teardown)
- Tests may run in parallel within/across suites (events interleaved)
- Suite fixtures teardown when **all** tests in that suite complete
- Non-autouse session/suite fixtures are setup on first use (during TEST_ACQUIRED of the first test that needs them), then cached

## Writing a Plugin

Plugins extend `PluginBase` and implement event handlers:

```python
from protest.plugin import PluginBase, PluginContext
from protest.entities import TestResult, SessionResult


class MyPlugin(PluginBase):
    name = "my-plugin"
    description = "Does something useful"

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.results: list[TestResult] = []

    # CLI integration
    @classmethod
    def add_cli_options(cls, parser):
        group = parser.add_argument_group("My Plugin")
        group.add_argument("--my-output", help="Output file path")

    @classmethod
    def activate(cls, ctx: PluginContext):
        output = ctx.get("my_output")
        if not output:
            return None  # Don't activate
        return cls(output_path=output)

    # Event handlers (sync or async)
    def on_test_pass(self, result: TestResult) -> None:
        self.results.append(result)

    def on_test_fail(self, result: TestResult) -> None:
        self.results.append(result)

    def on_session_complete(self, result: SessionResult) -> None:
        # Write report after all async handlers finished
        with open(self.output_path, "w") as f:
            f.write(f"Total: {len(self.results)} tests")
```

### Handler Signatures

Handlers can be sync or async. Return type is typically `None`, except for
`COLLECTION_FINISH`:

```python
# Sync handler
def on_test_pass(self, result: TestResult) -> None:
    print(f"PASS: {result.name}")


# Async handler
async def on_test_pass(self, result: TestResult) -> None:
    await self.send_notification(result)


# Collection filter (returns modified list)
def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
    return [item for item in items if "slow" not in item.tags]
```

### Registration

Plugins are wired to the EventBus in `ProTestSession.register_plugin()`:

```python
def register_plugin(self, plugin: PluginBase) -> None:
    if hasattr(plugin, "setup") and callable(plugin.setup):
        plugin.setup(self)

    for event in Event:
        method_name = f"on_{event.value}"
        handler = getattr(plugin, method_name, None)
        if handler and callable(handler):
            self._events.on(event, handler)
```

## Implementation Details

### Thread Safety

- Sync handlers run in the default thread pool via `run_in_threadpool()`
- Async handlers run as fire-and-forget tasks
- `_pending_tasks` is a set of active async tasks
- Handler registration/unregistration is not thread-safe (done at startup)

### Error Handling

Handler exceptions are:

1. Logged via `logger.exception()`
2. **Not propagated** - other handlers continue
3. Reported in `HANDLER_END` event's `HandlerInfo.error`

```python
try:
    await run_in_threadpool(handler, data)
except Exception as exc:
    logger.exception("Handler %s failed", handler_name)
    await self._emit_handler_end(handler_name, event, False, duration, exc)
```

### HANDLER_START/END Recursion Prevention

Meta-events (`HANDLER_START`, `HANDLER_END`) don't trigger themselves:

```python
async def _emit_handler_start(self, name: str, event: Event, is_async: bool) -> None:
    """Emit HANDLER_START without triggering handler events (avoid recursion)."""
    info = HandlerInfo(name=name, event=event, is_async=is_async)
    # Direct iteration, no emit() call
    for registered in self._handlers[Event.HANDLER_START]:
# ...
```

### Waiting for Async Handlers

Before session end, call `wait_pending()` to ensure all async handlers complete:

```python
if self._session.events.pending_count > 0:
    await self._session.events.emit(Event.WAITING_HANDLERS, pending_count)
await self._session.events.wait_pending()
await self._session.events.emit(Event.SESSION_COMPLETE, result)
```

## Best Practices

### Do

- Use `on_session_complete` for final reports (all async handlers done)
- Keep sync handlers fast (they block the event loop indirectly)
- Use async handlers for I/O-heavy operations
- Return `None` from `on_collection_finish` if not modifying items

### Don't

- Don't assume handler execution order between plugins
- Don't rely on async handlers completing before `SESSION_END`
- Don't raise exceptions to stop test execution (use `exitfirst` option instead)
- Don't modify shared state without locks in async handlers

### Choosing Sync vs Async

| Use Sync When              | Use Async When                      |
|----------------------------|-------------------------------------|
| Quick in-memory operations | Network I/O (HTTP, DB)              |
| File writes (fast)         | Long-running operations             |
| Logging                    | Operations that can run in parallel |

## Data Classes

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
