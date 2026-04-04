"""ProTest evals — native eval support."""

from protest.evals.evaluator import (
    EvalCase,
    EvalContext,
    Metric,
    Reason,
    ShortCircuit,
    Verdict,
    evaluator,
)
from protest.evals.types import (
    EvalCaseResult,
    EvalScore,
    EvalSuiteReport,
    Judge,
    JudgeInfo,
    JudgeResponse,
    ModelInfo,
    ScoreStats,
    TaskResult,
)

__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalContext",
    "EvalScore",
    "EvalSuiteReport",
    "Judge",
    "JudgeInfo",
    "JudgeResponse",
    "Metric",
    "ModelInfo",
    "Reason",
    "ScoreStats",
    "ShortCircuit",
    "TaskResult",
    "Verdict",
    "evaluator",
]
