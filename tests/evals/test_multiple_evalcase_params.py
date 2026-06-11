"""Tests for `_validate_single_evalcase_param` - D1 registration-time check.

The runtime contract (`_find_case`) picks the first `EvalCase` in kwargs and
silently drops any others. The wrapper detects > 1 EvalCase param at
registration and raises a clear error pointing at the offending parameters.
"""

from __future__ import annotations

from typing import Annotated

import pytest

from protest import ForEach, From, ProTestSession
from protest.evals import EvalCase
from protest.evals.suite import EvalSuite
from protest.exceptions import MultipleEvalCaseParamsError

# Module-level case sources so `get_type_hints()` can resolve Annotated args.
_cases_a = ForEach([EvalCase(inputs="a", name="a1")])
_cases_b = ForEach([EvalCase(inputs="b", name="b1")])


class _MyCase(EvalCase):
    """Subclass to verify the check covers user-defined EvalCase types."""


_subclass_cases = ForEach([_MyCase(inputs="x", name="x1")])


class TestSingleEvalCaseParamAccepted:
    def test_one_evalcase_param_via_annotated_from(self) -> None:
        session = ProTestSession()
        suite = EvalSuite("evals")

        @suite.eval()
        def good(case: Annotated[EvalCase, From(_cases_a)]) -> str:
            return str(case.inputs)

        _ = good
        session.add_suite(suite)  # no raise

    def test_zero_evalcase_param_accepted(self) -> None:
        """Evals without parametrization (or without EvalCase) are valid."""
        session = ProTestSession()
        suite = EvalSuite("evals")

        @suite.eval()
        def no_case() -> str:
            return "static"

        _ = no_case
        session.add_suite(suite)  # no raise

    def test_subclass_param_accepted_when_alone(self) -> None:
        session = ProTestSession()
        suite = EvalSuite("evals")

        @suite.eval()
        def good(case: Annotated[_MyCase, From(_subclass_cases)]) -> str:
            return str(case.inputs)

        _ = good
        session.add_suite(suite)


class TestMultipleEvalCaseParamRejected:
    def test_two_evalcase_params_raise(self) -> None:
        suite = EvalSuite("evals")

        with pytest.raises(MultipleEvalCaseParamsError) as excinfo:

            @suite.eval()
            def bad(
                case_a: Annotated[EvalCase, From(_cases_a)],
                case_b: Annotated[EvalCase, From(_cases_b)],
            ) -> str:
                return f"{case_a.inputs}+{case_b.inputs}"

        msg = str(excinfo.value)
        assert "bad" in msg
        assert "case_a" in msg
        assert "case_b" in msg

    def test_subclass_counts_as_evalcase(self) -> None:
        """A param typed `_MyCase` (subclass) collides with a `EvalCase` param."""
        suite = EvalSuite("evals")

        with pytest.raises(MultipleEvalCaseParamsError) as excinfo:

            @suite.eval()
            def bad(
                case_a: Annotated[EvalCase, From(_cases_a)],
                case_b: Annotated[_MyCase, From(_subclass_cases)],
            ) -> str:
                return str(case_a.inputs) + str(case_b.inputs)

        assert "case_a" in str(excinfo.value)
        assert "case_b" in str(excinfo.value)
