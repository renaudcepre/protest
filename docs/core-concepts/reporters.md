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
# Disable colors (forces ASCII mode)
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

# Force ASCII mode (no colors)
run_session(
    session,
    force_no_color=True,
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

## CTRF Reporter (CI/CD Integration)

ProTest includes a built-in [CTRF](https://ctrf.io) (Common Test Report Format) reporter for CI/CD integration. CTRF is a standardized JSON format supported by GitHub Actions, Slack, Jenkins, and other tools.

### Usage

```bash
# Generate CTRF report
protest run tests:session --ctrf-output ctrf-report.json

# Combine with parallel execution
protest run tests:session -n 4 --ctrf-output ctrf-report.json
```

### Output Format

The report includes:

- **Summary**: Test counts, duration, timestamps
- **Tests**: Name, status, duration, error messages, stack traces
- **Environment**: OS platform, git branch, commit SHA

### Example Output

```json
{
  "reportFormat": "CTRF",
  "specVersion": "0.0.0",
  "results": {
    "tool": { "name": "ProTest", "version": "0.1.0" },
    "summary": {
      "tests": 10,
      "passed": 8,
      "failed": 2,
      "skipped": 0,
      "pending": 0,
      "other": 0,
      "start": 1733754600000,
      "stop": 1733754605000
    },
    "tests": [
      {
        "name": "test_login",
        "status": "passed",
        "duration": 150,
        "suite": ["API", "Auth"]
      },
      {
        "name": "test_invalid_token",
        "status": "failed",
        "duration": 50,
        "message": "AssertionError: Expected 401",
        "trace": "Traceback ..."
      }
    ],
    "environment": {
      "osPlatform": "linux",
      "branchName": "main",
      "commit": "abc123"
    }
  }
}
```

### Status Mapping

| ProTest Status | CTRF Status | rawStatus |
|---------------|-------------|-----------|
| passed | `passed` | - |
| failed | `failed` | - |
| skipped | `skipped` | - |
| xfail | `failed` | `xfail` |
| xpass | `failed` | `xpass` |
| fixture error | `failed` | `error` |
| timeout | `failed` | `timeout` |

### Programmatic Usage

```python
from pathlib import Path
from protest.reporting.ctrf import CTRFReporter

session = ProTestSession()
session.use(CTRFReporter(output_path=Path("ctrf-report.json")))
```
