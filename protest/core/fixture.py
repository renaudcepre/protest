import inspect
from collections.abc import Callable
from typing import Any, TypeAlias

from protest.utils import get_callable_name

FixtureCallable: TypeAlias = Callable[..., Any]


def get_fixture_name(func: FixtureCallable) -> str:
    return get_callable_name(func, fallback=repr(func))


def is_generator_like(func: FixtureCallable) -> bool:
    """Check if func contains yield (sync or async)."""
    return inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)


class Fixture:
    """Wraps a fixture callable with caching and factory metadata."""

    def __init__(self, func: FixtureCallable, is_factory: bool = False):
        self.func = func
        self.is_factory = is_factory
        self.cached_value: Any = None
        self.is_cached: bool = False

    def clear_cache(self) -> None:
        self.cached_value = None
        self.is_cached = False
