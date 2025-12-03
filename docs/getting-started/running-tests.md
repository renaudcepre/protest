# Running Tests

## Basic Command

```bash
protest run <module>:<session>
```

- `<module>` - Python module path (e.g., `tests`, `myapp.tests`)
- `<session>` - Name of the `ProTestSession` variable in that module

## Common Options

### Parallelism

Run tests concurrently:

```bash
protest run tests:session -n 4      # 4 workers
protest run tests:session -n 8      # 8 workers
```

### Exit on First Failure

Stop immediately when a test fails:

```bash
protest run tests:session -x
protest run tests:session --exitfirst
```

### Re-run Failed Tests

Only run tests that failed in the previous run:

```bash
protest run tests:session --lf
protest run tests:session --last-failed
```

Clear the failure cache:

```bash
protest run tests:session --cache-clear
```

### Filter by Tags

Run only tests with specific tags:

```bash
protest run tests:session --tag slow
protest run tests:session -t integration -t api   # OR logic
```

Exclude tests with specific tags:

```bash
protest run tests:session --no-tag flaky
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

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed or errored |

## List Tags

See all tags declared in a session:

```bash
protest tags list tests:session
```

Show effective tags per test (including inherited):

```bash
protest tags list tests:session -r
protest tags list tests:session --recursive
```
