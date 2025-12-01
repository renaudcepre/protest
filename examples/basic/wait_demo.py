"""Demo showcasing the spinner for async handlers."""

import asyncio
from time import sleep
from protest.events.types import Event
from protest import ProTestSession, ProTestSuite
from protest.events.data import SessionResult
from protest.plugin import PluginBase

session = ProTestSession()
suite = ProTestSuite("Quick Tests")
session.add_suite(suite)


class SlowWebhookNotifier(PluginBase):
    """Simulates multiple slow async handlers (Slack, Discord, etc.)."""

    async def on_session_end(self, result: SessionResult) -> None:
        await asyncio.sleep(2.0)

    async def send_to_discord(self, result: SessionResult) -> None:
        await asyncio.sleep(1.5)

    async def send_metrics(self, result: SessionResult) -> None:
        await asyncio.sleep(1.0)

    def setup(self, session: ProTestSession) -> None:
        session.events.on(Event.SESSION_END, self.send_to_discord)
        session.events.on(Event.SESSION_END, self.send_metrics)


session.use(SlowWebhookNotifier())


@suite.test()
def test_one() -> None:
    sleep(1)
    assert True


@suite.test()
def test_two() -> None:
    sleep(2)
    assert True


@suite.test()
def test_three() -> None:
    sleep(1.4)
    assert True
