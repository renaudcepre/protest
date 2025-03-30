from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.use import Use


class Scope(StrEnum):
    SESSION = "session"
    SUITE = "suite"
    CLASS = "class"
    FUNCTION = "function"


@dataclass
class FixtureInfo:
    func: Callable[..., Any]
    scope: Scope
    dependencies: dict[str, Use] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"FixtureInfo(func={self.func.__name__} scope={self.scope}, deps={len(self.dependencies)})"


@dataclass
class CachedFixture:
    value: Any
    cleanup: AsyncGenerator[Any, None] | Generator[Any, None, None] | None = None
    is_async: bool = False
    is_generator: bool = False
    scope: Scope = Scope.FUNCTION

    def __repr__(self) -> str:
        return f"CachedFixture(value={self.value}, is_async={self.is_async}, scope={self.scope})"
