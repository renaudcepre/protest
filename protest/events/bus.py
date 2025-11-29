"""Event bus for decoupled event handling."""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from protest.events.types import Event
from protest.execution.async_bridge import run_in_threadpool


class EventBus:
    """Event bus with async support. Sync handlers block, async handlers are fire-and-forget."""

    def __init__(self) -> None:
        self._handlers: dict[Event, list[Callable[..., Any]]] = defaultdict(list)
        self._pending_tasks: set[asyncio.Task[None]] = set()

    def on(self, event: Event, handler: Callable[..., Any]) -> None:
        """Register a handler for an event."""
        self._handlers[event].append(handler)

    async def emit(self, event: Event, data: Any = None) -> None:
        """Emit event. Sync handlers block, async handlers run as fire-and-forget tasks."""
        for handler in self._handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    task = asyncio.create_task(self._run_async_handler(handler, data))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)
                else:
                    if data is not None:
                        await run_in_threadpool(handler, data)
                    else:
                        await run_in_threadpool(handler)
            except Exception:
                pass  # TODO: log errors

    async def _run_async_handler(
        self, handler: Callable[..., Any], data: Any
    ) -> None:
        """Run async handler with error handling."""
        try:
            if data is not None:
                await handler(data)
            else:
                await handler()
        except Exception:
            pass  # TODO: log errors

    async def wait_pending(self) -> None:
        """Wait for all fire-and-forget async tasks to complete."""
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
