# Installation

## Requirements

- Python 3.10 or higher

## Install with pip

```bash
pip install protest
```

## Install with uv

```bash
uv add protest
```

## Optional: Rich Output

ProTest automatically uses [Rich](https://rich.readthedocs.io/) for better terminal output if installed. If Rich is not available, it falls back to plain ASCII output.

```bash
pip install rich
```

## Verify Installation

```bash
protest --help
```

You should see the available commands:

```
Usage: protest [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  run   Run tests from a session
  tags  Tag-related commands
```
