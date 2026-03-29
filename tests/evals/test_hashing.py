"""Tests for protest.evals.hashing — including non-picklable dataclass fields."""

from __future__ import annotations

import dataclasses
import threading

from protest.evals.hashing import _canonical, compute_eval_hash

# ---------------------------------------------------------------------------
# _canonical — dataclass handling
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


class TestCanonicalDataclass:
    def test_simple_dataclass_is_serialized(self) -> None:
        ev = SimpleEvaluator(threshold=0.8)
        result = _canonical(ev)
        assert result == {"threshold": 0.8, "name": "simple"}

    def test_nested_dataclass_is_serialized_recursively(self) -> None:
        ev = NestedEvaluator(inner=SimpleEvaluator(threshold=0.5), weight=2.0)
        result = _canonical(ev)
        assert result == {"inner": {"threshold": 0.5, "name": "simple"}, "weight": 2.0}

    def test_dataclass_with_lock_does_not_crash(self) -> None:
        """Regression: dataclasses.asdict() deepcopy fails on threading.Lock."""
        ev = LockHoldingEvaluator(name="llm_judge")
        # Must not raise — lock falls back to repr()
        result = _canonical(ev)
        assert result["name"] == "llm_judge"
        assert "_lock" in result


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
        # Should not raise TypeError about cannot pickle '_thread.lock'
        hash_val = compute_eval_hash([ev])
        assert len(hash_val) == 12
