"""Fake Slack notifier to test async fire-and-forget handlers."""

import asyncio

from protest.events.bus import EventBus
from protest.events.data import SessionResult, TestResult
from protest.events.types import Event


class FakeSlackNotifier:
    """Simulates a slow async Slack webhook."""

    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay

    def register(self, events: EventBus) -> None:
        """Register async handlers (fire-and-forget)."""
        events.on(Event.TEST_FAIL, self.notify_failure)
        events.on(Event.SESSION_END, self.notify_session_end)

    async def notify_failure(self, result: TestResult) -> None:
        """Async handler - runs as fire-and-forget task."""
        print(f"    [Slack] Sending failure notification for {result.name}...")
        await asyncio.sleep(self._delay)
        print(f"    [Slack] ✓ Notified about {result.name} failure")

    async def notify_session_end(self, result: SessionResult) -> None:
        """Async handler - runs as fire-and-forget task."""
        print("[Slack] Sending session summary...")
        await asyncio.sleep(self._delay)
        print("[Slack] ✓ Session summary sent")
