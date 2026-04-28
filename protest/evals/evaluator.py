"""Evaluator primitives.

An evaluator is a function decorated with ``@evaluator`` that receives an
``EvalContext`` and returns a verdict. The decorator wraps the function in an
``Evaluator`` instance that carries identity (for hashing/history) and exposes
two distinct entry points:

- ``ev(keyword=value, ...)`` — bind params, return a new ``Evaluator``
- ``ev.run(ctx)`` — execute against an ``EvalContext`` (called by the framework)

Plain callables are not accepted in ``evaluators=[...]``; use ``@evaluator``::

    @evaluator
    def contains_keywords(ctx: EvalContext, keywords: list[str]) -> ContainsKeywordsResult:
        found = sum(1 for k in keywords if k.lower() in ctx.output.lower())
        return ContainsKeywordsResult(keyword_recall=found / len(keywords), ...)

    # Bind params → returns a fresh Evaluator with kwargs frozen in.
    evaluators=[contains_keywords(keywords=["paris", "france"])]

    # No params → use the bare Evaluator directly.
    @evaluator
    def not_empty(ctx: EvalContext) -> bool:
        return bool(ctx.output.strip())

Async evaluators are supported::

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

import dataclasses
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Generic,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)

from protest.evals.hashing import _canonical
from protest.evals.types import EvalScore

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.evals.types import Judge

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
T = TypeVar("T")


@dataclass
class EvalContext(Generic[InputT, OutputT]):
    """Context passed to evaluator functions.

    Dual role: read-only DTO (inputs, output, expected) + mutable accumulator
    for judge call stats (tokens, cost, call count). One instance per case,
    shared sequentially across evaluators, discarded after scoring.

    Note: judge stats accumulate via ctx.judge() side-effects. If evaluators
    are ever parallelized within a case, the accumulators will need isolation.
    """

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
                "judge is configured. Pass judge= to EvalSuite()."
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

    `name` is required: it identifies the case across history, reporting, and
    file-based output. Two cases sharing a name collide silently in those
    downstream consumers.

    Usage::

        cases = ForEach([
            EvalCase(inputs="Who is Marie?", name="marie_lookup", expected="Marie, Resistance"),
            EvalCase(inputs="Who is Pierre?", name="pierre_lookup", expected="Pierre, arrest"),
        ])

        @suite.eval(evaluators=[contains_facts])
        def my_eval(case: Annotated[EvalCase, From(cases)]) -> str:
            return ask(case.inputs)
    """

    inputs: Any
    name: str
    expected: Any = None
    evaluators: list[Any] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError(
                "EvalCase.name must be a non-empty string "
                "(used for history tracking and case identity)."
            )
        validate_evaluators(self.evaluators)

    def __repr__(self) -> str:
        return self.name


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

    def __init__(self, evaluators: list[Evaluator]) -> None:
        validate_evaluators(evaluators, _inside_short_circuit=True)
        self.evaluators = evaluators

    def evaluator_identity(self) -> dict[str, Any]:
        """Identity is the ordered list of inner evaluators."""
        return {"short_circuit": [_canonical(e) for e in self.evaluators]}


def validate_evaluators(
    items: list[Any], *, _inside_short_circuit: bool = False
) -> None:
    """Reject anything that isn't a registered Evaluator (or ShortCircuit).

    ``@evaluator`` is the only sanctioned path to producing an evaluator. Plain
    callables used to be accepted, which forced a runtime ``isinstance`` dispatch
    in the executor and made the evaluators list type effectively ``list[Any]``.
    Failing loud at registration moves the error to the boundary and lets
    downstream code work on a uniform ``Evaluator | ShortCircuit`` Union.
    """
    for item in items:
        if isinstance(item, Evaluator):
            continue
        if isinstance(item, ShortCircuit) and not _inside_short_circuit:
            continue
        if _inside_short_circuit and isinstance(item, ShortCircuit):
            raise TypeError(
                "ShortCircuit cannot nest another ShortCircuit; "
                "flatten the inner evaluators into the outer group."
            )
        if callable(item):
            raise TypeError(
                f"{item!r} is a plain callable, not an Evaluator. "
                "Wrap it with @evaluator (from protest.evals) so it carries "
                "identity, hashing, and a typed run() method."
            )
        raise TypeError(
            f"Expected Evaluator or ShortCircuit, got {type(item).__name__}. "
            "Only objects produced by @evaluator (or ShortCircuit groups) "
            "are accepted in evaluators=[...]."
        )


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


class Evaluator:
    """A configured evaluator — callable with identity for hashing.

    Created by the ``@evaluator`` decorator. Two distinct entry points:

    - ``ev(keyword=value, ...)`` — bind params, return a new Evaluator
    - ``ev.run(ctx)`` — execute against an EvalContext

    Splitting these avoids the "callable that does two things based on the
    type of arg[0]" anti-pattern: each method has a single, monomorphic
    signature that type checkers can read without overload gymnastics.
    """

    __slots__ = ("_fn", "_kwargs", "_name", "_qualname")

    def __init__(
        self, fn: Callable[..., Any], kwargs: dict[str, Any] | None = None
    ) -> None:
        self._fn = fn
        self._kwargs = kwargs or {}
        self._name = fn.__name__
        self._qualname = fn.__qualname__

    @property
    def name(self) -> str:
        return self._name

    def __call__(self, **kwargs: Any) -> Evaluator:
        # Re-binding form: always returns a fresh clone. Returning `self`
        # for the no-kwargs case used to make `f is f()` accidentally true,
        # which surprised users expecting `()` to behave like a constructor.
        return Evaluator(self._fn, {**self._kwargs, **kwargs})

    def run(self, ctx: EvalContext[Any, Any], /) -> Any:
        return self._fn(ctx, **self._kwargs)

    def evaluator_identity(self) -> dict[str, Any]:
        identity: dict[str, Any] = {"fn": self._qualname}
        if self._kwargs:
            identity["kwargs"] = self._kwargs
        return identity

    def __repr__(self) -> str:
        if self._kwargs:
            kw = ", ".join(f"{k}={v!r}" for k, v in self._kwargs.items())
            return f"Evaluator({self._name}({kw}))"
        return f"Evaluator({self._name})"


def evaluator(fn: Callable[..., Any]) -> Evaluator:
    """Turn a function into a ProTest evaluator.

    The decorator is the only sanctioned way to produce an object that
    ``evaluators=[...]`` will accept. Plain callables are rejected at
    registration so the executor can rely on a uniform Union type instead
    of dispatching at runtime.
    """
    return Evaluator(fn)
