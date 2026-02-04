"""Keyboard interrupt handling for graceful shutdown."""

from __future__ import annotations

import asyncio
import os
import signal
import threading
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
    - 3rd Ctrl+C (HARD_EXIT): Immediate shutdown via watchdog thread

    A watchdog thread monitors for exit requests and calls os._exit() to ensure
    clean termination even when worker threads are blocked in C code.
    """

    def __init__(self) -> None:
        self._state = InterruptState.RUNNING
        self._soft_stop_event: asyncio.Event | None = None
        self._force_teardown_event: asyncio.Event | None = None
        self._original_handler: SignalHandler = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._exit_flag = threading.Event()
        self._stop_watchdog = threading.Event()
        self._watchdog: threading.Thread | None = None

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

    def install(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._soft_stop_event = asyncio.Event()
        self._force_teardown_event = asyncio.Event()
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Start watchdog thread
        self._stop_watchdog = threading.Event()
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog.start()

    def uninstall(self) -> None:
        # Don't stop watchdog - it's a daemon thread and will die with the process.
        # Keep our signal handler active so we can catch 3rd SIGINT during
        # threading._shutdown() and trigger watchdog's os._exit().

        # Don't restore original handler - keep ours active for emergency exit
        self._loop = None
        self._soft_stop_event = None
        self._force_teardown_event = None

    def _handle_signal(self, signum: int, frame: object) -> None:
        if self._state == InterruptState.RUNNING:
            self._state = InterruptState.SOFT_STOP
            if self._loop is not None and self._soft_stop_event is not None:
                self._loop.call_soon_threadsafe(self._soft_stop_event.set)

        elif self._state == InterruptState.SOFT_STOP:
            self._state = InterruptState.FORCE_TEARDOWN
            if self._loop is not None and self._force_teardown_event is not None:
                self._loop.call_soon_threadsafe(self._force_teardown_event.set)

        else:
            self._state = InterruptState.HARD_EXIT
            self._exit_flag.set()  # Watchdog will os._exit()

    def _watchdog_loop(self) -> None:
        """Watch for exit flag and call os._exit() for clean termination.

        This ensures the process exits even when worker threads are blocked
        in C code that doesn't release the GIL.
        """
        while not self._stop_watchdog.is_set():
            if self._exit_flag.wait(timeout=0.1):
                os._exit(130)  # 128 + SIGINT(2)
