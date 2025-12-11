"""Xfail configuration and normalization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Xfail:
    """Configuration for expected failure."""

    reason: str = "Expected failure"
    strict: bool = True


def normalize_xfail(xfail: bool | str | Xfail | None) -> Xfail | None:
    """Normalize xfail parameter to Xfail object or None."""
    if xfail is None or xfail is False:
        return None
    if xfail is True:
        return Xfail()
    if isinstance(xfail, str):
        return Xfail(reason=xfail)
    return xfail
