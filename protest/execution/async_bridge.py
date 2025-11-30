"""Utilities for bridging sync and async code. Pattern inspired by Starlette."""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from protest.compat import TypeIs

T = TypeVar("T")


def is_async_callable(obj: object) -> TypeIs[Callable[..., Awaitable[Any]]]:
    """Check if obj is async. Unwraps functools.partial and checks __call__."""
    while isinstance(obj, functools.partial):
        obj = obj.func

    return asyncio.iscoroutinefunction(obj) or (
        callable(obj) and asyncio.iscoroutinefunction(obj.__call__)
    )


async def run_in_threadpool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a sync function in the default executor to avoid blocking the loop."""
    loop = asyncio.get_running_loop()
    if kwargs:
        func = functools.partial(func, **kwargs)
    return await loop.run_in_executor(None, func, *args)


async def ensure_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call func and return result. Async funcs are awaited, sync called directly."""
    if is_async_callable(func):
        return await func(*args, **kwargs)
    return func(*args, **kwargs)
