"""Tests for score namespacing and `ScoreNameCollisionError`.

Dataclass scores are namespaced per evaluator (``<evaluator>.<field>``),
so two evaluators on the same case can both declare plain ``ok`` /
``detail`` fields. A collision is still possible - and raises - when the
same evaluator name appears twice on one case (the same ``@evaluator``
attached twice, e.g. rebound with different kwargs).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated

import pytest

from protest import ForEach, From, ProTestSession
from protest.evals import (
    EvalCase,
    EvalContext,
    EvalSuite,
    Reason,
    Verdict,
    evaluator,
)
from protest.evals.wrapper import make_eval_wrapper
from protest.exceptions import ScoreNameCollisionError

_cases = ForEach([EvalCase(inputs="x", name="c1")])


@dataclass
class _ShapeA:
    matches: Annotated[bool, Verdict]
    detail: Annotated[str, Reason] = ""


@dataclass
class _ShapeB:
    other_check: Annotated[bool, Verdict]
    detail: Annotated[str, Reason] = ""  # same field name as _ShapeA - fine


@evaluator
def _shape_a(ctx: EvalContext) -> _ShapeA:
    return _ShapeA(matches=True, detail="from A")


@evaluator
def _shape_b(ctx: EvalContext) -> _ShapeB:
    return _ShapeB(other_check=True, detail="from B")


@evaluator
def _bool_one(ctx: EvalContext) -> bool:
    return True


@dataclass
class _ShapeWithBoolOneField:
    _bool_one: Annotated[bool, Verdict]  # namespaced - no clash with _bool_one


@evaluator
def _shape_with_bool_one_field(ctx: EvalContext) -> _ShapeWithBoolOneField:
    return _ShapeWithBoolOneField(_bool_one=True)


@evaluator
def _threshold(ctx: EvalContext, limit: int = 0) -> bool:
    return len(str(ctx.output)) >= limit


async def _invoke(evaluators: list, case: EvalCase):
    """Invoke the eval wrapper directly so collision exceptions propagate."""

    def task(case: EvalCase) -> str:
        return str(case.inputs)

    wrapped = make_eval_wrapper(task, evaluators)
    return await wrapped(case=case)


class TestNamespacing:
    def test_shared_field_names_do_not_collide(self) -> None:
        payload = asyncio.run(
            _invoke([_shape_a, _shape_b], EvalCase(inputs="x", name="c1"))
        )
        assert "_shape_a.detail" in payload.scores
        assert "_shape_b.detail" in payload.scores
        assert "_shape_a.matches" in payload.scores
        assert "_shape_b.other_check" in payload.scores

    def test_bool_evaluator_keeps_bare_name(self) -> None:
        payload = asyncio.run(_invoke([_bool_one], EvalCase(inputs="x", name="c1")))
        assert "_bool_one" in payload.scores

    def test_bool_name_does_not_clash_with_namespaced_field(self) -> None:
        payload = asyncio.run(
            _invoke(
                [_bool_one, _shape_with_bool_one_field],
                EvalCase(inputs="x", name="c2"),
            )
        )
        assert "_bool_one" in payload.scores
        assert "_shape_with_bool_one_field._bool_one" in payload.scores


class TestCollisionRaises:
    def test_same_bool_evaluator_twice(self) -> None:
        with pytest.raises(ScoreNameCollisionError) as excinfo:
            asyncio.run(
                _invoke([_bool_one, _bool_one], EvalCase(inputs="x", name="c1"))
            )
        msg = str(excinfo.value)
        assert "_bool_one" in msg
        assert "c1" in msg

    def test_same_evaluator_rebound_with_different_kwargs(self) -> None:
        # Rebinding keeps the function's name, so both emit '_threshold'.
        with pytest.raises(ScoreNameCollisionError) as excinfo:
            asyncio.run(
                _invoke(
                    [_threshold(limit=1), _threshold(limit=100)],
                    EvalCase(inputs="x", name="c2"),
                )
            )
        msg = str(excinfo.value)
        assert "_threshold" in msg
        assert "c2" in msg

    def test_same_dataclass_evaluator_twice(self) -> None:
        with pytest.raises(ScoreNameCollisionError) as excinfo:
            asyncio.run(_invoke([_shape_a, _shape_a], EvalCase(inputs="x", name="c3")))
        msg = str(excinfo.value)
        assert "_shape_a" in msg
        assert "c3" in msg

    def test_collision_detected_before_any_evaluator_runs(self) -> None:
        """The name check fires pre-execution - no evaluator (judge) call is made."""
        calls: list[str] = []

        @evaluator
        def _counting(ctx: EvalContext) -> bool:
            calls.append("ran")
            return True

        with pytest.raises(ScoreNameCollisionError):
            asyncio.run(
                _invoke([_counting, _counting], EvalCase(inputs="x", name="c4"))
            )
        assert calls == []

    def test_collision_inside_short_circuit_detected(self) -> None:
        from protest.evals import ShortCircuit  # noqa: PLC0415

        with pytest.raises(ScoreNameCollisionError):
            asyncio.run(
                _invoke(
                    [_bool_one, ShortCircuit([_bool_one])],
                    EvalCase(inputs="x", name="c5"),
                )
            )


class TestSkippedPlaceholderNamespacing:
    """Short-circuited evaluators emit placeholders under the same keys a
    real run would produce, so score keys are stable across runs."""

    def test_skipped_dataclass_evaluator_keeps_namespaced_keys(self) -> None:
        from protest.evals import ShortCircuit  # noqa: PLC0415

        @evaluator
        def _gate(ctx: EvalContext) -> bool:
            return False  # always short-circuits

        payload = asyncio.run(
            _invoke(
                [ShortCircuit([_gate, _shape_a])],
                EvalCase(inputs="x", name="c1"),
            )
        )
        assert "_shape_a.matches" in payload.scores
        assert "_shape_a.detail" in payload.scores
        assert payload.scores["_shape_a.matches"].skipped is True
        # Bare evaluator name must NOT appear - that was the pre-namespacing key.
        assert "_shape_a" not in payload.scores

    def test_skipped_bool_evaluator_keeps_bare_name(self) -> None:
        from protest.evals import ShortCircuit  # noqa: PLC0415

        @evaluator
        def _gate(ctx: EvalContext) -> bool:
            return False

        payload = asyncio.run(
            _invoke(
                [ShortCircuit([_gate, _bool_one])],
                EvalCase(inputs="x", name="c1"),
            )
        )
        assert "_bool_one" in payload.scores
        assert payload.scores["_bool_one"].skipped is True


class TestSessionPath:
    def test_session_with_shared_field_names_runs_clean(self) -> None:
        """Smoke check: shared `detail` fields pass through the full session."""
        from protest.api import run_session  # noqa: PLC0415 - heavy import

        session = ProTestSession()
        suite = EvalSuite("evals")

        @suite.eval(evaluators=[_shape_a, _shape_b])
        def ok(case: Annotated[EvalCase, From(_cases)]) -> str:
            return str(case.inputs)

        _ = ok
        session.add_suite(suite)
        result = run_session(session)
        assert result.success
