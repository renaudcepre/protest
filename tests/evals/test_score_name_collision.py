"""Tests for `ScoreNameCollisionError` — fail-loud on duplicate score names.

Two evaluators emitting a score under the same name (e.g. both have a
``detail`` field on their dataclass return) would silently overwrite each
other in ``EvalPayload.scores`` (a dict). The wrapper detects the
collision at runtime and raises a clear error pointing at the duplicate
name(s) so the user can rename the colliding field.
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
    detail: Annotated[str, Reason] = ""  # collides with _ShapeA.detail


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
    _bool_one: Annotated[bool, Verdict]  # collides with _bool_one evaluator's name


@evaluator
def _shape_collides_with_bool(ctx: EvalContext) -> _ShapeWithBoolOneField:
    return _ShapeWithBoolOneField(_bool_one=True)


@dataclass
class _ShapeUniqueA:
    matches_a: Annotated[bool, Verdict]
    detail_a: Annotated[str, Reason] = ""


@dataclass
class _ShapeUniqueB:
    matches_b: Annotated[bool, Verdict]
    detail_b: Annotated[str, Reason] = ""


@evaluator
def _shape_unique_a(ctx: EvalContext) -> _ShapeUniqueA:
    return _ShapeUniqueA(matches_a=True, detail_a="A")


@evaluator
def _shape_unique_b(ctx: EvalContext) -> _ShapeUniqueB:
    return _ShapeUniqueB(matches_b=True, detail_b="B")


def _invoke(evaluators: list, case: EvalCase) -> None:
    """Invoke the eval wrapper directly so collision exceptions propagate."""

    def task(case: EvalCase) -> str:
        return str(case.inputs)

    wrapped = make_eval_wrapper(task, evaluators)
    asyncio.run(wrapped(case=case))


class TestCollisionRaises:
    def test_two_dataclasses_share_field_name(self) -> None:
        with pytest.raises(ScoreNameCollisionError) as excinfo:
            _invoke([_shape_a, _shape_b], EvalCase(inputs="x", name="c1"))
        msg = str(excinfo.value)
        assert "'detail'" in msg
        assert "c1" in msg

    def test_bool_evaluator_name_collides_with_dataclass_field(self) -> None:
        with pytest.raises(ScoreNameCollisionError) as excinfo:
            _invoke(
                [_bool_one, _shape_collides_with_bool],
                EvalCase(inputs="x", name="c2"),
            )
        msg = str(excinfo.value)
        assert "_bool_one" in msg
        assert "c2" in msg


class TestNoCollisionPasses:
    def test_unique_names_pass(self) -> None:
        # Should not raise.
        _invoke(
            [_shape_unique_a, _shape_unique_b],
            EvalCase(inputs="x", name="c1"),
        )

    def test_session_with_unique_names_runs_clean(self) -> None:
        """Smoke check: running through the full session path also succeeds."""
        from protest.api import run_session  # noqa: PLC0415 — heavy import

        session = ProTestSession()
        suite = EvalSuite("evals")

        @suite.eval(evaluators=[_shape_unique_a, _shape_unique_b])
        def ok(case: Annotated[EvalCase, From(_cases)]) -> str:
            return str(case.inputs)

        _ = ok
        session.add_suite(suite)
        result = run_session(session)
        assert result.success
