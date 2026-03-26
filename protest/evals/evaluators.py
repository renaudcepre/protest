"""Built-in evaluators for common eval patterns.

Evaluators return either bool (simple verdict) or a dataclass with
annotated fields: Annotated[bool, Verdict], Annotated[float, Metric],
Annotated[str, Reason]. Unannotated fields are ignored by the runner.
"""

from __future__ import annotations

import json as json_module
import re
from dataclasses import dataclass
from typing import Annotated

from protest.evals.evaluator import EvalContext, Metric, Verdict, evaluator


@dataclass(frozen=True, slots=True)
class ContainsKeywordsResult:
    keyword_recall: Annotated[float, Metric]
    all_keywords_present: Annotated[bool, Verdict]


@dataclass(frozen=True, slots=True)
class DoesNotContainResult:
    no_forbidden_words: Annotated[bool, Verdict]


@dataclass(frozen=True, slots=True)
class MaxLengthResult:
    conciseness: Annotated[float, Metric]
    within_limit: Annotated[bool, Verdict]


@dataclass(frozen=True, slots=True)
class JsonValidResult:
    valid_json: Annotated[bool, Verdict]
    has_required_keys: Annotated[bool, Verdict]


@dataclass(frozen=True, slots=True)
class WordOverlapResult:
    overlap: Annotated[float, Metric]


@evaluator
def contains_keywords(ctx: EvalContext, keywords: list[str], min_recall: float = 0.0) -> ContainsKeywordsResult:
    """Check that the output contains expected keywords (case-insensitive)."""
    output_lower = ctx.output.lower()
    found = sum(1 for kw in keywords if kw.lower() in output_lower)
    total = len(keywords)
    recall = found / total if total else 1.0
    return ContainsKeywordsResult(
        keyword_recall=recall,
        all_keywords_present=recall >= min_recall if min_recall > 0 else found == total,
    )


@evaluator
def contains_expected(ctx: EvalContext, case_sensitive: bool = False) -> bool:
    """Check that the output contains expected_output as a substring."""
    if ctx.expected_output is None:
        return True
    if case_sensitive:
        return ctx.expected_output in ctx.output
    return ctx.expected_output.lower() in ctx.output.lower()


@evaluator
def does_not_contain(
    ctx: EvalContext, forbidden: list[str], case_sensitive: bool = False
) -> DoesNotContainResult:
    """Check that the output does not contain forbidden words."""
    output = ctx.output if case_sensitive else ctx.output.lower()
    found = [w for w in forbidden if (w if case_sensitive else w.lower()) in output]
    return DoesNotContainResult(no_forbidden_words=len(found) == 0)


@evaluator
def not_empty(ctx: EvalContext) -> bool:
    """Check that the output is not empty or whitespace-only."""
    if ctx.output is None:
        return False
    if isinstance(ctx.output, str):
        return len(ctx.output.strip()) > 0
    return True


@evaluator
def max_length(ctx: EvalContext, max_chars: int = 500) -> MaxLengthResult:
    """Check that the output doesn't exceed a character limit."""
    length = len(ctx.output)
    return MaxLengthResult(
        conciseness=min(1.0, max_chars / max(length, 1)),
        within_limit=length <= max_chars,
    )


@evaluator
def min_length(ctx: EvalContext, min_chars: int = 1) -> bool:
    """Check that the output meets a minimum length."""
    return len(ctx.output) >= min_chars


@evaluator
def matches_regex(ctx: EvalContext, pattern: str, flags: int = 0) -> bool:
    """Check that the output matches a regex pattern."""
    return bool(re.search(pattern, ctx.output, flags))


@evaluator
def json_valid(
    ctx: EvalContext, required_keys: list[str] | None = None
) -> JsonValidResult:
    """Check that the output is valid JSON, optionally with required keys."""
    if required_keys is None:
        required_keys = []
    try:
        parsed = json_module.loads(ctx.output)
    except (json_module.JSONDecodeError, TypeError):
        return JsonValidResult(valid_json=False, has_required_keys=False)

    has_keys = (
        all(k in parsed for k in required_keys)
        if required_keys and isinstance(parsed, dict)
        else True
    )
    return JsonValidResult(valid_json=True, has_required_keys=has_keys)


@evaluator
def word_overlap(ctx: EvalContext) -> WordOverlapResult:
    """Compute word overlap between output and expected_output (tracking-only)."""
    if ctx.expected_output is None:
        return WordOverlapResult(overlap=1.0)
    expected = str(ctx.expected_output)
    expected_words = set(expected.lower().split())
    output_words = set(ctx.output.lower().split())
    if not expected_words:
        return WordOverlapResult(overlap=1.0)
    return WordOverlapResult(
        overlap=len(expected_words & output_words) / len(expected_words),
    )
