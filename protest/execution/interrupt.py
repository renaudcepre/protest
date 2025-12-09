"""Keyboard interrupt handling for graceful shutdown."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable
from enum import Enum
from typing import Any


class InterruptState(Enum):
    RUNNING = "running"
    SOFT_STOP = "soft_stop"
    FORCE_TEARDOWN = "force_teardown"
    HARD_EXIT = "hard_exit"


SignalHandler = Callable[[int, Any], Any] | int | None


class InterruptHandler:
    """Handles keyboard interrupts with 3-level shutdown strategy.

    - 1st Ctrl+C (SOFT_STOP): Stop launching new tests, wait for running tests + teardowns
    - 2nd Ctrl+C (FORCE_TEARDOWN): Cancel running tests, execute teardowns, skip wait_pending
    - 3rd Ctrl+C (HARD_EXIT): Immediate shutdown
    """

    def __init__(self) -> None:
        self._state = InterruptState.RUNNING
        self._soft_stop_event: asyncio.Event | None = None
        self._force_teardown_event: asyncio.Event | None = None
        self._original_handler: SignalHandler = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_interrupt: Callable[[InterruptState], None] | None = None

    @property
    def state(self) -> InterruptState:
        return self._state

    @property
    def should_stop_new_tests(self) -> bool:
        return self._state != InterruptState.RUNNING

    @property
    def should_cancel_running(self) -> bool:
        return self._state in (InterruptState.FORCE_TEARDOWN, InterruptState.HARD_EXIT)

    @property
    def should_skip_wait_pending(self) -> bool:
        return self._state in (InterruptState.FORCE_TEARDOWN, InterruptState.HARD_EXIT)

    @property
    def soft_stop_event(self) -> asyncio.Event:
        if self._soft_stop_event is None:
            raise RuntimeError("InterruptHandler not installed")
        return self._soft_stop_event

    @property
    def force_teardown_event(self) -> asyncio.Event:
        if self._force_teardown_event is None:
            raise RuntimeError("InterruptHandler not installed")
        return self._force_teardown_event

    def set_interrupt_callback(
        self, callback: Callable[[InterruptState], None]
    ) -> None:
        self._on_interrupt = callback

    def install(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._soft_stop_event = asyncio.Event()
        self._force_teardown_event = asyncio.Event()
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_signal)

    def uninstall(self) -> None:
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)
            self._original_handler = None
        self._loop = None
        self._soft_stop_event = None
        self._force_teardown_event = None

    def _handle_signal(self, signum: int, frame: object) -> None:
        if self._state == InterruptState.RUNNING:
            self._state = InterruptState.SOFT_STOP
            if self._loop is not None and self._soft_stop_event is not None:
                self._loop.call_soon_threadsafe(self._soft_stop_event.set)
            if self._on_interrupt:
                self._on_interrupt(self._state)

        elif self._state == InterruptState.SOFT_STOP:
            self._state = InterruptState.FORCE_TEARDOWN
            if self._loop is not None and self._force_teardown_event is not None:
                self._loop.call_soon_threadsafe(self._force_teardown_event.set)
            if self._on_interrupt:
                self._on_interrupt(self._state)

        else:
            self._state = InterruptState.HARD_EXIT
            if self._original_handler is not None:
                signal.signal(signal.SIGINT, self._original_handler)
            raise KeyboardInterrupt

    def simulate_signal(self) -> None:
        """Simulate receiving SIGINT for testing purposes."""
        self._handle_signal(signal.SIGINT, None)
