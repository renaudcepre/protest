"""Skip configuration and normalization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Skip:
    """Configuration for skipping a test."""

    reason: str = "Skipped"


def normalize_skip(skip: bool | str | Skip | None) -> Skip | None:
    """Normalize skip parameter to Skip object or None."""
    if skip is None or skip is False:
        return None
    if skip is True:
        return Skip()
    if isinstance(skip, str):
        return Skip(reason=skip)
    return skip
