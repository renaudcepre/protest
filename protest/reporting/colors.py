"""ANSI color support with automatic TTY detection."""

import os
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def supports_color() -> bool:
    """Detect if terminal supports ANSI colors."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class Fg:
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


def colorize(text: str, *codes: str) -> str:
    """Apply ANSI codes to text. No-op if colors disabled."""
    if not supports_color():
        return text
    return "".join(codes) + text + Style.RESET
