"""Skip configuration and normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class Skip:
    """Configuration for skipping a test.

    Supports both static and conditional skipping:
    - Static: condition is None or True, test is always skipped
    - Conditional: condition is a callable, evaluated at runtime with fixture values

    Example (static):
        Skip(reason="Not implemented")

    Example (conditional):
        Skip(condition=lambda env: env.is_ci, reason="Skip in CI")
    """

    reason: str = "Skipped"
    condition: bool | Callable[..., bool] | None = None

    @property
    def is_conditional(self) -> bool:
        """True if skip has a callable condition to evaluate at runtime."""
        return callable(self.condition)

    @property
    def is_static(self) -> bool:
        """True if skip should be applied unconditionally."""
        return self.condition is None or self.condition is True


def normalize_skip(
    skip: bool | str | Callable[..., bool] | Skip | None,
    reason: str = "Skipped",
) -> Skip | None:
    """Normalize skip parameter to Skip object or None.

    Args:
        skip: The skip value to normalize
        reason: Default reason for callable conditions

    Returns:
        Skip object or None if skip is None/False
    """
    if skip is None or skip is False:
        return None
    if skip is True:
        return Skip(reason=reason)
    if isinstance(skip, str):
        return Skip(reason=skip)
    if callable(skip):
        return Skip(condition=skip, reason=reason)
    # Already a Skip instance
    return skip
