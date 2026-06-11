"""Tests for `NoEvaluatorsError` - fail loud on the zero-evaluators trap.

`passed` is `all(s.passed for s in scores)` and `all([])` is `True`: an
eval that ends up with no evaluators at runtime would always pass,
hiding wiring mistakes. The guard runs at execution time because
per-case evaluators are only known then.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import pytest

from protest import ForEach, From, ProTestSession
from protest.evals import (
    EvalCase,
    EvalContext,
    EvalSuite,
    ShortCircuit,
    evaluator,
)
from protest.evals.wrapper import make_eval_wrapper
from protest.exceptions import NoEvaluatorsError


@evaluator
def _ok(ctx: EvalContext) -> bool:
    return True


async def _invoke(evaluators: list, case: EvalCase):
    def task(case: EvalCase) -> str:
        return str(case.inputs)

    wrapped = make_eval_wrapper(task, evaluators)
    return await wrapped(case=case)


class TestNoEvaluatorsRaises:
    def test_empty_list_raises(self) -> None:
        with pytest.raises(NoEvaluatorsError) as excinfo:
            asyncio.run(_invoke([], EvalCase(inputs="x", name="c1")))
        assert "c1" in str(excinfo.value)

    def test_empty_short_circuit_rejected_at_construction(self) -> None:
        """ShortCircuit([]) would contribute zero evaluators - rejected
        even earlier, when the group is built."""
        with pytest.raises(ValueError, match="at least one evaluator"):
            ShortCircuit([])

    def test_session_path_fails_with_no_evaluators_error(self) -> None:
        """Through the runner, the guard surfaces as a NoEvaluatorsError on
        the case, not a silently green session."""
        from protest.api import run_session  # noqa: PLC0415 - heavy import
        from protest.plugin import PluginBase  # noqa: PLC0415 - heavy import

        captured = []

        class Capture(PluginBase):
            name = "capture"

            def on_test_fail(self, result) -> None:
                captured.append(result)

        cases = ForEach([EvalCase(inputs="x", name="c1")])
        session = ProTestSession()
        session.register_plugin(Capture())
        suite = EvalSuite("evals")

        @suite.eval()
        def forgot_evaluators(case: Annotated[EvalCase, From(cases)]) -> str:
            return str(case.inputs)

        # Twin eval with an evaluator: must stay green, proving the
        # failure below is the guard and not collateral wiring breakage.
        @suite.eval(evaluators=[_ok])
        def wired_correctly(case: Annotated[EvalCase, From(cases)]) -> str:
            return str(case.inputs)

        _ = forgot_evaluators, wired_correctly
        session.add_suite(suite)
        result = run_session(session)
        assert result.success is False
        assert len(captured) == 1
        assert isinstance(captured[0].error, NoEvaluatorsError)
        assert "no evaluators" in str(captured[0].error)


class TestEvaluatorsPresentPasses:
    def test_suite_level_evaluator_passes_guard(self) -> None:
        payload = asyncio.run(_invoke([_ok], EvalCase(inputs="x", name="c1")))
        assert "_ok" in payload.scores

    def test_per_case_evaluators_satisfy_guard(self) -> None:
        """Empty suite-level list is fine when the case brings its own."""
        case = EvalCase(inputs="x", name="c1", evaluators=[_ok])
        payload = asyncio.run(_invoke([], case))
        assert "_ok" in payload.scores
