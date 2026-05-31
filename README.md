![ProTest](assets/logo-with-text-animate.svg)

[![CI](https://github.com/renaudcepre/protest/actions/workflows/ci.yml/badge.svg)](https://github.com/renaudcepre/protest/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/renaudcepre/protest/graph/badge.svg?token=V0MLGEE5UZ)](https://codecov.io/gh/renaudcepre/protest)
[![docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://renaudcepre.github.io/protest/)

**Write your tests and your LLM evals in one async-first framework.**

An eval is just a test that returns a value — scored, not asserted. Your evals get
real fixtures, dependency injection and parallelism, and live right next to the
tests they ship with. Python 3.10+, installs lean (Rich UI optional).

---

## Why ProTest?

### Explicit Injection (IDE-Ready)

**Ctrl+Click works.** Your IDE knows every type. No guessing where fixtures come from.

```python
def test_user(db: Annotated[Database, Use(database)]): ...
```

### Native Async & Parallelism

Tests run as coroutines on a single event loop. No plugin needed.

```bash
protest run tests:session -n 10
```

### Smart Tagging (Tag Propagation)

Tag a fixture once, every test using it inherits the tag automatically.

```python
@fixture(tags=["database"])
def db(): ...

session.bind(db)

@session.test()
def test_users(repo: Annotated[Repo, Use(user_repo)]): ...  # Also tagged "database"
```

```bash
protest run tests:session --no-tag database  # Skips ALL tests touching DB
```

### Infra vs Code Errors (Error ≠ Fail)

```
✗ test_create_user: AssertionError       # Your bug - TEST FAILED
⚠ test_with_db: [FIXTURE] ConnectionError  # Infra issue - SETUP ERROR
```

### Typed Parameterization

```python
CODES = ForEach([200, 201])

@session.test()
def test_status(code: Annotated[int, From(CODES)]): ...
```

### Native LLM Evals

Score model outputs alongside your tests — same fixtures, same parallelism, same `protest` CLI. Cases get pass/fail + numeric metrics, persisted to JSONL for run-over-run comparison.

```python
from typing import Annotated
from protest import ForEach, From, ProTestSession
from protest.evals import EvalCase, EvalSuite
from protest.evals.evaluators import contains_keywords

session = ProTestSession()
chatbot_suite = EvalSuite("chatbot")
session.add_suite(chatbot_suite)

cases = ForEach([
    EvalCase(name="capital_fr", inputs="Capital of France?", expected="Paris"),
])

@chatbot_suite.eval(evaluators=[contains_keywords(keywords=["paris"])])
async def chatbot(case: Annotated[EvalCase, From(cases)]) -> str:
    return await my_agent(case.inputs)  # your LLM call
```

```bash
protest eval evals.session:session   # runs are recorded to .protest/history.jsonl
```

See [Evals docs](https://renaudcepre.github.io/protest/evals/) for evaluators, judges, and scoring.

---

## Quick Start

```python
from protest import ProTestSession

session = ProTestSession()


def inc(x):
    return x + 1


@session.test()
def test_answer():
    assert inc(3) == 4
```

```bash
protest run test_sample:session
```

## Installation

ProTest is not yet on PyPI. Install directly from GitHub:

```bash
# With uv (recommended)
uv add git+https://github.com/renaudcepre/protest.git

# With pip
pip install git+https://github.com/renaudcepre/protest.git
```

## CLI

```bash
protest run module:session                    # Run tests
protest run module:session -n 4               # Parallel (4 workers)
protest run module:session --lf               # Re-run failed tests only
protest run module:session --collect-only     # List tests without running
protest run module:session --cache-clear      # Clear cache before run
protest run module:session --app-dir src      # Look for module in src/
protest run module:session --ctrf-output r.json  # CTRF report for CI/CD

protest eval module:session                   # Run LLM evals
protest eval module:session --tag safety      # Filter by case tag
protest eval module:session --last-failed     # Re-run failed cases only
```

## Features

- **Explicit DI** - No guessing which fixture you're using
- **Async native** - No plugin needed, just `async def`
- **Parallel execution** - Built-in with `-n 4`
- **Scoped fixtures** - `SESSION`, `SUITE`, `TEST`
- **Mix sync/async** - They just work together
- **Factory fixtures** - Callables to create instances on-demand
- **Plugin system** - Custom reporters, filters
- **Last-failed mode** - Re-run only failed tests with `--lf`
- **CTRF reports** - Standardized JSON for CI/CD integration
- **Native LLM evals** - Scored cases, JSONL history, `protest eval` (see [evals docs](https://renaudcepre.github.io/protest/evals/))

## Why Not pytest?

|          | pytest                          | ProTest                              |
|----------|---------------------------------|--------------------------------------|
| Fixtures | Implicit (by name)              | Explicit (`Use(fixture)`)            |
| Params   | Hidden in fixture               | Visible in test (`From()` + factory) |
| Async    | Plugin required                 | Native                               |
| Parallel | Plugin required                 | Built-in                             |
| Cycles   | Runtime error                   | Prevented at registration            |
| Evals    | External (deepeval, pydantic-…) | Native (`protest eval`, JSONL history) |

pytest has a large ecosystem and extensive community. ProTest is an alternative if you
prefer FastAPI-style explicit dependencies and native async in your tests.

## Documentation

Full API reference, guides, and examples: [renaudcepre.github.io/protest](https://renaudcepre.github.io/protest/)

## License

MIT
