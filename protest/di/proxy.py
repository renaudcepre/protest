from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from protest.exceptions import FixtureError

if TYPE_CHECKING:
    from collections.abc import Callable

T = TypeVar("T")


class SafeProxy(Generic[T]):
    """Proxy that wraps all method calls to convert exceptions to FixtureError.

    Used for non-managed factory fixtures (factory=True, managed=False) to ensure
    that errors in factory class methods are reported as SETUP ERROR, not TEST FAIL.
    """

    def __init__(self, target: T, fixture_name: str) -> None:
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_fixture_name", fixture_name)

    def _wrap_sync(self, method: Callable[..., Any]) -> Callable[..., Any]:
        fixture_name = object.__getattribute__(self, "_fixture_name")

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return method(*args, **kwargs)
            except FixtureError:
                raise
            except Exception as exc:
                raise FixtureError(fixture_name, exc) from exc

        return wrapper

    def _wrap_async(self, method: Callable[..., Any]) -> Callable[..., Any]:
        fixture_name = object.__getattribute__(self, "_fixture_name")

        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await method(*args, **kwargs)
            except FixtureError:
                raise
            except Exception as exc:
                raise FixtureError(fixture_name, exc) from exc

        return wrapper

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        target = object.__getattribute__(self, "_target")
        fixture_name = object.__getattribute__(self, "_fixture_name")

        if not callable(target):
            raise TypeError(f"'{fixture_name}' is not callable")

        if asyncio.iscoroutinefunction(target.__call__):
            return self._wrap_async(target)(*args, **kwargs)
        return self._wrap_sync(target)(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        target = object.__getattribute__(self, "_target")
        attr = getattr(target, name)

        if callable(attr):
            if asyncio.iscoroutinefunction(attr) or inspect.iscoroutinefunction(attr):
                return self._wrap_async(attr)
            return self._wrap_sync(attr)

        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        target = object.__getattribute__(self, "_target")
        setattr(target, name, value)

    def __repr__(self) -> str:
        target = object.__getattribute__(self, "_target")
        fixture_name = object.__getattribute__(self, "_fixture_name")
        return f"SafeProxy({fixture_name!r}, {target!r})"
