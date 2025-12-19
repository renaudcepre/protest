"""Test that sync handlers are serialized per plugin to avoid race conditions."""

import asyncio
import time

import pytest

from protest.events.bus import EventBus
from protest.events.types import Event


class CounterPlugin:
    """Plugin with shared mutable state - vulnerable to race conditions."""

    def __init__(self) -> None:
        self.count = 0

    def on_test_pass(self, result: dict) -> None:
        # Artificially widen the race window
        current = self.count
        time.sleep(0.001)  # Force context switch
        self.count = current + 1


@pytest.mark.asyncio
async def test_sync_handlers_are_serialized_per_plugin() -> None:
    """Concurrent emits should not cause race conditions on plugin state.

    Without serialization, multiple threads can:
    1. Read the same counter value
    2. Sleep (simulating work)
    3. Write back incremented value, losing other increments

    With per-plugin serialization, handlers for the same plugin
    execute one at a time, preventing lost updates.
    """
    bus = EventBus()
    plugin = CounterPlugin()

    # Register the handler
    bus.on(Event.TEST_PASS, plugin.on_test_pass)

    # Emit 20 events concurrently
    num_events = 20

    async def emit_one() -> None:
        await bus.emit(Event.TEST_PASS, {"name": "test"})

    # Launch all emits concurrently
    await asyncio.gather(*[emit_one() for _ in range(num_events)])

    # Without serialization: count will be much less than num_events
    # With serialization: count should equal num_events exactly
    assert plugin.count == num_events, (
        f"Race condition detected! Expected {num_events}, got {plugin.count}. "
        f"Lost {num_events - plugin.count} increments."
    )
