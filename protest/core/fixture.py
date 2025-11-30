import inspect
from collections.abc import Callable
from typing import Any, TypeAlias

from protest.core.scope import Scope

FixtureCallable: TypeAlias = Callable[..., Any]


def get_callable_name(func: FixtureCallable) -> str:
    return getattr(func, "__name__", repr(func))


def is_generator_like(func: FixtureCallable) -> bool:
    """Check if func contains yield (sync or async)."""
    return inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)


class Fixture:
    def __init__(self, func: FixtureCallable, scope: Scope, is_factory: bool = False):
        self.func = func
        self.scope = scope
        self.is_factory = is_factory
        self.cached_value: Any = None
        self.is_cached: bool = False

    def clear_cache(self) -> None:
        self.cached_value = None
        self.is_cached = False
