"""Validation utilities for fixture decorators."""

from __future__ import annotations

from inspect import signature
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from protest.di.markers import ForEach, From
from protest.exceptions import ParameterizedFixtureError
from protest.utils import get_callable_name

if TYPE_CHECKING:
    from collections.abc import Callable


def _extract_from_params(func: Callable[..., Any]) -> dict[str, ForEach[Any]]:
    """Extract parameters annotated with From(source)."""
    try:
        type_hints = get_type_hints(func, include_extras=True)
    except Exception:  # noqa: BLE001 - get_type_hints can fail on unresolvable annotations
        type_hints = {}

    result: dict[str, ForEach[Any]] = {}
    for param_name in signature(func).parameters:
        annotation = type_hints.get(param_name)
        if annotation is not None and get_origin(annotation) is Annotated:
            for metadata in get_args(annotation)[1:]:
                if isinstance(metadata, From):
                    result[param_name] = metadata.source
                    break
    return result


def validate_no_from_params(func: Callable[..., Any]) -> None:
    """Raise ParameterizedFixtureError if fixture uses From()."""
    from_params = _extract_from_params(func)
    if from_params:
        raise ParameterizedFixtureError(
            get_callable_name(func), list(from_params.keys())
        )
