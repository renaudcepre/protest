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
    JudgeInfo,
    ModelInfo,
    ScoreStats,
)

__all__ = [
    "EvalCase",
    "EvalCaseResult",
    "EvalContext",
    "EvalScore",
    "EvalSession",
    "EvalSuiteReport",
    "JudgeInfo",
    "Metric",
    "ModelInfo",
    "Reason",
    "ScoreStats",
    "ShortCircuit",
    "Verdict",
    "evaluator",
]


def __getattr__(name: str) -> object:
    # EvalSession imports protest.core.session which imports reporters,
    # and reporters import protest.evals.types — eagerly importing
    # EvalSession here would create a circular import chain.
    if name == "EvalSession":
        from protest.evals.session import EvalSession

        return EvalSession
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
