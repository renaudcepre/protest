"""Retry configuration and normalization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Retry:
    """Configuration for test retry behavior."""

    times: int
    delay: float = 0.0
    on: type[Exception] | tuple[type[Exception], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.times < 0:
            raise ValueError(f"retry times must be non-negative, got {self.times}")
        if self.delay < 0:
            raise ValueError(f"retry delay must be non-negative, got {self.delay}")
        if not isinstance(self.on, tuple):
            object.__setattr__(self, "on", (self.on,))


def normalize_retry(retry: int | Retry | None) -> Retry | None:
    """Normalize retry parameter to Retry object or None."""
    if retry is None:
        return None
    if isinstance(retry, int):
        return Retry(times=retry)
    return retry
