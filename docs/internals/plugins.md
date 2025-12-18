# Plugins

Plugins extend ProTest by reacting to events. They can report results, filter tests, cache data, or integrate with external systems.

## PluginBase

All plugins extend `PluginBase` from `protest/plugin.py`:

```python
from protest.plugin import PluginBase, PluginContext
from protest.entities import TestResult, SessionResult


class MyPlugin(PluginBase):
    name = "my-plugin"
    description = "Does something useful"

    def __init__(self, output_path: str):
        self.output_path = output_path
        self.results: list[TestResult] = []

    def on_test_pass(self, result: TestResult) -> None:
        self.results.append(result)

    def on_session_complete(self, result: SessionResult) -> None:
        with open(self.output_path, "w") as f:
            f.write(f"Total: {len(self.results)} tests")
```

## CLI Integration

Plugins can add CLI options and conditionally activate:

```python
class CTRFPlugin(PluginBase):
    name = "ctrf"
    description = "CTRF JSON reporter"

    def __init__(self, output_path: str):
        self.output_path = output_path

    @classmethod
    def add_cli_options(cls, parser):
        group = parser.add_argument_group("CTRF Reporter")
        group.add_argument(
            "--ctrf-output",
            metavar="PATH",
            help="Write CTRF JSON report to PATH"
        )

    @classmethod
    def activate(cls, ctx: PluginContext):
        output = ctx.get("ctrf_output")
        if not output:
            return None  # Don't activate
        return cls(output_path=output)
```

### PluginContext

`PluginContext` provides access to CLI args and programmatic config:

```python
@classmethod
def activate(cls, ctx: PluginContext):
    # Get value with default
    verbose = ctx.get("verbose", False)

    # Check if option was provided
    if "output" in ctx:
        return cls(output=ctx.get("output"))

    return None
```

## Handler Methods

Handlers are methods named `on_{event_name}`. They can be sync or async:

```python
# Sync - runs in threadpool
def on_test_pass(self, result: TestResult) -> None:
    print(f"PASS: {result.name}")

# Async - fire-and-forget
async def on_test_pass(self, result: TestResult) -> None:
    await self.send_webhook(result)
```

### Available Handlers

| Handler                     | Data               | Notes                          |
|-----------------------------|--------------------|--------------------------------|
| `on_collection_finish`      | `list[TestItem]`   | Can filter/sort, return list   |
| `on_session_start`          | None               |                                |
| `on_session_setup_done`     | `SessionSetupInfo` |                                |
| `on_session_teardown_start` | None               |                                |
| `on_session_end`            | `SessionResult`    |                                |
| `on_session_complete`       | `SessionResult`    | After async handlers done      |
| `on_suite_start`            | `str`              | suite_path                     |
| `on_suite_setup_done`       | `SuiteSetupInfo`   |                                |
| `on_suite_teardown_start`   | `str`              | suite_path                     |
| `on_suite_end`              | `SuiteResult`      |                                |
| `on_test_start`             | `TestStartInfo`    |                                |
| `on_test_acquired`          | `TestStartInfo`    |                                |
| `on_test_setup_done`        | `TestStartInfo`    |                                |
| `on_test_teardown_start`    | `TestTeardownInfo` |                                |
| `on_test_retry`             | `TestRetryInfo`    |                                |
| `on_test_pass`              | `TestResult`       |                                |
| `on_test_fail`              | `TestResult`       |                                |
| `on_test_skip`              | `TestResult`       |                                |
| `on_test_xfail`             | `TestResult`       |                                |
| `on_test_xpass`             | `TestResult`       |                                |
| `on_fixture_setup_start`    | `FixtureInfo`      |                                |
| `on_fixture_setup_done`     | `FixtureInfo`      |                                |
| `on_fixture_teardown_start` | `FixtureInfo`      |                                |
| `on_fixture_teardown_done`  | `FixtureInfo`      |                                |
| `on_session_interrupted`    | `bool`             | force_teardown flag            |

### Collection Filter

`on_collection_finish` can filter or reorder tests:

```python
def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
    # Filter out slow tests
    return [item for item in items if "slow" not in item.tags]
```

Return `None` or the original list to pass through unchanged.

## Setup Hook

`setup()` is called when the plugin is registered, before any events:

```python
def setup(self, session: ProTestSession) -> None:
    # Access session config
    self.concurrency = session.concurrency

    # Access shared cache
    self.cache = session.cache
```

## Registering Plugins

### Programmatic

```python
session = ProTestSession()
session.register_plugin(MyPlugin(output="report.json"))
```

### Via CLI

Plugins with `add_cli_options` are automatically discovered and their options added to `--help`.

## Best Practices

### Do

- Use `on_session_complete` for final reports (all async work done)
- Keep sync handlers fast
- Use async for network I/O
- Return `None` from `on_collection_finish` if not filtering

### Don't

- Don't assume handler order between plugins
- Don't raise exceptions to control flow
- Don't modify shared state without locks in async handlers

### Sync vs Async

| Use Sync                   | Use Async                     |
|----------------------------|-------------------------------|
| Quick in-memory operations | Network I/O (HTTP, webhooks)  |
| File writes                | Long-running operations       |
| Logging, printing          | Parallel work                 |

## See Also

- [Event Bus](event-bus.md) - Bus architecture
- [Events](events.md) - Complete event reference
