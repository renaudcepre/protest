# Development

Guide for contributing to ProTest.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) - Package manager
- [just](https://github.com/casey/just) - Command runner

## Setup

```bash
git clone https://github.com/renaudcepre/protest.git
cd protest
just setup
```

This installs dependencies and sets up pre-commit hooks.

## Commands

```bash
just              # Show available commands
just test         # Run tests
just test-cov     # Run tests with coverage
just lint         # Format and lint code
just fullcheck    # Lint + types + tests (CI equivalent)
just docs         # Serve documentation locally
just clean        # Remove cache files
```

## Running Tests

ProTest uses pytest for its own test suite:

```bash
# All tests
just test

# Specific file
just test tests/core/test_session.py

# With coverage
just test-cov

# Coverage with HTML report
just test-cov-open
```

## Code Quality

### Linting & Formatting

```bash
just lint
```

Uses:
- **ruff format** - Code formatting
- **ruff check** - Linting (pyflakes, pycodestyle, bugbear, etc.)
- **mypy --strict** - Type checking

### Pre-commit

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
pre-commit run --all-files
```

## Project Structure

```
protest/
├── protest/              # Main package
│   ├── cli/              # Command-line interface
│   ├── core/             # Session, suite, runner, collector
│   ├── di/               # Dependency injection (Use, From, ForEach)
│   ├── entities/         # Data classes (TestResult, etc.)
│   ├── events/           # Event bus and hooks
│   ├── execution/        # Test execution engine
│   ├── filters/          # Test filtering (keywords, suites)
│   ├── fixtures/         # Built-in fixtures (caplog, mocker)
│   ├── reporting/        # Reporters (Rich, ASCII, CTRF, Web)
│   ├── tags/             # Tag filtering plugin
│   └── cache/            # Last-failed cache plugin
├── tests/                # Test suite (mirrors protest/ structure)
├── docs/                 # MkDocs documentation
├── web/                  # Web reporter UI (Vite + vanilla JS)
└── examples/             # Example project (yorkshire)
```

## Documentation

```bash
just docs
```

Opens http://127.0.0.1:8000 with live reload.

Documentation source is in `docs/` using MkDocs with Material theme.


## Running the Example

```bash
uv run protest run examples.yorkshire.tests.session:session
```
