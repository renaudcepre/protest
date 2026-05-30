"""Tests for `EvalCase` construction invariants."""

from __future__ import annotations

import pytest

from protest.evals import EvalCase


class TestEvalCaseRequiresName:
    """`name` is required and must be non-empty."""

    def test_name_required_as_kwarg(self) -> None:
        case = EvalCase(inputs="x", name="my_case")
        assert case.name == "my_case"

    def test_missing_name_raises(self) -> None:
        with pytest.raises(TypeError):
            EvalCase(inputs="x")  # type: ignore[call-arg]

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            EvalCase(inputs="x", name="")

    def test_name_is_second_positional(self) -> None:
        case = EvalCase("input_val", "case_name")
        assert case.inputs == "input_val"
        assert case.name == "case_name"


class TestEvalCaseRepr:
    """`__repr__` returns the name (no fallback anymore since name is required)."""

    def test_repr_is_name(self) -> None:
        case = EvalCase(inputs="x", name="readable_name")
        assert repr(case) == "readable_name"
