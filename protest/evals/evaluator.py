"""Evaluator primitives — functions, not classes.

An evaluator is a callable that receives an EvalContext and returns a score.
The @evaluator decorator adds partial-application ergonomics:

    @evaluator
    def contains_keywords(ctx: EvalContext, keywords: list[str]) -> ContainsKeywordsResult:
        found = sum(1 for k in keywords if k.lower() in ctx.output.lower())
        return ContainsKeywordsResult(keyword_recall=found / len(keywords), ...)

    # Bind params → returns a callable(ctx) via functools.partial
    evaluators=[contains_keywords(keywords=["paris", "france"])]

    # No params → use directly
    @evaluator
    def not_empty(ctx: EvalContext) -> bool:
        return bool(ctx.output.strip())

Async evaluators are supported:

    @evaluator
    async def llm_judge(ctx: EvalContext, model: str = "haiku") -> bool:
        ...

Evaluators return either bool (simple verdict) or a dataclass (structured result).
The framework reads fields by type:
- bool → verdict (pass/fail = all(bool_fields))
- float → metric (aggregated in stats)
- str → reason (displayed on failure)
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

I = TypeVar("I")
O = TypeVar("O")


@dataclass
class EvalContext(Generic[I, O]):
    """Context passed to evaluator functions."""

    name: str
    inputs: I
    output: O
    expected_output: O | None
    metadata: Any
    duration: float


@dataclass
class EvalCase:
    """Typed container for eval case data in ForEach.

    Usage::

        cases = ForEach([
            EvalCase(inputs="Who is Marie?", expected="Marie, Resistance", name="lookup"),
            EvalCase(inputs="Who is Pierre?", expected="Pierre, arrest"),
        ])

        @session.eval(evaluators=[contains_facts])
        def my_eval(case: Annotated[EvalCase, From(cases)]) -> str:
            return ask(case.inputs)
    """

    inputs: Any
    expected: Any = None
    name: str = ""
    evaluators: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return self.name or f"EvalCase({self.inputs!r})"


class Metric:
    """Annotate a float/int field as a metric for stats aggregation."""


class Verdict:
    """Annotate a bool field as a verdict for pass/fail."""


class Reason:
    """Annotate a str field as a reason displayed on failure."""


def extract_scores_from_result(result: Any, evaluator_name: str) -> list[Any]:
    """Extract EvalScore instances from an evaluator result.

    For bool returns: a single verdict named after the evaluator.
    For dataclass returns: only fields annotated with Metric/Verdict/Reason
    are extracted. Unannotated fields are ignored (free metadata).

    Raises:
        TypeError: If result is not bool or dataclass.
    """
    from typing import Annotated, get_args, get_origin, get_type_hints

    from protest.evals.types import EvalScore

    if isinstance(result, bool):
        return [EvalScore(name=evaluator_name, value=result)]

    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        scores = []
        hints = get_type_hints(type(result), include_extras=True)
        for f in dataclasses.fields(result):
            ann = hints.get(f.name)
            if ann is None or get_origin(ann) is not Annotated:
                continue
            for meta in get_args(ann)[1:]:
                if isinstance(meta, type) and issubclass(meta, (Metric, Verdict, Reason)):
                    scores.append(EvalScore(name=f.name, value=getattr(result, f.name)))
                    break
        return scores

    type_name = type(result).__name__
    raise TypeError(
        f"Evaluator must return bool or dataclass, got {type_name}"
    )


def evaluator(fn: Any) -> Any:
    """Decorator that turns a function into a protest evaluator.

    The decorated function can be called two ways:

    1. ``evaluator_fn(ctx)`` — evaluate directly
    2. ``evaluator_fn(keyword=value, ...)`` — returns a bound evaluator (partial)

    This is just ``functools.partial`` with nicer ergonomics: when the first
    positional argument is an ``EvalContext``, the function evaluates. Otherwise,
    all arguments are bound and the result is a new callable expecting only ``ctx``.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    has_extra_params = len(params) > 1

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Direct call: first positional arg is an EvalContext
        if args and isinstance(args[0], EvalContext):
            return fn(*args, **kwargs)
        # Bind params → return partial
        if has_extra_params and kwargs:
            bound = functools.partial(fn, **kwargs)
            # Preserve async detection on the partial
            bound._is_async_evaluator = asyncio.iscoroutinefunction(fn)  # type: ignore[attr-defined]
            bound.__name__ = fn.__name__  # type: ignore[attr-defined]
            bound.__qualname__ = fn.__qualname__  # type: ignore[attr-defined]
            return bound
        # No args at all — if no extra params, this IS the evaluator
        if not has_extra_params and not args and not kwargs:
            return fn
        return fn(*args, **kwargs)

    wrapper._is_evaluator = True  # type: ignore[attr-defined]
    wrapper._is_async_evaluator = asyncio.iscoroutinefunction(fn)  # type: ignore[attr-defined]
    return wrapper


def is_async_evaluator(fn: Any) -> bool:
    """Check if an evaluator (or partial thereof) is async."""
    if hasattr(fn, "_is_async_evaluator"):
        return fn._is_async_evaluator
    if isinstance(fn, functools.partial):
        return asyncio.iscoroutinefunction(fn.func)
    return asyncio.iscoroutinefunction(fn)
