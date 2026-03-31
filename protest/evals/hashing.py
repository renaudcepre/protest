"""Content hashing for eval cases — detect when cases or scoring change.

Hashes capture identity + configuration, not implementation. A renamed
parameter changes the hash; a rewritten function body does not. This is
a deliberate trade-off: we detect config drift, not code drift.

Custom evaluators can implement ``evaluator_identity()`` to control
exactly what gets hashed. Built-in types (dataclass, functools.partial,
plain callable) are introspected automatically as a fallback.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
from typing import Any

HASH_LENGTH = 12


class CanonicalError(TypeError):
    """Raised when an object cannot be converted to a canonical form."""


def compute_case_hash(inputs: Any, expected_output: Any) -> str:
    """Hash the case content (inputs + expected_output)."""
    data = {"inputs": _canonical(inputs), "expected": _canonical(expected_output)}
    return _hash(data)


def compute_eval_hash(evaluators: list[Any]) -> str:
    """Hash the scoring config (evaluators only)."""
    data = {"evaluators": [_canonical(e) for e in evaluators]}
    return _hash(data)


def _hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:HASH_LENGTH]


def _canonical(obj: Any) -> Any:  # noqa: PLR0911
    """Convert an object to a canonical JSON-serializable form.

    Resolution order:
    1. Primitives, list, tuple, dict — native support
    2. ``evaluator_identity()`` — explicit, user-controlled
    3. Dataclass / functools.partial / callable — introspection fallback
    4. Anything else → CanonicalError
    """
    # --- primitives & containers ---
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_canonical(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in sorted(obj.items())}

    # --- explicit identity (user-controlled) ---
    if hasattr(obj, "evaluator_identity"):
        return _canonical(obj.evaluator_identity())

    # --- introspection fallback ---

    # Dataclasses — public fields only (skip _ prefixed runtime internals)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            "__type__": type(obj).__qualname__,
            **{
                f.name: _canonical(getattr(obj, f.name))
                for f in dataclasses.fields(obj)
                if not f.name.startswith("_")
            },
        }
    # functools.partial — qualname + bound kwargs
    if isinstance(obj, functools.partial):
        return {
            "fn": _fn_qualname(obj.func),
            "args": _canonical(list(obj.args)) if obj.args else [],
            "kwargs": _canonical(dict(obj.keywords)) if obj.keywords else {},
        }
    # Plain callable — qualname only
    if callable(obj):
        qualname = _fn_qualname(obj)
        if qualname is not None:
            return {"fn": qualname}

    raise CanonicalError(
        f"Cannot canonicalize {type(obj).__name__!r}. "
        f"Implement evaluator_identity() or use a supported type "
        f"(primitives, list, dict, dataclass, callable)."
    )


def _fn_qualname(fn: Any) -> str | None:
    """Extract a stable qualified name from a callable."""
    return getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
