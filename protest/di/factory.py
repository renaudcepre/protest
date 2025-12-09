from __future__ import annotations

import asyncio
import inspect
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from protest.core.fixture import is_generator_like
from protest.di.hashable import UnhashableValueError, make_hashable
from protest.exceptions import FixtureError
from protest.execution.async_bridge import ensure_async

if TYPE_CHECKING:
    from protest.entities import Fixture

T = TypeVar("T")


class FixtureFactory(Generic[T]):
    """A callable wrapper that creates fixture instances with caching and teardown."""

    def __init__(
        self,
        fixture: Fixture,
        fixture_name: str,
        resolved_dependencies: dict[str, Any],
        exit_stack: AsyncExitStack,
        cache_enabled: bool = True,
    ) -> None:
        self._fixture = fixture
        self._fixture_name = fixture_name
        self._resolved_dependencies = resolved_dependencies
        self._exit_stack = exit_stack
        self._cache_enabled = cache_enabled
        self._instance_cache: dict[Any, T] = {}
        self._lock = asyncio.Lock()

    def _make_cache_key(self, kwargs: dict[str, Any]) -> Any:
        try:
            return make_hashable(kwargs, path=self._fixture_name)
        except UnhashableValueError as exc:
            raise TypeError(
                f"Factory '{self._fixture_name}' cannot cache call: {exc}"
            ) from exc

    async def __call__(self, **kwargs: Any) -> T:
        cache_key = self._make_cache_key(kwargs)

        if self._cache_enabled and cache_key in self._instance_cache:
            return self._instance_cache[cache_key]

        async with self._lock:
            if self._cache_enabled and cache_key in self._instance_cache:
                return self._instance_cache[cache_key]

            instance = await self._create_instance(kwargs)

            if self._cache_enabled:
                self._instance_cache[cache_key] = instance

            return instance

    async def _create_instance(self, user_kwargs: dict[str, Any]) -> T:
        all_kwargs = {**self._resolved_dependencies, **user_kwargs}

        try:
            if is_generator_like(self._fixture.func):
                return await self._execute_generator(all_kwargs)
            return await ensure_async(self._fixture.func, **all_kwargs)
        except Exception as exc:
            raise FixtureError(self._fixture_name, exc) from exc

    async def _execute_generator(self, kwargs: dict[str, Any]) -> T:
        if inspect.isasyncgenfunction(self._fixture.func):
            async_cm = asynccontextmanager(self._fixture.func)(**kwargs)
            return cast("T", await self._exit_stack.enter_async_context(async_cm))
        sync_cm = contextmanager(self._fixture.func)(**kwargs)
        return cast("T", self._exit_stack.enter_context(sync_cm))
