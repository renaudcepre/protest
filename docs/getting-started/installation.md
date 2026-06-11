# Installation

## Requirements

- Python 3.10 or higher

## Install

ProTest is not yet on PyPI. Install directly from GitHub:

```bash
# With uv (recommended)
uv add git+https://github.com/renaudcepre/protest.git

# With pip
pip install git+https://github.com/renaudcepre/protest.git
```

## Install from source (development)

```bash
git clone https://github.com/renaudcepre/protest.git
cd protest
uv sync
```

## Optional: Rich Output

ProTest automatically uses [Rich](https://rich.readthedocs.io/) for better terminal output if installed. If Rich is not available, it falls back to plain ASCII output.

```bash
uv add rich
```

## IDE / type checker setup

ProTest ships a `py.typed` marker, so Pyright, mypy and Pylance pick up
its type hints once it is installed in the project's virtual env.

If your editor reports `Import "protest" could not be resolved`, point
your type checker at the right interpreter:

- **VS Code / Pylance**: open the command palette → *Python: Select
  Interpreter* → choose `.venv/bin/python` (the one `uv` created).
- **Pyright (CLI/standalone)**: add a `pyrightconfig.json` next to your
  `pyproject.toml`:

  ```json
  {
    "venvPath": ".",
    "venv": ".venv"
  }
  ```

- **mypy**: run via `uv run mypy ...` so it inherits the same
  interpreter, or set `python_executable` in `mypy.ini`.

Once configured, no extra stub package or plugin is needed - protest
exposes its own types directly.
