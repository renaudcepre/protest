"""Shared formatting helpers used by both Rich and Ascii reporters.

Only formats that are *truly identical* between the two reporters live here.
Visual rendering (glyphs vs ASCII words, colors) stays in each reporter.
"""

from __future__ import annotations

MIN_DURATION_THRESHOLD = 0.001
_TOKEN_K_THRESHOLD = 1000


def format_duration(seconds: float) -> str:
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def format_tokens(tokens: int) -> str:
    """Format token count: 1234 → '1.2k', 45 → '45'."""
    return (
        f"{tokens / _TOKEN_K_THRESHOLD:.1f}k"
        if tokens >= _TOKEN_K_THRESHOLD
        else str(tokens)
    )


def format_usage(input_tokens: int, output_tokens: int, cost: float) -> str:
    """Format usage stats as 'Xk in / Yk out, $0.0042'."""
    parts: list[str] = []
    if input_tokens > 0 or output_tokens > 0:
        parts.append(
            f"{format_tokens(input_tokens)} in / {format_tokens(output_tokens)} out"
        )
    if cost > 0:
        parts.append(f"${cost:.4f}")
    return ", ".join(parts)
