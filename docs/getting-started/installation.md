# Installation

## Requirements

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) (recommended package manager)

## Install from source

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
