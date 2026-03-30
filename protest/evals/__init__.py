"""ProTest evals — native eval support."""

from protest.evals.evaluator import EvalCase, EvalContext, Metric, Reason, ShortCircuit, Verdict, evaluator
from protest.evals.session import EvalSession
from protest.evals.types import (
    EvalCaseResult,
    EvalScore,
    EvalSuiteReport,
    JudgeInfo,
    ModelInfo,
    ScoreStats,
)

__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalContext",
    "Metric",
    "EvalScore",
    "EvalSession",
    "EvalSuiteReport",
    "JudgeInfo",
    "ModelInfo",
    "Reason",
    "ScoreStats",
    "ShortCircuit",
    "Verdict",
    "evaluator",
]
