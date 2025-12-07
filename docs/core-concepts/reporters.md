# Reporters

ProTest adapts its output automatically based on your environment.

## Display Modes

| Mode | When | Description |
|------|------|-------------|
| **Live** | Interactive terminal | Spinners, real-time updates, parallel test phases |
| **Rich** | CI, pipe, file | Colors, sequential output (no cursor manipulation) |
| **ASCII** | NO_COLOR, TERM=dumb | Plain text, no dependencies |

## Automatic Detection

ProTest automatically selects the best reporter:

1. `NO_COLOR=1` → ASCII (respects the standard)
2. `TERM=dumb` → ASCII
3. Rich not installed → ASCII
4. `CI=true` → Rich (colors, no cursor manipulation)
5. Interactive terminal → Live
6. Pipe/file → Rich

## Force a Mode

```bash
# Force live mode (interactive terminal only)
protest run demo:session --live

# Force sequential mode (CI/logs)
protest run demo:session --no-live

# Disable colors
protest run demo:session --no-color
```

## Environment Variables

| Variable | Effect |
|----------|--------|
| `NO_COLOR=1` | Disables all colors |
| `CI=true` | Disables live mode (cursor manipulation) |
| `TERM=dumb` | Forces ASCII mode |

## Live Mode Features

When running in Live mode, you get:

- **Real-time test phases**: See tests progress through `waiting` → `setup` → `running` → `teardown`
- **Spinner animations**: Visual feedback for running tests
- **Log streaming**: Last log message displayed next to running tests
- **Suite teardown tracking**: See when suite fixtures are being torn down
- **Live summary line**: Current pass/fail counts updated in real-time

## Programmatic Usage

```python
from protest.api import run_session
from protest import ProTestSession

session = ProTestSession()

# Force a specific reporter mode
run_session(
    session,
    force_live=True,      # Force live mode
    force_no_live=True,   # Force sequential mode
    force_no_color=True,  # Force ASCII mode
)
```

## Custom Reporters

You can create custom reporters by implementing the `PluginBase` interface:

```python
from protest.plugin import PluginBase
from protest.entities import TestResult, SessionResult

class MyReporter(PluginBase):
    def on_test_pass(self, result: TestResult) -> None:
        print(f"PASS: {result.name}")

    def on_test_fail(self, result: TestResult) -> None:
        print(f"FAIL: {result.name} - {result.error}")

    def on_session_complete(self, result: SessionResult) -> None:
        print(f"Done: {result.passed} passed, {result.failed} failed")

# Use your custom reporter
session = ProTestSession(default_reporter=False)
session.use(MyReporter())
```
