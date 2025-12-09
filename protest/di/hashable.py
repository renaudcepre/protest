from __future__ import annotations

from typing import Any


class UnhashableValueError(TypeError):
    def __init__(self, value: Any, path: str):
        type_name = type(value).__name__
        super().__init__(
            f"Cannot make value hashable at '{path}': type '{type_name}' is not supported. "
            f"Supported types: primitives, list, tuple, dict, set, frozenset."
        )


def _convert_sequence(value: list[Any] | tuple[Any, ...], path: str) -> tuple[Any, ...]:
    return tuple(
        make_hashable(item, f"{path}[{idx}]") for idx, item in enumerate(value)
    )


def _convert_set(value: set[Any] | frozenset[Any], path: str) -> frozenset[Any]:
    return frozenset(make_hashable(item, f"{path}{{...}}") for item in value)


def _convert_dict(value: dict[Any, Any], path: str) -> tuple[tuple[Any, Any], ...]:
    try:
        sorted_keys = sorted(value.keys())
    except TypeError:
        sorted_keys = list(value.keys())
    return tuple(
        (key, make_hashable(value[key], f"{path}[{key!r}]")) for key in sorted_keys
    )


def make_hashable(value: Any, path: str = "root") -> Any:
    """Recursively convert mutable containers to immutable equivalents for hashing.

    Converts: list → tuple, dict → tuple of sorted items, set → frozenset.
    Primitives (str, int, float, bool, None, bytes) pass through unchanged.
    """
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value

    if isinstance(value, (list, tuple)):
        return _convert_sequence(value, path)

    if isinstance(value, (set, frozenset)):
        return _convert_set(value, path)

    if isinstance(value, dict):
        return _convert_dict(value, path)

    try:
        hash(value)
        return value
    except TypeError:
        raise UnhashableValueError(value, path) from None
