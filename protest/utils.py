"""Utility functions for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


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
