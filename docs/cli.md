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
| `eval` | Run evaluations |
| `history` | Browse run history (tests and evals) |
| `live` | Start live reporter server |
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

## protest eval

Run evaluations from a session.

`protest eval` is the eval-suite counterpart of `protest run`. It shares
the same target format, filters, capture flags and reporting options as
`run`; the differences are listed below.

### Syntax

```bash
protest eval <target> [options]
```

### Options

`protest eval` accepts every option from `protest run` (see above:
`-n/--concurrency`, `--collect-only`, `-x/--exitfirst`, `-s/--no-capture`,
`-q/--quiet`, `-v/--verbose`, `--show-logs`, `-t/--tag`, `--no-tag`,
`-k/--keyword`, `--lf`, `--cache-clear`, `--no-color`, `--ctrf-output`,
`--no-log-file`, `--app-dir`), plus one eval-only flag:

| Option | Description | Default |
|--------|-------------|---------|
| `--show-output` | Print `inputs` / `output` / `expected` for **every** case (failed cases always print these). | off |

### Examples

```bash
# Run all evals in a session
protest eval evals.session:session

# One specific suite
protest eval evals.session:session::helpdesk_struct

# One ticket by name
protest eval evals.session:session -k T001

# All cases tagged "cat:hardware"
protest eval evals.session:session --tag cat:hardware

# Re-run only the cases that failed last time
protest eval evals.session:session --lf

# Show the input/output of every case (not just failures)
protest eval evals.session:session --show-output
```

### Output

Each case prints one line:

```
✓   classify_ticket_struct[T011] (2ms) category_is_allowed=✓ summary_keyword_recall=1.00 …
```

After every suite, an aggregate-stats table summarizes the `Metric`
fields across cases (mean / p50 / p5 / p95). `Verdict` and `Reason`
fields don't appear in this table — only numeric `Metric` fields do.

Per-case markdown artifacts are written to
`.protest/results/<suite>_<timestamp>/<case-id>.md`, with the full
input, output, expected, and per-evaluator scores.

---

## protest history

Browse persisted run history (tests and evals).

Every run appends one entry to `.protest/history.jsonl`; `protest history`
queries that file with various views.

### Syntax

```bash
protest history [view] [filters]
```

Exactly one view is shown at a time. The view defaults to a per-suite
trend table when no flag is given.

### View flags (mutually exclusive)

| Flag | Description |
|------|-------------|
| _(none)_ | Per-suite trend table: pass-rate trend + score arrows |
| `--runs` | Run-by-run pass rates, most recent first |
| `--show [N]` | Detailed panel for the Nth most recent run (`0` = latest, default) |
| `--compare` | Compare the two most recent runs of the same model |

### Filters (apply to all views)

| Flag | Description | Default |
|------|-------------|---------|
| `--tail N`, `-n N` | Limit to the N most recent entries | 10 |
| `--evals` | Show eval runs only | _all kinds_ |
| `--tests` | Show test runs only | _all kinds_ |
| `--model NAME` | Filter by `ModelLabel.name` | _all_ |
| `--suite NAME` | Filter by suite name | _all_ |
| `--clean-dirty` | Remove entries from runs made on a dirty working tree | off |
| `--path DIR` | Use a custom history directory | `.protest/` |

### Reading `--compare`

`--compare` reports four kinds of change between the two most recent
runs of the same model:

| Marker | Label | Meaning |
|--------|-------|---------|
| `+` | Fixed | Case was failing in the previous run, passes now |
| `-` | Regressions | Case was passing in the previous run, fails now |
| `⟳` | Modified | Case is recognizable (same name) but its content changed |
| `*` | New | Case did not exist in the previous run |
| `✗` | Deleted | Case existed in the previous run, gone now |

The `Modified` line tells you **what** changed by suffixing the case
name:

- `T001 (case modified)` — `inputs` or `expected` changed (`case_hash`
  diff)
- `T001 (scoring modified)` — only the evaluator configuration changed
  (`eval_hash` diff). Inputs and expected output are intact; you've
  edited an evaluator or its parameters.

### Examples

```bash
# Per-suite trend across last 10 runs (default view)
protest history --evals

# Run-by-run breakdown of the last 5 eval runs
protest history --evals --runs --tail 5

# Detailed panel for the most recent run
protest history --evals --show

# Detailed panel for the run before that (1 = next-most-recent)
protest history --evals --show 1

# Compare the two most recent runs
protest history --evals --compare

# Filter to one model across all views
protest history --evals --model qwen-2.5

# Drop runs made on a dirty working tree before any view
protest history --evals --clean-dirty
```

### Notes

- When the project is not a git repo, the per-run commit / dirty
  columns display `?`. `--clean-dirty` is a no-op in that case.
- `--evals` and `--tests` are mutually exclusive; omit both to see
  every kind.
- Per-case detail (input, output, expected, evaluator scores) lives in
  `.protest/results/`, not in the history file.

---

## protest live

Start a persistent live reporter server for real-time test visualization.

### Syntax

```bash
protest live [options]
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--port` | `-p` | Port to listen on | 8765 |

### Example

```bash
# Start the live server
protest live

# Start on a custom port
protest live -p 9000
```

The live server stays running and displays test results in real-time as you run tests in another terminal.

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
