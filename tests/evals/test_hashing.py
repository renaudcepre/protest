"""Tests for protest.evals.hashing — fail-hard canonicalization."""

from __future__ import annotations

import dataclasses
import functools
import threading

import pytest

from protest.evals.hashing import (
    CanonicalError,
    _canonical,
    compute_case_hash,
    compute_eval_hash,
)

# ---------------------------------------------------------------------------
# Fixtures — representative evaluator types
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SimpleEvaluator:
    threshold: float
    name: str = "simple"


@dataclasses.dataclass
class NestedEvaluator:
    inner: SimpleEvaluator
    weight: float = 1.0


@dataclasses.dataclass
class LockHoldingEvaluator:
    """Simulates evaluators like LLMJudge that hold non-picklable resources."""

    name: str
    _lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)


def bare_function(ctx: object) -> bool:
    return True


def parameterized_function(ctx: object, keywords: list[str]) -> bool:
    return True


# ---------------------------------------------------------------------------
# _canonical — primitives & containers
# ---------------------------------------------------------------------------


class TestCanonicalPrimitives:
    @pytest.mark.parametrize("value", [None, True, False, 42, 3.14, "hello"])
    def test_primitives_pass_through(self, value: object) -> None:
        assert _canonical(value) is value

    def test_list(self) -> None:
        assert _canonical([1, "a", [2]]) == [1, "a", [2]]

    def test_tuple_treated_as_list(self) -> None:
        assert _canonical((1, 2)) == [1, 2]

    def test_dict_sorted_by_key(self) -> None:
        assert _canonical({"b": 2, "a": 1}) == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# _canonical — dataclass handling
# ---------------------------------------------------------------------------


class TestCanonicalDataclass:
    def test_simple_dataclass_is_serialized(self) -> None:
        ev = SimpleEvaluator(threshold=0.8)
        result = _canonical(ev)
        assert result == {
            "__type__": "SimpleEvaluator",
            "threshold": 0.8,
            "name": "simple",
        }

    def test_nested_dataclass_is_serialized_recursively(self) -> None:
        ev = NestedEvaluator(inner=SimpleEvaluator(threshold=0.5), weight=2.0)
        result = _canonical(ev)
        assert result == {
            "__type__": "NestedEvaluator",
            "inner": {
                "__type__": "SimpleEvaluator",
                "threshold": 0.5,
                "name": "simple",
            },
            "weight": 2.0,
        }

    def test_dataclass_with_lock_skips_private_fields(self) -> None:
        """Regression: dataclasses.asdict() deepcopy fails on threading.Lock.

        Private fields (_prefixed) are runtime internals, not config — excluded from hash.
        """
        ev = LockHoldingEvaluator(name="llm_judge")
        result = _canonical(ev)
        assert result == {"__type__": "LockHoldingEvaluator", "name": "llm_judge"}
        assert "_lock" not in result


# ---------------------------------------------------------------------------
# _canonical — callables (the real-world evaluator path)
# ---------------------------------------------------------------------------


class TestCanonicalCallable:
    def test_bare_function(self) -> None:
        result = _canonical(bare_function)
        assert result == {"fn": "bare_function"}

    def test_partial_captures_qualname_and_kwargs(self) -> None:
        bound = functools.partial(parameterized_function, keywords=["paris"])
        result = _canonical(bound)
        assert result == {
            "fn": "parameterized_function",
            "args": [],
            "kwargs": {"keywords": ["paris"]},
        }

    def test_partial_different_kwargs_different_canonical(self) -> None:
        a = functools.partial(parameterized_function, keywords=["paris"])
        b = functools.partial(parameterized_function, keywords=["lyon"])
        assert _canonical(a) != _canonical(b)

    def test_partial_same_kwargs_same_canonical(self) -> None:
        a = functools.partial(parameterized_function, keywords=["paris"])
        b = functools.partial(parameterized_function, keywords=["paris"])
        assert _canonical(a) == _canonical(b)


# ---------------------------------------------------------------------------
# _canonical — evaluator_identity (explicit, user-controlled)
# ---------------------------------------------------------------------------


class TestCanonicalEvaluatorIdentity:
    def test_evaluator_identity_takes_precedence(self) -> None:
        """evaluator_identity() is used over introspection when available."""

        class CustomScorer:
            def __init__(self, model: str, temperature: float):
                self.model = model
                self.temperature = temperature
                self._client = object()  # runtime state, not config

            def evaluator_identity(self) -> dict:
                return {"model": self.model, "temperature": self.temperature}

        result = _canonical(CustomScorer(model="gpt-4", temperature=0.7))
        assert result == {"model": "gpt-4", "temperature": 0.7}

    def test_evaluator_identity_on_dataclass_overrides_introspection(self) -> None:
        """evaluator_identity() wins even if the object is a dataclass."""

        @dataclasses.dataclass
        class VersionedEvaluator:
            threshold: float
            version: int = 1

            def evaluator_identity(self) -> dict:
                return {"v": self.version, "t": self.threshold}

        result = _canonical(VersionedEvaluator(threshold=0.8, version=2))
        assert result == {"v": 2, "t": 0.8}

    def test_evaluator_identity_different_config_different_hash(self) -> None:
        class CustomScorer:
            def __init__(self, model: str):
                self.model = model

            def evaluator_identity(self) -> dict:
                return {"model": self.model}

        h1 = compute_eval_hash([CustomScorer(model="gpt-4")])
        h2 = compute_eval_hash([CustomScorer(model="claude")])
        assert h1 != h2

    def test_evaluator_identity_same_config_same_hash(self) -> None:
        class CustomScorer:
            def __init__(self, model: str):
                self.model = model

            def evaluator_identity(self) -> dict:
                return {"model": self.model}

        h1 = compute_eval_hash([CustomScorer(model="gpt-4")])
        h2 = compute_eval_hash([CustomScorer(model="gpt-4")])
        assert h1 == h2


# ---------------------------------------------------------------------------
# _canonical — fail-hard on unknown types
# ---------------------------------------------------------------------------


class TestCanonicalFailHard:
    def test_unknown_type_raises_canonical_error(self) -> None:
        class Opaque:
            pass

        with pytest.raises(CanonicalError, match="Opaque"):
            _canonical(Opaque())

    def test_non_callable_non_dataclass_raises(self) -> None:
        with pytest.raises(CanonicalError):
            _canonical(object())

    def test_error_message_mentions_evaluator_identity(self) -> None:
        class Opaque:
            pass

        with pytest.raises(CanonicalError, match="evaluator_identity"):
            _canonical(Opaque())


# ---------------------------------------------------------------------------
# compute_case_hash
# ---------------------------------------------------------------------------


class TestComputeCaseHash:
    def test_same_inputs_same_hash(self) -> None:
        h1 = compute_case_hash("hello", "expected")
        h2 = compute_case_hash("hello", "expected")
        assert h1 == h2

    def test_different_inputs_different_hash(self) -> None:
        h1 = compute_case_hash("hello", "expected")
        h2 = compute_case_hash("world", "expected")
        assert h1 != h2

    def test_none_expected_is_stable(self) -> None:
        h1 = compute_case_hash("hello", None)
        h2 = compute_case_hash("hello", None)
        assert h1 == h2

    def test_dict_inputs(self) -> None:
        h1 = compute_case_hash({"q": "hello", "context": "world"}, "expected")
        h2 = compute_case_hash({"context": "world", "q": "hello"}, "expected")
        assert h1 == h2, "dict key order should not affect hash"


# ---------------------------------------------------------------------------
# compute_eval_hash
# ---------------------------------------------------------------------------


class TestComputeEvalHash:
    def test_identical_evaluators_produce_same_hash(self) -> None:
        ev = SimpleEvaluator(threshold=0.8)
        h1 = compute_eval_hash([ev])
        h2 = compute_eval_hash([ev])
        assert h1 == h2

    def test_different_thresholds_produce_different_hashes(self) -> None:
        ev_a = SimpleEvaluator(threshold=0.8)
        ev_b = SimpleEvaluator(threshold=0.9)
        assert compute_eval_hash([ev_a]) != compute_eval_hash([ev_b])

    def test_evaluator_with_lock_does_not_crash(self) -> None:
        """Regression for non-picklable evaluator fields."""
        ev = LockHoldingEvaluator(name="llm_judge")
        hash_val = compute_eval_hash([ev])
        assert len(hash_val) == 12

    def test_partial_evaluators_hash_stably(self) -> None:
        ev = functools.partial(parameterized_function, keywords=["paris"])
        h1 = compute_eval_hash([ev])
        h2 = compute_eval_hash([ev])
        assert h1 == h2

    def test_bare_function_evaluator(self) -> None:
        h1 = compute_eval_hash([bare_function])
        h2 = compute_eval_hash([bare_function])
        assert h1 == h2

    def test_different_partial_kwargs_different_hash(self) -> None:
        ev_a = functools.partial(parameterized_function, keywords=["paris"])
        ev_b = functools.partial(parameterized_function, keywords=["lyon"])
        assert compute_eval_hash([ev_a]) != compute_eval_hash([ev_b])
