# Running Tests

## Basic Command

```bash
protest run <module>:<session>
```

- `<module>` - Python module path (e.g., `tests`, `myapp.tests`)
- `<session>` - Name of the `ProTestSession` variable in that module

## Filtering Tests

ProTest provides multiple ways to filter which tests run. All filters can be combined.

### By Suite

Run only tests in a specific suite using `::SuiteName` syntax:

```bash
# Run tests in the "API" suite (and its children)
protest run tests:session::API

# Run tests in the nested "Users" suite under "API"
protest run tests:session::API::Users
```

### By Keyword (-k)

Run tests whose name contains a substring:

```bash
# Run tests containing "login" in their name
protest run tests:session -k login

# Multiple patterns use OR logic
protest run tests:session -k login -k logout
```

### By Tags (-t, --tag)

Run only tests with specific tags:

```bash
protest run tests:session --tag slow
protest run tests:session -t integration -t api   # OR logic
```

Exclude tests with specific tags:

```bash
protest run tests:session --no-tag flaky
```

### Re-run Failed Tests (--lf)

Only run tests that failed in the previous run:

```bash
protest run tests:session --lf
protest run tests:session --last-failed
```

Clear the failure cache:

```bash
protest run tests:session --cache-clear
```

### Combining Filters

All filters compose as intersection:

```bash
# Suite + keyword
protest run tests:session::API -k users

# Suite + keyword + tag
protest run tests:session::API -k users -t slow

# All filters together
protest run tests:session::API -k login -t integration --lf
```

## Execution Options

### Parallelism (-n)

Run tests concurrently:

```bash
protest run tests:session -n 4      # 4 workers
protest run tests:session -n 8      # 8 workers
```

### Exit on First Failure (-x)

Stop immediately when a test fails:

```bash
protest run tests:session -x
protest run tests:session --exitfirst
```

### Disable Output Capture (-s)

Show print statements and logs during test execution:

```bash
protest run tests:session -s
protest run tests:session --no-capture
```

### Collect Without Running

List tests without executing them:

```bash
protest run tests:session --collect-only
```

### Module Location

If your module is in a specific directory:

```bash
protest run tests:session --app-dir src
```

## Running with Coverage

ProTest doesn't include a built-in coverage tool, but works seamlessly with [coverage.py](https://coverage.readthedocs.io/). Just run `protest` through `coverage run`:

```bash
# Collect coverage data
coverage run -m protest run tests:session

# Show report with missing lines
coverage report -m --include="app/*"

# Or generate an HTML report
coverage html --include="app/*"
```

If you use `uv`, prefix with `uv run`:

```bash
uv run coverage run -m protest run tests:session
uv run coverage report -m --include="app/*"
```

> **Tip:** Add `coverage` to your dev dependencies (`uv add --group dev coverage`).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed or errored |

## Tags Command

See all tags declared in a session:

```bash
protest tags list tests:session
```

Show effective tags per test (including inherited):

```bash
protest tags list tests:session -r
protest tags list tests:session --recursive
```
