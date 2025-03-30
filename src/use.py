import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class Use:
    """Dependency injection marker class for fixtures."""

    def __init__(
        self,
        fixture: Callable[..., Any] | None = None,
    ):
        self.dependency = fixture
        self.name = getattr(fixture, "__name__", None) if callable(fixture) else None

    def __repr__(self) -> str:
        return f"Use(fixture={self.name})"
