from collections.abc import Callable
from typing import Any

from protest.core.scope import Scope

type FixtureCallable = Callable[..., Any]


def get_callable_name(func: FixtureCallable) -> str:
    return getattr(func, "__name__", repr(func))


class Fixture:
    def __init__(self, func: FixtureCallable, scope: Scope):
        self.func = func
        self.scope = scope
        self.cached_value: Any = None
        self.is_cached: bool = False

    def clear_cache(self) -> None:
        self.cached_value = None
        self.is_cached = False
