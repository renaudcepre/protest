"""Utilities for bridging sync and async code. Pattern inspired by Starlette."""

import asyncio
import contextvars
import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from protest.compat import TypeIs

T = TypeVar("T")


def is_async_callable(obj: object) -> TypeIs[Callable[..., Awaitable[Any]]]:
    """Check if obj is async. Unwraps functools.partial and checks __call__."""
    while isinstance(obj, functools.partial):
        obj = obj.func

    return asyncio.iscoroutinefunction(obj) or (
        callable(obj) and callable(obj) and asyncio.iscoroutinefunction(obj.__call__)
    )


async def run_in_threadpool(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a sync function in the default executor, preserving contextvars."""
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    bound_func = functools.partial(ctx.run, func, *args, **kwargs)
    return cast("T", await loop.run_in_executor(None, bound_func))


async def ensure_async(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Call func, awaiting async or offloading sync to threadpool."""
    if is_async_callable(func):
        return cast("T", await func(*args, **kwargs))
    return await run_in_threadpool(func, *args, **kwargs)
