import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from protest.entities import HandlerInfo
from protest.events.types import Event
from protest.execution.async_bridge import run_in_threadpool
from protest.utils import get_callable_name

logger = logging.getLogger(__name__)


@dataclass
class _RegisteredHandler:
    """Internal: handler with metadata."""

    func: Callable[..., Any]
    name: str


class EventBus:
    """Decoupled event dispatch with async support.

    Sync handlers are executed in a thread pool (blocking the event emission).
    Async handlers run fire-and-forget and are tracked for cleanup.

    Use wait_pending() before session end to ensure all async handlers complete.
    Handler exceptions are logged but don't stop other handlers or the session.
    """

    def __init__(self) -> None:
        self._handlers: dict[Event, list[_RegisteredHandler]] = defaultdict(list)
        self._pending_tasks: set[asyncio.Task[None]] = set()

    def on(self, event: Event, handler: Callable[..., Any]) -> None:
        """Register a handler for an event."""
        name = get_callable_name(handler)
        self._handlers[event].append(_RegisteredHandler(func=handler, name=name))

    async def emit(self, event: Event, data: Any = None) -> None:
        """Emit event. Sync handlers block, async handlers run fire-and-forget."""
        for registered in self._handlers[event]:
            handler = registered.func
            handler_name = registered.name
            is_async = asyncio.iscoroutinefunction(handler)

            await self._emit_handler_start(handler_name, event, is_async)
            start_time = time.perf_counter()

            try:
                if is_async:
                    task = asyncio.create_task(
                        self._run_async_handler_tracked(
                            handler, data, handler_name, event, start_time
                        )
                    )
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                elif data is not None:
                    await run_in_threadpool(handler, data)
                    duration = time.perf_counter() - start_time
                    await self._emit_handler_end(
                        handler_name, event, False, duration, None
                    )
                else:
                    await run_in_threadpool(handler)
                    duration = time.perf_counter() - start_time
                    await self._emit_handler_end(
                        handler_name, event, False, duration, None
                    )
            except Exception as exc:
                duration = time.perf_counter() - start_time
                await self._emit_handler_end(
                    handler_name, event, is_async, duration, exc
                )
                logger.exception(
                    "Handler %s failed for event %s",
                    handler_name,
                    event.value,
                )

    async def _run_async_handler_tracked(
        self,
        handler: Callable[..., Any],
        data: Any,
        handler_name: str,
        event: Event,
        start_time: float,
    ) -> None:
        """Run async handler with tracking for HANDLER_END."""
        error: Exception | None = None
        try:
            if data is not None:
                await handler(data)
            else:
                await handler()
        except Exception as exc:
            error = exc
            logger.exception("Async handler %s failed", handler_name)
        finally:
            duration = time.perf_counter() - start_time
            await self._emit_handler_end(handler_name, event, True, duration, error)

    async def _emit_handler_start(
        self, name: str, event: Event, is_async: bool
    ) -> None:
        """Emit HANDLER_START without triggering handler events (avoid recursion)."""
        info = HandlerInfo(name=name, event=event, is_async=is_async)
        for registered in self._handlers[Event.HANDLER_START]:
            try:
                if asyncio.iscoroutinefunction(registered.func):
                    await registered.func(info)
                else:
                    await run_in_threadpool(registered.func, info)
            except Exception:
                logger.exception("HANDLER_START listener %s failed", registered.name)

    async def _emit_handler_end(
        self,
        name: str,
        event: Event,
        is_async: bool,
        duration: float,
        error: Exception | None,
    ) -> None:
        """Emit HANDLER_END without triggering handler events (avoid recursion)."""
        info = HandlerInfo(
            name=name, event=event, is_async=is_async, duration=duration, error=error
        )
        for registered in self._handlers[Event.HANDLER_END]:
            try:
                if asyncio.iscoroutinefunction(registered.func):
                    await registered.func(info)
                else:
                    await run_in_threadpool(registered.func, info)
            except Exception:
                logger.exception("HANDLER_END listener %s failed", registered.name)

    @property
    def pending_count(self) -> int:
        """Number of pending async tasks."""
        return len(self._pending_tasks)

    async def wait_pending(self) -> None:
        """Wait for all fire-and-forget async tasks to complete."""
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)

    async def emit_and_collect(self, event: Event, data: Any) -> Any:
        """Emit event and allow handlers to modify data in chain."""
        for registered in self._handlers[event]:
            handler = registered.func
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(data)
                else:
                    result = handler(data)
                if result is not None:
                    data = result
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s",
                    registered.name,
                    event.value,
                )
        return data
