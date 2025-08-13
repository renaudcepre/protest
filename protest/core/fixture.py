from collections.abc import Callable
from typing import Any

from protest.core.scope import Scope


class Fixture:
    def __init__(self, func: Callable[..., Any], scope: Scope):
        self.func = func
        self.scope = scope
        self.cached_value: Any = None
        self.is_cached: bool = False

    def clear_cache(self) -> None:
        self.cached_value = None
        self.is_cached = False
