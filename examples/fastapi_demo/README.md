# ProTest FastAPI Demo

This example demonstrates testing a FastAPI application with ProTest, showcasing async tests and parallel HTTP calls.

## Setup

```bash
cd examples/fastapi_demo
uv sync
```

## Running Tests

### Basic run (sequential)

```bash
uv run protest run tests:session
```

### Parallel execution

This is where ProTest shines for async tests. The demo has tests that make HTTP calls with simulated latency.

```bash
# Run 4 tests concurrently - much faster for I/O bound tests
uv run protest run tests:session -n 4

# Run 8 tests concurrently
uv run protest run tests:session -n 8
```

**Why parallel matters here:**
- `test_slow_1`, `test_slow_2`, `test_slow_3`, `test_slow_4` each take ~100ms
- Sequential: ~400ms
- With `-n 4`: ~100ms (4x faster!)

### Re-run failed tests only (--lf)

```bash
# First run
uv run protest run tests:session -n 4

# Re-run only failed tests
uv run protest run tests:session --lf

# Combine with concurrency
uv run protest run tests:session --lf -n 4
```

### Clear cache

```bash
uv run protest run tests:session --cache-clear
```

### Collect only (list tests without running)

```bash
# See all tests
uv run protest run tests:session --collect-only

# See which tests would run with --lf
uv run protest run tests:session --lf --collect-only
```

### Combined options

```bash
# Typical workflow for FastAPI testing
uv run protest run tests:session -n 4                    # Run all in parallel
uv run protest run tests:session --lf -n 4               # Iterate on failures
uv run protest run tests:session --collect-only --lf     # Check what would run
uv run protest run tests:session --cache-clear -n 4      # Fresh run
```

## Demo Files

| File | Description |
|------|-------------|
| `app.py` | Simple FastAPI app with users, products, health endpoints |
| `tests.py` | Async tests using httpx.AsyncClient |

## Key Features Demonstrated

1. **Async fixtures**: `async_client` is an async generator fixture
2. **Parallel HTTP calls**: Tests use `asyncio.gather` for concurrent requests
3. **Mixed sync/async**: `test_sync_for_comparison` shows sync tests work too
4. **ASGI transport**: Uses `httpx.ASGITransport` for in-process testing (no actual HTTP)

## Performance Comparison

```bash
# Sequential (default)
uv run protest run tests:session
# Total time: ~2s

# Parallel with -n 4
uv run protest run tests:session -n 4
# Total time: ~0.5s
```
