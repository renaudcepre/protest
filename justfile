# justfile for ProTest development
@default:
    echo "Hi ! Welcome to ProTest !"
    just --list

# Run all linting and formatting
@lint:
    ruff format .
    ruff check --fix .
    mypy --strict protest

@fullcheck:
  ruff format --check . && ruff check .  # lint
  mypy --strict protest                  # types
  uv run pytest -vv                      # tests

# Run tests with verbose output
@test *options="":
    uv run pytest -vv {{ options }}

# Run tests with coverage
@test-cov *options="":
    uv run pytest -vv --cov=protest --cov-report=term {{ options }}

# Run tests with coverage and open browser
@test-cov-open *options="":
    uv run pytest -vv --cov=protest --cov-report=html {{ options }}
    python -m webbrowser htmlcov/index.html

# Development setup
setup:
    uv sync --dev

# Clean cache and temp files
clean:
    rm -rf .pytest_cache/
    rm -rf .ruff_cache/
    rm -rf htmlcov/
    find . -type d -name __pycache__ -exec rm -rf {} +
