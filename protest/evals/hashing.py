"""Content hashing for eval cases — detect when cases or scoring change."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

HASH_LENGTH = 12


def compute_case_hash(inputs: Any, expected_output: Any) -> str:
    """Hash the case content (inputs + expected_output)."""
    data = {"inputs": _canonical(inputs), "expected": _canonical(expected_output)}
    return _hash(data)


def compute_eval_hash(
    evaluators: list[Any],
) -> str:
    """Hash the scoring config (evaluators only)."""
    data = {
        "evaluators": [_canonical(e) for e in evaluators],
    }
    return _hash(data)


def _hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:HASH_LENGTH]


def _canonical(obj: Any) -> Any:
    """Convert an object to a canonical JSON-serializable form."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_canonical(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in sorted(obj.items())}
    # Pydantic models
    if hasattr(obj, "model_dump"):
        return _canonical(obj.model_dump(mode="json"))
    # Dataclasses — iterate without deepcopy to support non-picklable fields
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: _canonical(getattr(obj, f.name)) for f in dataclasses.fields(obj)
        }
    # Fallback
    return repr(obj)
