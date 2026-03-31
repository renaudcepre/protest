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
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from protest.evals.types import Judge

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
T = TypeVar("T")


@dataclass
class EvalContext(Generic[InputT, OutputT]):
    """Context passed to evaluator functions."""

    name: str
    inputs: InputT
    output: OutputT
    expected_output: OutputT | None
    metadata: Any
    duration: float
    _judge: Judge | None = field(default=None, repr=False)
    _judge_call_count: int = field(default=0, repr=False, init=False)
    _judge_input_tokens: int = field(default=0, repr=False, init=False)
    _judge_output_tokens: int = field(default=0, repr=False, init=False)
    _judge_cost: float = field(default=0.0, repr=False, init=False)

    async def judge(self, prompt: str, output_type: type[T]) -> T:
        """Call the configured LLM judge and return the typed output.

        Tokens and cost from JudgeResponse are accumulated internally
        and flow to EvalPayload for history/display. The evaluator
        only sees the unwrapped output.

        Raises RuntimeError if no judge was configured on the session.
        """
        if self._judge is None:
            raise RuntimeError(
                f"Evaluator for case '{self.name}' called ctx.judge() but no "
                "judge is configured. Pass judge= to EvalSession()."
            )
        self._judge_call_count += 1
        response = await self._judge.judge(prompt, output_type)
        if response.input_tokens is not None:
            self._judge_input_tokens += response.input_tokens
        if response.output_tokens is not None:
            self._judge_output_tokens += response.output_tokens
        if response.cost is not None:
            self._judge_cost += response.cost
        return response.output

    @property
    def judge_call_count(self) -> int:
        return self._judge_call_count

    @property
    def judge_input_tokens(self) -> int:
        return self._judge_input_tokens

    @property
    def judge_output_tokens(self) -> int:
        return self._judge_output_tokens

    @property
    def judge_cost(self) -> float:
        return self._judge_cost


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


class ShortCircuit:
    """Group evaluators with fail-fast behavior.

    The first Verdict=False stops the group. Evaluators outside
    the ShortCircuit run regardless.

    Usage::

        evaluators=[
            not_empty,
            ShortCircuit([
                contains_expected_facts(min_score=0.5),
                llm_judge(rubric="..."),  # skipped if above fails
            ]),
        ]
    """

    def __init__(self, evaluators: list[Any]) -> None:
        self.evaluators = evaluators


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
                if isinstance(meta, type) and issubclass(
                    meta, (Metric, Verdict, Reason)
                ):
                    scores.append(EvalScore(name=f.name, value=getattr(result, f.name)))
                    break
        return scores

    type_name = type(result).__name__
    raise TypeError(f"Evaluator must return bool or dataclass, got {type_name}")


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
