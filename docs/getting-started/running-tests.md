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

### Verbosity Levels (-v)

Control output detail level. By default, only failures are shown with a live progress bar:

```bash
protest run tests:session           # Default: progress bar + failures only
protest run tests:session -v        # Show all test names + suite headers
protest run tests:session -vv       # Also show lifecycle (setup/teardown)
protest run tests:session -vvv      # Also show fixtures
```

| Level | Shows |
|-------|-------|
| 0 (default) | Progress bar, failures, summary |
| 1 (-v) | + All test names, suite headers |
| 2 (-vv) | + Session/suite setup and teardown |
| 3 (-vvv) | + Fixture setup and teardown |

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
