from __future__ import annotations

from contextlib import AsyncExitStack
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncio
    from types import TracebackType

    from protest.compat import Self
    from protest.di.container import FixtureContainer
    from protest.entities import FixtureCallable, SuitePath

# Global cancellation signal for graceful shutdown.
# When set, teardown code should abort ASAP.
cancellation_event: ContextVar[asyncio.Event | None] = ContextVar(
    "cancellation_event", default=None
)


class TestExecutionContext:
    """Isolated context for a single test execution.

    Manages FUNCTION-scoped fixtures independently per test, allowing parallel
    execution. Provides its cache and exit stack to the FixtureContainer which handles
    all resolution logic.
    """

    def __init__(
        self, parent: FixtureContainer, suite_path: SuitePath | None = None
    ) -> None:
        self._parent = parent
        self._suite_path = suite_path
        self._cache: dict[FixtureCallable, Any] = {}
        self._exit_stack = AsyncExitStack()
        self._closed = False

    async def __aenter__(self) -> Self:
        await self._exit_stack.__aenter__()
        # Resolve TEST-scoped autouse fixtures at test start
        await self._parent.resolve_test_autouse(
            current_path=self._suite_path,
            context_cache=self._cache,
            context_exit_stack=self._exit_stack,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if self._closed:
            return False
        result = await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
        return result or False

    async def close(self) -> None:
        """Explicitly close the context and teardown fixtures."""
        if not self._closed:
            self._closed = True
            await self._exit_stack.aclose()

    async def resolve(self, target_func: FixtureCallable) -> Any:
        """Resolve a fixture by delegating to the parent FixtureContainer with injected context."""
        return await self._parent.resolve(
            target_func,
            current_path=self._suite_path,
            context_cache=self._cache,
            context_exit_stack=self._exit_stack,
        )
