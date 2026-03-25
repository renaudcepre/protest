"""Type hints resolution with PEP 563 / TYPE_CHECKING compatibility.

Shared by the core DI system and evals runner. Handles two failure modes:

1. Local fixtures — ``from __future__ import annotations`` stringifies
   annotations; names defined in local scopes aren't in ``func.__globals__``.
   Fix: collect locals from the call stack.

2. TYPE_CHECKING-only types — e.g. ``AsyncDriver`` imported only under
   ``if TYPE_CHECKING:``. Fix: substitute ``Any`` for each unresolvable
   name. The type itself is irrelevant for DI; only the ``Use(...)``
   marker inside ``Annotated[...]`` matters.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_type_hints


def get_type_hints_compat(func: Any) -> dict[str, Any]:
    """Resolve type hints with PEP 563 / TYPE_CHECKING fallbacks."""
    try:
        return get_type_hints(func, include_extras=True)
    except Exception:
        pass

    # Build a namespace from the entire call stack (covers local fixtures).
    localns: dict[str, Any] = {}
    try:
        for frame_info in inspect.stack():
            localns.update(frame_info.frame.f_locals)
    except Exception:
        pass

    try:
        return get_type_hints(func, localns=localns, include_extras=True)
    except Exception:
        pass

    # TYPE_CHECKING fallback: substitute Any for unresolvable names.
    return _get_type_hints_substituting_any(func, localns)


def _get_type_hints_substituting_any(
    func: Any,
    localns: dict[str, Any],
) -> dict[str, Any]:
    """Retry get_type_hints, replacing each NameError'd name with Any."""
    localns = dict(localns)
    for _ in range(20):
        try:
            return get_type_hints(func, localns=localns, include_extras=True)
        except NameError as exc:
            match = re.search(r"name '(\w+)' is not defined", str(exc))
            if not match:
                break
            localns[match.group(1)] = Any
        except Exception:
            break
    return {}
