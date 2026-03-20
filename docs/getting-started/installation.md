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
