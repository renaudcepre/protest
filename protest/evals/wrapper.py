"""Eval wrapper — turns a function into a scored eval test.

The wrapper intercepts the return value, runs evaluators, and returns
an EvalPayload. The rest of the pipeline (executor, outcome builder,
reporters) handles it like any eval test.
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

from protest.entities.events import EvalPayload, EvalScoreEntry
from protest.evals.evaluator import (
    EvalCase,
    EvalContext,
    ShortCircuit,
    extract_scores_from_result,
)
from protest.evals.hashing import compute_case_hash, compute_eval_hash
from protest.evals.types import EvalScore, TaskResult
from protest.exceptions import FixtureError


def make_eval_wrapper(
    func: Any,
    evaluators: list[Any],
    judge: Any = None,
) -> Any:
    """Wrap a function to run evaluators on its return value."""

    @functools.wraps(func)
    async def eval_wrapper(**kwargs: Any) -> EvalPayload:
        expected = _extract_expected(kwargs)
        case_name = _extract_case_name(kwargs, func.__name__)
        inputs = _extract_inputs(kwargs)
        metadata = _extract_metadata(kwargs)

        start = time.perf_counter()
        if asyncio.iscoroutinefunction(func):
            raw_output = await func(**kwargs)
        else:
            raw_output = func(**kwargs)
        task_duration = time.perf_counter() - start

        # Unwrap TaskResult if returned
        task_input_tokens = 0
        task_output_tokens = 0
        task_cost = 0.0
        if isinstance(raw_output, TaskResult):
            output = raw_output.output
            task_input_tokens = raw_output.input_tokens or 0
            task_output_tokens = raw_output.output_tokens or 0
            task_cost = raw_output.cost or 0.0
        else:
            output = raw_output

        all_evaluators = list(evaluators)
        per_case = _extract_per_case_evaluators(kwargs)
        all_evaluators.extend(per_case)

        scores, eval_ctx = await run_evaluators(
            all_evaluators,
            case_name,
            inputs,
            output,
            expected,
            metadata,
            task_duration,
            judge=judge,
        )

        return EvalPayload(
            case_name=case_name,
            passed=all(s.passed for s in scores),
            task_duration=task_duration,
            inputs=inputs,
            output=output,
            expected_output=expected,
            scores={
                s.name: EvalScoreEntry(
                    value=s.value,
                    passed=s.passed,
                    skipped=s.skipped,
                )
                for s in scores
            },
            case_hash=compute_case_hash(inputs, expected),
            eval_hash=compute_eval_hash(all_evaluators),
            task_input_tokens=task_input_tokens,
            task_output_tokens=task_output_tokens,
            task_cost=task_cost,
            judge_call_count=eval_ctx.judge_call_count,
            judge_input_tokens=eval_ctx.judge_input_tokens,
            judge_output_tokens=eval_ctx.judge_output_tokens,
            judge_cost=eval_ctx.judge_cost,
        )

    return eval_wrapper


# ---------------------------------------------------------------------------
# Extract helpers — pull EvalCase from kwargs
# ---------------------------------------------------------------------------


def _find_case(kwargs: dict[str, Any]) -> EvalCase | None:
    """Find the EvalCase instance in kwargs."""
    for v in kwargs.values():
        if isinstance(v, EvalCase):
            return v
    return None


def _extract_expected(kwargs: dict[str, Any]) -> Any:
    case = _find_case(kwargs)
    if case is None:
        return None
    return case.expected


def _extract_case_name(kwargs: dict[str, Any], fallback: str) -> str:
    case = _find_case(kwargs)
    if case is None or not case.name:
        return fallback
    return case.name


def _extract_inputs(kwargs: dict[str, Any]) -> Any:
    case = _find_case(kwargs)
    if case is None:
        return None
    return case.inputs


def _extract_metadata(kwargs: dict[str, Any]) -> Any:
    case = _find_case(kwargs)
    if case is None:
        return None
    return case.metadata or None


def _extract_per_case_evaluators(kwargs: dict[str, Any]) -> list[Any]:
    case = _find_case(kwargs)
    if case is None or not case.evaluators:
        return []
    return list(case.evaluators)


# ---------------------------------------------------------------------------
# Evaluator execution
# ---------------------------------------------------------------------------


async def run_evaluators(
    evaluators: list[Any],
    case_name: str,
    inputs: Any,
    output: Any,
    expected_output: Any,
    metadata: Any,
    duration: float,
    judge: Any = None,
) -> tuple[list[EvalScore], EvalContext[Any, Any]]:
    """Run evaluators and return (scores, ctx with judge stats)."""
    ctx = EvalContext(
        name=case_name,
        inputs=inputs,
        output=output,
        expected_output=expected_output,
        metadata=metadata,
        duration=duration,
        _judge=judge,
    )

    scores: list[EvalScore] = []
    for ev in evaluators:
        if isinstance(ev, ShortCircuit):
            scores.extend(await _run_short_circuit(ev.evaluators, ctx))
            continue

        evaluator_name = getattr(ev, "__name__", type(ev).__name__)
        try:
            raw = ev(ctx)
            result = await raw if asyncio.iscoroutine(raw) else raw
            scores.extend(extract_scores_from_result(result, evaluator_name))
        except Exception as exc:
            raise FixtureError(f"evaluator '{evaluator_name}'", exc) from exc

    return scores, ctx


async def _run_short_circuit(
    evaluators: list[Any],
    ctx: EvalContext[Any, Any],
) -> list[EvalScore]:
    """Run evaluators in order, stop at first Verdict=False."""
    scores: list[EvalScore] = []
    for i, ev in enumerate(evaluators):
        evaluator_name = getattr(ev, "__name__", type(ev).__name__)
        try:
            raw = ev(ctx)
            result = await raw if asyncio.iscoroutine(raw) else raw
        except Exception as exc:
            raise FixtureError(f"evaluator '{evaluator_name}'", exc) from exc
        extracted = extract_scores_from_result(result, evaluator_name)
        scores.extend(extracted)
        if any(s.is_verdict and not s.passed for s in extracted):
            # Mark remaining evaluators as skipped
            for skipped_ev in evaluators[i + 1 :]:
                skipped_name = getattr(
                    skipped_ev, "__name__", type(skipped_ev).__name__
                )
                scores.append(EvalScore(name=skipped_name, value=False, skipped=True))
            break
    return scores
