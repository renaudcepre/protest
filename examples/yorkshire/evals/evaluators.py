"""Yorkshire-specific evaluators.

Generic evaluators come from protest.evals.evaluators.
Only project-specific ones live here.

These also demonstrate how EvalContext generics document
what an evaluator expects as input/output types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from protest.evals import EvalContext, Metric, Verdict, evaluator

# --- Text evaluator: EvalContext[Any, str] ---------------------------------
# Most evaluators work on text output. The first type param (inputs) is Any
# because evaluators don't usually care about the input shape.


@dataclass(frozen=True, slots=True)
class MentionsBreedResult:
    breed_mentioned: Annotated[bool, Verdict]


@evaluator
def mentions_breed(
    ctx: EvalContext[Any, str], breed: str = "Yorkshire"
) -> MentionsBreedResult:
    """Check that the output mentions a specific breed."""
    return MentionsBreedResult(breed_mentioned=breed.lower() in ctx.output.lower())


# --- Numeric evaluator: EvalContext[str, float] ----------------------------
# An evaluator for a task that returns a numeric score (e.g. a classifier
# confidence, a similarity metric). The output is a float, not a string.


@dataclass(frozen=True, slots=True)
class ConfidenceResult:
    confidence: Annotated[float, Metric]
    above_threshold: Annotated[bool, Verdict]


@evaluator
def confidence_above(
    ctx: EvalContext[str, float], threshold: float = 0.8
) -> ConfidenceResult:
    """Check that a numeric output (e.g. classifier confidence) meets a threshold."""
    return ConfidenceResult(
        confidence=ctx.output,
        above_threshold=ctx.output >= threshold,
    )


# --- Binary evaluator: EvalContext[str, bytes] -----------------------------
# An evaluator for a task that returns raw bytes (e.g. image generation,
# audio synthesis). The evaluator checks basic properties of the output.


@evaluator
def output_not_empty_bytes(ctx: EvalContext[str, bytes]) -> bool:
    """Check that a binary output (e.g. generated image) is not empty."""
    return len(ctx.output) > 0
