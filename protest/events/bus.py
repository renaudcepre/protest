"""Event bus for decoupled event handling."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from protest.events.types import Event
from protest.execution.async_bridge import run_in_threadpool

logger = logging.getLogger(__name__)


class EventBus:
    """Event bus with async support. Sync handlers block, async fire-and-forget."""

    def __init__(self) -> None:
        self._handlers: dict[Event, list[Callable[..., Any]]] = defaultdict(list)
        self._pending_tasks: set[asyncio.Task[None]] = set()

    def on(self, event: Event, handler: Callable[..., Any]) -> None:
        """Register a handler for an event."""
        self._handlers[event].append(handler)

    async def emit(self, event: Event, data: Any = None) -> None:
        """Emit event. Sync handlers block, async handlers run fire-and-forget."""
        for handler in self._handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    task = asyncio.create_task(self._run_async_handler(handler, data))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                elif data is not None:
                    await run_in_threadpool(handler, data)
                else:
                    await run_in_threadpool(handler)
            except Exception:
                handler_name = getattr(handler, "__name__", "<unknown>")
                logger.exception(
                    "Handler %s failed for event %s", handler_name, event.value
                )

    async def _run_async_handler(self, handler: Callable[..., Any], data: Any) -> None:
        """Run async handler with error handling."""
        try:
            if data is not None:
                await handler(data)
            else:
                await handler()
        except Exception:
            handler_name = getattr(handler, "__name__", "<unknown>")
            logger.exception("Async handler %s failed", handler_name)

    async def wait_pending(self) -> None:
        """Wait for all fire-and-forget async tasks to complete."""
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)

    async def emit_and_collect(self, event: Event, data: Any) -> Any:
        """Emit event and allow handlers to modify data in chain."""
        for handler in self._handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(data)
                else:
                    result = handler(data)
                if result is not None:
                    data = result
            except Exception:
                handler_name = getattr(handler, "__name__", "<unknown>")
                logger.exception(
                    "Handler %s failed for event %s", handler_name, event.value
                )
        return data
