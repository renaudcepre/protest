# Event Bus

The Event Bus decouples test execution from reporting and plugins. Components communicate through events without direct dependencies.

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
│  _handlers: dict[Event, list[Handler]]                          │
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

### `emit()` - Notifications

Used for events where handlers observe but don't modify data.

```python
await bus.emit(Event.TEST_PASS, result)
```

| Handler Type | Behavior                                            |
|--------------|-----------------------------------------------------|
| Sync         | Runs in threadpool, `emit()` waits for completion   |
| Async        | Fire-and-forget, `emit()` continues immediately     |

```
emit(TEST_PASS, result)
│
├─ sync handler 1 ────► threadpool, waits ⏳
├─ sync handler 2 ────► threadpool, waits ⏳
├─ async handler 1 ───► fire-and-forget 🔥
├─ async handler 2 ───► fire-and-forget 🔥
│
└─ returns (async handlers may still run)
```

Async handlers are tracked and waited on before `SESSION_COMPLETE`.

### `emit_and_collect()` - Pipeline

Used when handlers can transform data (e.g., filtering tests).

```python
filtered = await bus.emit_and_collect(Event.COLLECTION_FINISH, items)
```

- Handlers run **sequentially** (order matters)
- Each receives the previous handler's output
- Returning `None` passes data unchanged

```
emit_and_collect(COLLECTION_FINISH, items)
│
├─ TagFilter(items) ──────► filtered_1
├─ KeywordFilter(filtered_1) ► filtered_2
├─ CachePlugin(filtered_2) ──► filtered_3
│
└─ returns filtered_3
```

## Handler Types

### Sync Handlers

Run in the default threadpool to avoid blocking the event loop.

```python
def on_test_pass(self, result: TestResult) -> None:
    self.results.append(result)
```

Best for: quick operations, file writes, logging.

### Async Handlers

Run as background tasks. The bus doesn't wait for them.

```python
async def on_test_pass(self, result: TestResult) -> None:
    await self.send_webhook(result)
```

Best for: network I/O, long operations, parallel work.

## Error Handling

Handler exceptions are:

1. Logged (not silent)
2. **Not propagated** - other handlers continue
3. Reported via `HANDLER_END` event

A failing handler never breaks test execution.

## See Also

- [Events](events.md) - Complete event reference
- [Plugins](plugins.md) - Writing plugins
