"""Validation that evaluators=[...] only accepts @evaluator-wrapped objects.

Plain callables and arbitrary values used to be silently accepted, forcing a
runtime ``isinstance`` dispatch in the executor. Validating at the boundary
turns the failure into a clear TypeError at registration time and lets the
downstream code work on a uniform ``Evaluator | ShortCircuit`` Union.
"""

from __future__ import annotations

import pytest

from protest.evals.evaluator import (
    EvalCase,
    EvalContext,
    ShortCircuit,
    evaluator,
    validate_evaluators,
)


@evaluator
def _ok(ctx: EvalContext) -> bool:
    return True


def _plain_callable(ctx: EvalContext) -> bool:
    return True


class TestValidateEvaluators:
    def test_accepts_evaluator(self) -> None:
        validate_evaluators([_ok])

    def test_accepts_short_circuit(self) -> None:
        validate_evaluators([ShortCircuit([_ok])])

    def test_rejects_plain_callable(self) -> None:
        with pytest.raises(TypeError, match="@evaluator"):
            validate_evaluators([_plain_callable])

    def test_rejects_non_callable(self) -> None:
        with pytest.raises(TypeError, match="Expected Evaluator or ShortCircuit"):
            validate_evaluators(["not_an_evaluator"])  # type: ignore[list-item]

    def test_rejects_nested_short_circuit(self) -> None:
        with pytest.raises(TypeError, match="cannot nest"):
            ShortCircuit([ShortCircuit([_ok])])  # type: ignore[list-item]


class TestEvalCaseValidates:
    def test_evalcase_rejects_plain_callable(self) -> None:
        with pytest.raises(TypeError, match="@evaluator"):
            EvalCase(inputs="x", name="c", evaluators=[_plain_callable])

    def test_evalcase_accepts_evaluator(self) -> None:
        EvalCase(inputs="x", name="c", evaluators=[_ok])
