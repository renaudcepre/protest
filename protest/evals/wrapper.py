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
from protest.evals.evaluator import EvalContext, ShortCircuit, extract_scores_from_result
from protest.evals.types import EvalScore


def make_eval_wrapper(
    func: Any,
    evaluators: list[Any],
    expected_key: str,
) -> Any:
    """Wrap a function to run evaluators on its return value."""

    @functools.wraps(func)
    async def eval_wrapper(**kwargs: Any) -> EvalPayload:
        expected = _extract_expected(kwargs, expected_key)
        case_name = _extract_case_name(kwargs, func.__name__)
        inputs = _extract_inputs(kwargs)
        metadata = _extract_metadata(kwargs)

        start = time.perf_counter()
        if asyncio.iscoroutinefunction(func):
            output = await func(**kwargs)
        else:
            output = func(**kwargs)
        task_duration = time.perf_counter() - start

        all_evaluators = list(evaluators)
        per_case = _extract_per_case_evaluators(kwargs)
        all_evaluators.extend(per_case)

        scores = await run_evaluators(
            all_evaluators,
            case_name,
            inputs,
            output,
            expected,
            metadata,
            task_duration,
        )

        from protest.evals.hashing import compute_case_hash, compute_eval_hash

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
        )

    return eval_wrapper


# ---------------------------------------------------------------------------
# Extract helpers — pull data from case_kwargs (dict or dataclass)
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Get a value from a dict or dataclass by key/attr name."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _is_case_data(v: Any) -> bool:
    """Check if a value looks like case data (dict or has 'expected'/'q'/'inputs')."""
    if isinstance(v, dict):
        return True
    return hasattr(v, "expected") or hasattr(v, "q") or hasattr(v, "inputs")


def _extract_expected(kwargs: dict[str, Any], key: str) -> Any:
    for v in kwargs.values():
        if _is_case_data(v):
            val = _get(v, key)
            if val is not None:
                return val
    return None


def _extract_case_name(kwargs: dict[str, Any], fallback: str) -> str:
    for v in kwargs.values():
        if _is_case_data(v):
            name = _get(v, "name")
            if name:
                return name
    return fallback


def _extract_inputs(kwargs: dict[str, Any]) -> Any:
    for v in kwargs.values():
        if _is_case_data(v):
            return _get(v, "inputs") or _get(v, "q") or _get(v, "input")
    return None


def _extract_metadata(kwargs: dict[str, Any]) -> Any:
    for v in kwargs.values():
        if _is_case_data(v):
            val = _get(v, "metadata")
            if val is not None:
                return val
    return None


def _extract_per_case_evaluators(kwargs: dict[str, Any]) -> list[Any]:
    for v in kwargs.values():
        if _is_case_data(v):
            evs = _get(v, "evaluators")
            if evs:
                return list(evs)
    return []


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
) -> list[EvalScore]:
    """Run evaluators and convert results to EvalScores."""
    ctx = EvalContext(
        name=case_name,
        inputs=inputs,
        output=output,
        expected_output=expected_output,
        metadata=metadata,
        duration=duration,
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
            from protest.exceptions import FixtureError

            raise FixtureError(f"evaluator '{evaluator_name}'", exc) from exc

    return scores


async def _run_short_circuit(
    evaluators: list[Any], ctx: EvalContext[Any, Any],
) -> list[EvalScore]:
    """Run evaluators in order, stop at first Verdict=False."""
    scores: list[EvalScore] = []
    for i, ev in enumerate(evaluators):
        evaluator_name = getattr(ev, "__name__", type(ev).__name__)
        try:
            raw = ev(ctx)
            result = await raw if asyncio.iscoroutine(raw) else raw
        except Exception as exc:
            from protest.exceptions import FixtureError

            raise FixtureError(f"evaluator '{evaluator_name}'", exc) from exc
        extracted = extract_scores_from_result(result, evaluator_name)
        scores.extend(extracted)
        if any(s.is_verdict and not s.passed for s in extracted):
            # Mark remaining evaluators as skipped
            for skipped_ev in evaluators[i + 1 :]:
                skipped_name = getattr(skipped_ev, "__name__", type(skipped_ev).__name__)
                scores.append(EvalScore(name=skipped_name, value=False, skipped=True))
            break
    return scores
