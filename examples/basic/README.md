# ProTest Basic Examples

This directory contains basic examples demonstrating ProTest features.

## Setup

```bash
cd examples/basic
uv sync
```

## Running Tests

### Basic run (sequential)

```bash
# Run demo.py tests
uv run protest demo:session

# Run async demo
uv run protest demo_async:session

# Run capture demo (stdout/stderr capture)
uv run protest demo_capture:session

# Run factory demo
uv run protest factory_demo:session

# Run caplog demo (log capture)
uv run protest caplog_demo:session
```

### Parallel execution

```bash
# Run 4 tests concurrently
uv run protest demo:session -n 4

# Run 8 tests concurrently
uv run protest demo_async:session -n 8
```

### Re-run failed tests only (--lf)

```bash
# First run - some tests fail, results cached in .protest/cache.json
uv run protest demo:session

# Second run - only re-run failed tests
uv run protest demo:session --lf

# Combine with concurrency
uv run protest demo:session --lf -n 4
```

### Clear cache

```bash
# Clear cache before run (runs all tests)
uv run protest demo:session --cache-clear

# Clear cache + concurrency
uv run protest demo:session --cache-clear -n 4
```

### Collect only (list tests without running)

```bash
# List all tests
uv run protest demo:session --collect-only

# Combine with --lf to see which tests would run
uv run protest demo:session --lf --collect-only
```

### Combined options

```bash
# Clear cache, then run failed (effectively runs all since cache is cleared)
uv run protest demo:session --cache-clear --lf

# Typical workflow: first run all, then iterate on failures
uv run protest demo:session -n 4           # Run all
uv run protest demo:session --lf           # Fix failures, re-run only those
uv run protest demo:session --lf           # Keep iterating
uv run protest demo:session -n 4           # Final full run
```

## Demo Files

| File | Description |
|------|-------------|
| `demo.py` | Full feature showcase: fixtures, suites, scopes |
| `demo_async.py` | Async tests and fixtures |
| `demo_capture.py` | stdout/stderr capture during tests |
| `factory_demo.py` | Factory fixtures for dynamic instances |
| `caplog_demo.py` | Log capture fixture |
| `slack_notifier.py` | Example plugin (fake Slack notifications) |

## Cache Location

Test results are cached in `.protest/cache.json`. This file is used by `--lf` to determine which tests failed in the previous run.

```bash
# View cache contents
cat .protest/cache.json
```
