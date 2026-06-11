"""Types for eval results, scores, and run context."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from protest.entities.events import TestResult

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TaskResult(Generic[T]):
    """Optional wrapper for eval task return values with usage stats.

    Return this instead of a plain value to report LLM usage for the
    system under test. ProTest unwraps it transparently - evaluators
    see the plain output.

    Usage::

        @suite.eval(evaluators=[...])
        async def my_eval(case: EvalCase) -> TaskResult[str]:
            result = await agent.run(case.inputs)
            usage = result.usage()
            return TaskResult(
                output=result.output,
                input_tokens=usage.request_tokens,
                output_tokens=usage.response_tokens,
                cost=0.003,
            )

        # Or just return str directly - TaskResult is opt-in.
    """

    output: T
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None


@dataclass(frozen=True, slots=True)
class JudgeResponse(Generic[T]):
    """Return type for Judge.judge() - wraps the output with optional usage stats.

    Evaluators never see this: ``ctx.judge()`` unwraps and returns ``output``.
    ProTest accumulates tokens/cost for history and display.

    Usage::

        return JudgeResponse(
            output=result.output,
            input_tokens=usage.request_tokens,
            output_tokens=usage.response_tokens,
            cost=0.003,
        )

        # Or minimal - tokens/cost are optional:
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

        suite = EvalSuite("chatbot", judge=MyJudge())
    """

    name: str
    provider: str | None

    async def judge(self, prompt: str, output_type: type[T]) -> JudgeResponse[T]: ...


@dataclass(frozen=True, slots=True)
class ModelLabel:
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

    @classmethod
    def from_test_result(cls, result: TestResult) -> EvalCaseResult:
        """Build from a `TestResult` carrying an `eval_payload`.

        `passed` is derived from `result.error` and `payload.passed`, so both
        the runner (post-execution) and the results writer (pass/fail hooks)
        agree on the same computation.
        """
        payload = result.eval_payload
        if payload is None:
            raise ValueError(
                f"Cannot build EvalCaseResult from TestResult without "
                f"eval_payload (node_id={result.node_id})"
            )
        return cls(
            case_name=payload.case_name or "",
            node_id=result.node_id,
            scores=tuple(
                EvalScore(name=name, value=entry.value, skipped=entry.skipped)
                for name, entry in payload.scores.items()
            ),
            duration=payload.task_duration,
            passed=result.error is None and payload.passed,
            inputs=payload.inputs,
            output=payload.output,
            expected_output=payload.expected_output,
            case_hash=payload.case_hash,
            eval_hash=payload.eval_hash,
            task_input_tokens=payload.task_input_tokens,
            task_output_tokens=payload.task_output_tokens,
            task_cost=payload.task_cost,
            judge_call_count=payload.judge_call_count,
            judge_input_tokens=payload.judge_input_tokens,
            judge_output_tokens=payload.judge_output_tokens,
            judge_cost=payload.judge_cost,
            is_error=result.is_fixture_error,
        )

    @property
    def numeric_scores(self) -> dict[str, float]:
        return {s.name: float(s.value) for s in self.scores if s.is_metric}

    @property
    def failed_scores(self) -> tuple[EvalScore, ...]:
        return tuple(s for s in self.scores if not s.passed)


_MIN_VALUES_FOR_PERCENTILES = 2  # statistics.quantiles requires at least 2 inputs


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
        if n >= _MIN_VALUES_FOR_PERCENTILES:
            # `quantiles(n=20, method='inclusive')` returns 19 cutpoints that
            # split the data into 20 equal groups. Index 0 = 5%, index 18 = 95%.
            # Inclusive method interpolates linearly between adjacent values
            # and clamps to [min, max] - appropriate for bounded scores.
            cuts = statistics.quantiles(sv, n=20, method="inclusive")
            p5_value = cuts[0]
            p95_value = cuts[18]
        else:
            # Single value: percentiles are undefined; fall back to that value.
            p5_value = p95_value = sv[0]
        return cls(
            name=name,
            mean=statistics.mean(sv),
            median=statistics.median(sv),
            p5=p5_value,
            p95=p95_value,
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
        # Single pass groups values by score name, avoiding O(n_cases x n_names)
        # of calling score_stats(n) per name. score_stats(name) is preserved as
        # a public single-name accessor.
        by_name: dict[str, list[float]] = {}
        for c in self.cases:
            for s in c.scores:
                if s.is_metric:
                    by_name.setdefault(s.name, []).append(float(s.value))
        return [ScoreStats.from_values(n, by_name[n]) for n in sorted(by_name)]

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
