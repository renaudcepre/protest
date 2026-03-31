"""Types for eval results, scores, and run context."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TaskResult(Generic[T]):
    """Optional wrapper for eval task return values with usage stats.

    Return this instead of a plain value to report LLM usage for the
    system under test. ProTest unwraps it transparently — evaluators
    see the plain output.

    Usage::

        @session.eval(evaluators=[...])
        async def my_eval(case) -> TaskResult[str]:
            result = await agent.run(case.inputs)
            usage = result.usage()
            return TaskResult(
                output=result.output,
                input_tokens=usage.request_tokens,
                output_tokens=usage.response_tokens,
                cost=0.003,
            )

        # Or just return str directly — TaskResult is opt-in.
    """

    output: T
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class JudgeResponse(Generic[T]):
    """Return type for Judge.judge() — wraps the output with optional usage stats.

    Evaluators never see this: ``ctx.judge()`` unwraps and returns ``output``.
    ProTest accumulates tokens/cost for history and display.

    Usage::

        return JudgeResponse(
            output=result.output,
            input_tokens=usage.request_tokens,
            output_tokens=usage.response_tokens,
            cost=0.003,
        )

        # Or minimal — tokens/cost are optional:
        return JudgeResponse(output=result.output)
    """

    output: T
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None


@runtime_checkable
class Judge(Protocol):
    """Protocol for LLM judge implementations.

    All configuration (model, temperature, system_prompt, max_tokens)
    lives in the constructor of the implementation, NOT in this protocol.

    Usage::

        class MyJudge:
            name = "my-judge"
            provider = "openai"

            async def judge(self, prompt: str, output_type: type[T]) -> JudgeResponse[T]:
                result = await agent.run(prompt)
                return JudgeResponse(output=result.output, input_tokens=100)

        session = EvalSession(judge=MyJudge())
    """

    name: str
    provider: str | None

    async def judge(self, prompt: str, output_type: type[T]) -> JudgeResponse[T]: ...


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadata about the model being evaluated."""

    name: str
    provider: str | None = None
    temperature: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


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
    skipped: bool = False

    @property
    def is_verdict(self) -> bool:
        return not self.skipped and isinstance(self.value, bool)

    @property
    def is_metric(self) -> bool:
        return (
            not self.skipped
            and isinstance(self.value, (int, float))
            and not isinstance(self.value, bool)
        )

    @property
    def is_reason(self) -> bool:
        return not self.skipped and isinstance(self.value, str)

    @property
    def passed(self) -> bool:
        if self.skipped:
            return True  # skipped scores don't affect pass/fail
        if isinstance(self.value, bool):
            return self.value
        return True


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
    task_input_tokens: int = 0
    task_output_tokens: int = 0
    task_cost: float = 0.0
    judge_call_count: int = 0
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0
    judge_cost: float = 0.0
    is_error: bool = False

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
        return sum(1 for c in self.cases if not c.passed and not c.is_error)

    @property
    def errored_count(self) -> int:
        return sum(1 for c in self.cases if c.is_error)

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

    @property
    def total_task_input_tokens(self) -> int:
        return sum(c.task_input_tokens for c in self.cases)

    @property
    def total_task_output_tokens(self) -> int:
        return sum(c.task_output_tokens for c in self.cases)

    @property
    def total_task_tokens(self) -> int:
        return self.total_task_input_tokens + self.total_task_output_tokens

    @property
    def total_task_cost(self) -> float:
        return sum(c.task_cost for c in self.cases)

    @property
    def total_judge_calls(self) -> int:
        return sum(c.judge_call_count for c in self.cases)

    @property
    def total_judge_input_tokens(self) -> int:
        return sum(c.judge_input_tokens for c in self.cases)

    @property
    def total_judge_output_tokens(self) -> int:
        return sum(c.judge_output_tokens for c in self.cases)

    @property
    def total_judge_tokens(self) -> int:
        return self.total_judge_input_tokens + self.total_judge_output_tokens

    @property
    def total_judge_cost(self) -> float:
        return sum(c.judge_cost for c in self.cases)
