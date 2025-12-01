"""Demo showcasing the spinner for async handlers."""

import asyncio

from protest import ProTestSession, ProTestSuite
from protest.events.data import SessionResult
from protest.plugin import PluginBase

session = ProTestSession()
suite = ProTestSuite("Quick Tests")
session.add_suite(suite)


class SlowWebhookNotifier(PluginBase):
    """Simulates multiple slow async handlers (Slack, Discord, etc.)."""

    async def on_session_end(self, result: SessionResult) -> None:
        print("\n[Slack] Sending summary to #testing channel...")
        await asyncio.sleep(3.0)
        print("[Slack] ✓ Done")

    async def send_to_discord(self, result: SessionResult) -> None:
        print("[Discord] Posting results...")
        await asyncio.sleep(3.5)
        print("[Discord] ✓ Done")

    async def send_metrics(self, result: SessionResult) -> None:
        print("[Metrics] Pushing to Datadog...")
        await asyncio.sleep(1.0)
        print("[Metrics] ✓ Done")

    def setup(self, sess: ProTestSession) -> None:
        from protest.events.types import Event

        sess.events.on(Event.SESSION_END, self.send_to_discord)
        sess.events.on(Event.SESSION_END, self.send_metrics)


session.use(SlowWebhookNotifier())


@suite.test()
def test_one() -> None:
    assert True


@suite.test()
def test_two() -> None:
    assert True


@suite.test()
def test_three() -> None:
    assert True
