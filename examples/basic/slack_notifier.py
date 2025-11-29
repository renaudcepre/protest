"""Fake Slack notifier to test async fire-and-forget handlers."""

import asyncio

from protest.events.data import SessionResult, TestResult


class FakeSlackNotifier:
    """Simulates a slow async Slack webhook."""

    def __init__(self, delay: float = 1.0) -> None:
        self._delay = delay

    async def on_test_fail(self, result: TestResult) -> None:
        """Async handler - runs as fire-and-forget task."""
        print(f"    [Slack] Sending failure notification for {result.name}...")
        await asyncio.sleep(self._delay)
        print(f"    [Slack] ✓ Notified about {result.name} failure")

    async def on_session_end(self, result: SessionResult) -> None:
        """Async handler - runs as fire-and-forget task."""
        print("[Slack] Sending session summary...")
        await asyncio.sleep(self._delay)
        print("[Slack] ✓ Session summary sent")
