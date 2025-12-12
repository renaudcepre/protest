# CLI Reference

Complete reference for the ProTest command-line interface.

## Synopsis

```bash
protest <command> [options] <target>
```

## Commands

| Command | Description |
|---------|-------------|
| `run` | Run tests |
| `tags list` | List tags in a session |

---

## protest run

Run tests from a session.

### Syntax

```bash
protest run <target> [options]
```

### Target Format

```
<module>:<session>[::SuiteName[::NestedSuite]]
```

| Part | Required | Description |
|------|----------|-------------|
| `module` | Yes | Python module path |
| `session` | Yes | Name of the `ProTestSession` variable |
| `::SuiteName` | No | Filter to specific suite |

**Examples:**

```bash
protest run tests:session              # Run all tests
protest run myapp.tests:session        # Module in package
protest run tests:session::API         # Only API suite
protest run tests:session::API::Users  # Nested suite
```

### Options

#### Filtering Options

| Option | Short | Description |
|--------|-------|-------------|
| `::SuiteName` | - | Run only tests in specified suite (part of target) |
| `--keyword` | `-k` | Run tests matching keyword (substring match) |
| `--tag` | `-t` | Run tests with specified tag |
| `--no-tag` | - | Exclude tests with specified tag |
| `--last-failed` | `--lf` | Run only tests that failed last time |
| `--cache-clear` | - | Clear the test cache before running |
| `--collect-only` | - | List tests without running them |

#### Execution Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--concurrency` | `-n` | Number of parallel workers | 1 |
| `--exitfirst` | `-x` | Stop on first failure | false |
| `--no-capture` | `-s` | Show stdout/stderr during tests | false |
| `--app-dir` | - | Directory containing the module | . |

#### Output Options

| Option | Description |
|--------|-------------|
| `--no-color` | Disable colors (plain ASCII output) |
| `--no-log-file` | Disable writing to `.protest/last_run.log` |
| `--ctrf-output PATH` | Output CTRF JSON report to PATH |

---

## Filtering in Detail

### Suite Filter (::SuiteName)

The suite filter is part of the target, not a separate option. It filters tests to only those belonging to the specified suite and its children.

```bash
# Given this structure:
# session
# ├── API (suite)
# │   ├── Users (nested suite)
# │   │   ├── test_list_users
# │   │   └── test_create_user
# │   └── test_api_health
# └── test_standalone

# Run all API tests (including Users)
protest run tests:session::API
# Runs: test_api_health, test_list_users, test_create_user

# Run only Users tests
protest run tests:session::API::Users
# Runs: test_list_users, test_create_user

# Standalone tests are excluded when using suite filter
```

!!! note "Standalone Tests"
    Tests registered directly on the session (not in any suite) are excluded when using a suite filter.

### Keyword Filter (-k)

Match tests by substring in their name. Multiple `-k` flags use OR logic.

```bash
# Match test names containing "login"
protest run tests:session -k login
# Matches: test_login, test_login_failed, test_user_login

# Multiple keywords (OR logic)
protest run tests:session -k login -k logout
# Matches: test_login, test_logout, test_login_failed

# Works with parameterized tests (matches case IDs too)
protest run tests:session -k admin
# Matches: test_user[admin], test_permissions[admin-read]
```

!!! tip "Case Sensitivity"
    Keyword matching is case-sensitive. Use exact casing from your test names.

### Tag Filter (-t, --no-tag)

Filter by tags declared on tests, suites, or fixtures.

```bash
# Include tests with tag
protest run tests:session -t unit

# Multiple tags (OR logic)
protest run tests:session -t unit -t integration

# Exclude tests with tag
protest run tests:session --no-tag slow

# Combine include and exclude
protest run tests:session -t api --no-tag flaky
```

Tags are inherited:

- Tests inherit tags from their parent suite
- Tests inherit tags from fixtures they depend on (transitively)

### Last Failed (--lf)

Re-run only tests that failed in the previous run.

```bash
# First run - some tests fail
protest run tests:session
# Output: 8/10 passed, 2 failed

# Second run - only failed tests
protest run tests:session --lf
# Runs only the 2 failed tests
```

!!! warning "Behavior with Other Filters"
    When combined with other filters, `--lf` returns the **intersection**:

    - `--lf -t slow` → failed tests that have tag "slow"
    - If no failed tests match the filter, **0 tests run** (no fallback)

```bash
# Clear cache to run all tests again
protest run tests:session --cache-clear
```

---

## Combining Filters

All filters compose as **intersection** (AND logic between filter types).

```bash
# Suite AND keyword
protest run tests:session::API -k users
# Tests in API suite with "users" in name

# Suite AND keyword AND tag
protest run tests:session::API -k users -t slow
# Tests in API suite, with "users" in name, tagged "slow"

# Suite AND keyword AND tag AND last-failed
protest run tests:session::API -k users -t slow --lf
# Failed tests in API suite, with "users" in name, tagged "slow"
```

**Filter evaluation order:**

```
Collected tests
    → Suite filter (::SuiteName)
    → Keyword filter (-k)
    → Tag filter (-t, --no-tag)
    → Cache filter (--lf)
    → Final test list
```

---

## Execution Examples

### Development Workflow

```bash
# Run all tests
protest run tests:session

# Quick check - stop on first failure
protest run tests:session -x

# Re-run failures
protest run tests:session --lf

# Re-run failures, stop on first
protest run tests:session --lf -x
```

### CI/CD Workflow

```bash
# Full test suite, parallel
protest run tests:session -n 4

# Unit tests only
protest run tests:session -t unit -n 4

# Integration tests (might need sequential)
protest run tests:session -t integration

# Generate CTRF report for CI tools
protest run tests:session -n 4 --ctrf-output ctrf-report.json
```

### Debugging

```bash
# See output from tests
protest run tests:session -s

# Run specific test
protest run tests:session -k test_specific_function

# List what would run
protest run tests:session::API -k login --collect-only
```

### Working on a Feature

```bash
# Focus on one suite during development
protest run tests:session::API::Users -x

# Run related tests
protest run tests:session -k user -x

# Check everything still works
protest run tests:session
```

---

## protest tags list

List tags declared in a session.

### Syntax

```bash
protest tags list <target> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--recursive` | `-r` | Show effective tags per test |
| `--app-dir` | - | Directory containing the module |

### Examples

```bash
# List all declared tags
protest tags list tests:session
# Output:
# api
# database
# integration
# slow
# unit

# Show tags per test (includes inherited)
protest tags list tests:session -r
# Output:
# Effective tags for 3 test(s):
#
#   API::test_api_call
#     tags: api, integration
#
#   API::test_db_query
#     tags: database, slow
#
#   test_simple
#     tags: unit
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed (or no tests collected) |
| 1 | One or more tests failed or errored |

---

## Environment

### Cache Location

Test results are cached in `.protest/cache.json` relative to the current directory.

```bash
# View cache location
ls .protest/

# Clear cache
protest run tests:session --cache-clear
# Or manually: rm -rf .protest/
```

### Module Resolution

By default, ProTest looks for modules in the current directory. Use `--app-dir` to specify a different location:

```bash
# Module in src/ directory
protest run myapp.tests:session --app-dir src

# Module in project root (default)
protest run tests:session
```
