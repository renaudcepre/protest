"""ProTest evals - native eval support."""

from protest.evals.evaluator import (
    EvalCase,
    EvalContext,
    Evaluator,
    Metric,
    Reason,
    ShortCircuit,
    Verdict,
    evaluator,
)
from protest.evals.suite import EvalSuite
from protest.evals.types import (
    EvalCaseResult,
    EvalScore,
    EvalSuiteReport,
    Judge,
    JudgeInfo,
    JudgeResponse,
    ModelLabel,
    ScoreStats,
    TaskResult,
)

__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalContext",
    "EvalScore",
    "EvalSuite",
    "EvalSuiteReport",
    "Evaluator",
    "Judge",
    "JudgeInfo",
    "JudgeResponse",
    "Metric",
    "ModelLabel",
    "Reason",
    "ScoreStats",
    "ShortCircuit",
    "TaskResult",
    "Verdict",
    "evaluator",
]
