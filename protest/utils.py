"""Utility functions for ProTest."""

from collections.abc import Callable
from typing import Any


def normalize_reason(value: bool | str, default: str) -> str | None:
    """Normalize a bool|str flag to a reason string or None.

    Used for skip/xfail parameters that accept either:
    - False: disabled, returns None
    - True: enabled with default reason
    - str: enabled with custom reason

    Examples:
        normalize_reason(False, "Skipped") -> None
        normalize_reason(True, "Skipped") -> "Skipped"
        normalize_reason("WIP", "Skipped") -> "WIP"
    """
    if not value:
        return None
    if isinstance(value, str):
        return value
    return default


def get_callable_name(func: Callable[..., Any], fallback: str = "<unnamed>") -> str:
    """Get the name of a callable, with a fallback for edge cases.

    Python's `Callable[..., Any]` type doesn't guarantee `__name__` exists.
    While all regular functions (`def`) have `__name__`, the type system
    can't prove this. This function provides a safe way to get the name
    with a fallback for:
    - Lambdas (have `__name__` = "<lambda>")
    - Callable objects without `__name__`
    - Partial functions
    - Built-in functions in some edge cases

    This pattern is used by FastAPI and other frameworks that work with
    decorated callables.
    """
    return getattr(func, "__name__", fallback)
