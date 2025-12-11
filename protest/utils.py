"""Utility functions for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from protest.entities import Retry, Skip, Xfail


def normalize_skip(skip: bool | str | Skip | None) -> Skip | None:
    """Normalize skip parameter to Skip object or None."""
    if skip is None or skip is False:
        return None
    if skip is True:
        return Skip()
    if isinstance(skip, str):
        return Skip(reason=skip)
    return skip


def normalize_xfail(xfail: bool | str | Xfail | None) -> Xfail | None:
    """Normalize xfail parameter to Xfail object or None."""
    if xfail is None or xfail is False:
        return None
    if xfail is True:
        return Xfail()
    if isinstance(xfail, str):
        return Xfail(reason=xfail)
    return xfail


def normalize_retry(retry: int | Retry | None) -> Retry | None:
    """Normalize retry parameter to Retry object or None."""
    if retry is None:
        return None
    if isinstance(retry, int):
        return Retry(times=retry)
    return retry


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
