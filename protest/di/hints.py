"""Type hints resolution with PEP 563 / TYPE_CHECKING compatibility.

Shared by the core DI system and evals runner. ``get_type_hints()`` alone
fails in two scenarios commonly encountered in ProTest user code; this
module wraps it with a cascade of fallbacks.

------------------------------------------------------------------------
Failure mode 1 — names defined in a local scope (PEP 563 stringification)
------------------------------------------------------------------------

With ``from __future__ import annotations``, all annotations are stored
as strings. ``get_type_hints()`` resolves them via ``eval()`` inside
``func.__globals__`` only. Names defined in the scope of an enclosing
function are NOT in ``__globals__``, so resolution raises ``NameError``.

The most common form of this in ProTest is a parametrized eval defined
inside a helper, where the case source is a local variable::

    def _build_suite(cases):
        source = ForEach(cases)            # local to _build_suite

        @suite.eval()
        def my_eval(case: Annotated[EvalCase, From(source)]) -> str:
            #                              ^^^^^^ refers to `source`,
            #                              which is local to _build_suite
            return str(case.inputs)

When ``get_type_hints(my_eval)`` evaluates ``"Annotated[EvalCase, From(source)]"``
inside ``my_eval.__globals__``, ``source`` is undefined → ``NameError``.

Fix: walk the call stack with ``inspect.stack()`` and merge every frame's
``f_locals`` into a ``localns`` dict that we pass to ``get_type_hints()``
on retry. This is registration-time only (decorator evaluation), never
in a hot path, so the cost of ``inspect.stack()`` is acceptable.

Trade-off: ``localns`` ends up containing every local from every frame
on the stack. Name collisions silently resolve to the most recently
seen binding. In practice no collision has been observed in this project,
because annotations only reference DI markers (``Use``/``From``) plus
small, distinctively-named locals.

-------------------------------------------------
Failure mode 2 — TYPE_CHECKING-only imported types
-------------------------------------------------

Types imported under ``if TYPE_CHECKING:`` are absent at runtime, so
``get_type_hints()`` raises ``NameError`` regardless of ``localns``::

    if TYPE_CHECKING:
        from heavy_module import HeavyType

    @factory()
    def make() -> HeavyType: ...

Fix: substitute ``Any`` for each unresolvable name and retry. The exact
type is irrelevant for DI dispatch — only the ``Use(...)``/``From(...)``
marker inside ``Annotated[...]`` is consulted at injection time.
"""

from __future__ import annotations

import contextlib
import inspect
import re
from typing import Any, get_type_hints


def get_type_hints_compat(func: Any) -> dict[str, Any]:
    """Resolve type hints with PEP 563 / TYPE_CHECKING fallbacks.

    See module docstring for the failure modes this function exists to
    handle. Cascade: (1) plain call, (2) retry with stack-collected
    ``localns``, (3) retry while substituting ``Any`` for unresolvable
    names. All fallbacks run at registration time only.
    """
    with contextlib.suppress(Exception):
        return get_type_hints(func, include_extras=True)

    # Build a namespace from the entire call stack so that locals from
    # an enclosing helper (e.g. `source = ForEach(...)`) become visible
    # to `get_type_hints`'s eval. See module docstring, failure mode 1.
    localns: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        for frame_info in inspect.stack():
            localns.update(frame_info.frame.f_locals)

    with contextlib.suppress(Exception):
        return get_type_hints(func, localns=localns, include_extras=True)

    # Last resort for TYPE_CHECKING-only types. See module docstring,
    # failure mode 2.
    return _get_type_hints_substituting_any(func, localns)


def _get_type_hints_substituting_any(
    func: Any,
    localns: dict[str, Any],
) -> dict[str, Any]:
    """Retry ``get_type_hints``, replacing each NameError'd name with ``Any``.

    Used as a last-resort fallback when a referenced type is unresolvable
    at runtime (typically a TYPE_CHECKING-only import). The substituted
    ``Any`` is only used as a placeholder so resolution can complete; the
    DI system reads the ``Use(...)``/``From(...)`` marker out of the
    ``Annotated[...]``, not the underlying type.
    """
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
