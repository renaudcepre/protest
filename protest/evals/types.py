"""Types for eval results, scores, and run context."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadata about the model being evaluated."""

    name: str
    provider: str | None = None
    temperature: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_agent(cls, agent: Any) -> ModelInfo:
        """Extract model info from a pydantic-ai Agent (duck-typed)."""
        model = getattr(agent, "model", None)
        if model is None:
            msg = "Agent has no model configured"
            raise ValueError(msg)
        if isinstance(model, str):
            return cls(name=model)
        model_name = getattr(model, "model_name", None)
        if callable(model_name):
            return cls(name=str(model_name()))
        return cls(name=str(getattr(model, "name", None) or model))


@dataclass(frozen=True, slots=True)
class JudgeInfo:
    """Metadata about the LLM judge used for evaluation."""

    name: str
    provider: str | None = None
    evaluators: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalScore:
    """A single named value from an evaluator result.

    Values are categorized by type:
    - bool → verdict (pass/fail)
    - float → metric (aggregated in stats)
    - str → reason (displayed on failure)
    """

    name: str
    value: float | bool | str

    @property
    def is_verdict(self) -> bool:
        return isinstance(self.value, bool)

    @property
    def is_metric(self) -> bool:
        return isinstance(self.value, (int, float)) and not isinstance(self.value, bool)

    @property
    def is_reason(self) -> bool:
        return isinstance(self.value, str)

    @property
    def passed(self) -> bool:
        if isinstance(self.value, bool):
            return self.value
        return True  # metrics and reasons always "pass"


@dataclass(frozen=True, slots=True)
class EvalCaseResult:
    """Complete result of evaluating a single case."""

    case_name: str
    node_id: str
    scores: tuple[EvalScore, ...]
    duration: float
    passed: bool
    inputs: Any = None
    output: Any = None
    expected_output: Any = None
    case_hash: str = ""
    eval_hash: str = ""

    @property
    def numeric_scores(self) -> dict[str, float]:
        return {s.name: float(s.value) for s in self.scores if s.is_metric}

    @property
    def failed_scores(self) -> tuple[EvalScore, ...]:
        return tuple(s for s in self.scores if not s.passed)


@dataclass(frozen=True, slots=True)
class ScoreStats:
    """Aggregated statistics for a named score across cases."""

    name: str
    mean: float
    median: float
    p5: float
    p95: float
    min: float
    max: float
    count: int

    @classmethod
    def from_values(cls, name: str, values: list[float]) -> ScoreStats:
        if not values:
            return cls(name=name, mean=0, median=0, p5=0, p95=0, min=0, max=0, count=0)
        sv = sorted(values)
        n = len(sv)
        return cls(
            name=name,
            mean=statistics.mean(sv),
            median=statistics.median(sv),
            p5=sv[max(0, int(n * 0.05))],
            p95=sv[min(n - 1, int(n * 0.95))],
            min=sv[0],
            max=sv[-1],
            count=n,
        )


@dataclass(frozen=True, slots=True)
class EvalSuiteReport:
    """Aggregated report for a suite of eval cases."""

    suite_name: str
    cases: tuple[EvalCaseResult, ...]
    duration: float

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed)

    @property
    def total_count(self) -> int:
        return len(self.cases)

    @property
    def pass_rate(self) -> float:
        return self.passed_count / self.total_count if self.cases else 0.0

    def score_names(self) -> set[str]:
        return {s.name for c in self.cases for s in c.scores if s.is_metric}

    def score_stats(self, name: str) -> ScoreStats:
        values = [
            float(s.value)
            for c in self.cases
            for s in c.scores
            if s.name == name and s.is_metric
        ]
        return ScoreStats.from_values(name, values)

    def all_score_stats(self) -> list[ScoreStats]:
        return [self.score_stats(n) for n in sorted(self.score_names())]
