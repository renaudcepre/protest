"""Tests for EventBus - sync/async handlers and fire-and-forget."""

import asyncio

import pytest

from protest.events.bus import EventBus
from protest.events.types import Event


class TestHandlerRegistration:
    """Handler registration and basic emit."""

    @pytest.mark.asyncio
    async def test_sync_handler_called_on_emit(self) -> None:
        """Sync handlers are called when event is emitted."""
        bus = EventBus()
        received_data: list[str] = []

        def handler(data: str) -> None:
            received_data.append(data)

        bus.on(Event.TEST_PASS, handler)
        await bus.emit(Event.TEST_PASS, "test_data")

        assert received_data == ["test_data"]

    @pytest.mark.asyncio
    async def test_async_handler_called_on_emit(self) -> None:
        """Async handlers are called when event is emitted."""
        bus = EventBus()
        received_data: list[str] = []

        async def handler(data: str) -> None:
            received_data.append(data)

        bus.on(Event.TEST_PASS, handler)
        await bus.emit(Event.TEST_PASS, "test_data")
        await bus.wait_pending()

        assert received_data == ["test_data"]

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self) -> None:
        """Multiple handlers can subscribe to the same event."""
        bus = EventBus()
        received_messages: list[str] = []

        def handler1(data: str) -> None:
            received_messages.append(f"h1_{data}")

        def handler2(data: str) -> None:
            received_messages.append(f"h2_{data}")

        bus.on(Event.TEST_PASS, handler1)
        bus.on(Event.TEST_PASS, handler2)
        await bus.emit(Event.TEST_PASS, "data")

        assert "h1_data" in received_messages
        assert "h2_data" in received_messages

    @pytest.mark.asyncio
    async def test_emit_without_data(self) -> None:
        """Events can be emitted without data."""
        bus = EventBus()
        called = False

        def handler() -> None:
            nonlocal called
            called = True

        bus.on(Event.SESSION_START, handler)
        await bus.emit(Event.SESSION_START)

        assert called


class TestAsyncFireAndForget:
    """Async handlers run as fire-and-forget tasks."""

    @pytest.mark.asyncio
    async def test_async_handler_does_not_block_emit(self) -> None:
        """Async handlers don't block the emit call."""
        bus = EventBus()
        handler_finished = False

        async def slow_handler(data: str) -> None:
            nonlocal handler_finished
            await asyncio.sleep(0.1)
            handler_finished = True

        bus.on(Event.TEST_PASS, slow_handler)
        await bus.emit(Event.TEST_PASS, "data")

        await asyncio.sleep(0)
        assert not handler_finished

        await bus.wait_pending()
        assert handler_finished

    @pytest.mark.asyncio
    async def test_wait_pending_waits_for_all_async_handlers(self) -> None:
        """wait_pending() waits for all fire-and-forget handlers."""
        bus = EventBus()
        finished: list[int] = []

        async def handler1(data: str) -> None:
            await asyncio.sleep(0.05)
            finished.append(1)

        async def handler2(data: str) -> None:
            await asyncio.sleep(0.1)
            finished.append(2)

        bus.on(Event.TEST_PASS, handler1)
        bus.on(Event.TEST_PASS, handler2)
        await bus.emit(Event.TEST_PASS, "data")

        assert len(finished) == 0

        await bus.wait_pending()
        assert 1 in finished
        assert 2 in finished


class TestErrorHandling:
    """Handler errors should not crash other handlers."""

    @pytest.mark.asyncio
    async def test_sync_handler_error_does_not_crash(self) -> None:
        """Sync handler error doesn't prevent other handlers."""
        bus = EventBus()
        second_called = False

        def failing_handler(data: str) -> None:
            raise ValueError("Handler error")

        def working_handler(data: str) -> None:
            nonlocal second_called
            second_called = True

        bus.on(Event.TEST_PASS, failing_handler)
        bus.on(Event.TEST_PASS, working_handler)

        await bus.emit(Event.TEST_PASS, "data")

        assert second_called

    @pytest.mark.asyncio
    async def test_async_handler_error_does_not_crash(self) -> None:
        """Async handler error doesn't prevent other handlers."""
        bus = EventBus()
        second_called = False

        async def failing_handler(data: str) -> None:
            raise ValueError("Async handler error")

        async def working_handler(data: str) -> None:
            nonlocal second_called
            second_called = True

        bus.on(Event.TEST_PASS, failing_handler)
        bus.on(Event.TEST_PASS, working_handler)

        await bus.emit(Event.TEST_PASS, "data")
        await bus.wait_pending()

        assert second_called


class TestEventTypes:
    """Different event types are handled correctly."""

    @pytest.mark.asyncio
    async def test_handlers_only_receive_subscribed_events(self) -> None:
        """Handlers only receive events they subscribed to."""
        bus = EventBus()
        pass_received: list[str] = []
        fail_received: list[str] = []

        def pass_handler(data: str) -> None:
            pass_received.append(data)

        def fail_handler(data: str) -> None:
            fail_received.append(data)

        bus.on(Event.TEST_PASS, pass_handler)
        bus.on(Event.TEST_FAIL, fail_handler)

        await bus.emit(Event.TEST_PASS, "pass_data")
        await bus.emit(Event.TEST_FAIL, "fail_data")

        assert pass_received == ["pass_data"]
        assert fail_received == ["fail_data"]


class TestEmitAndCollect:
    """emit_and_collect chains handlers and returns modified data."""

    @pytest.mark.asyncio
    async def test_emit_and_collect_returns_data_unchanged(self) -> None:
        """Without handlers, emit_and_collect returns original data."""
        bus = EventBus()

        result = await bus.emit_and_collect(Event.COLLECTION_FINISH, ["item1", "item2"])

        assert result == ["item1", "item2"]

    @pytest.mark.asyncio
    async def test_emit_and_collect_sync_handler_modifies_data(self) -> None:
        """Sync handler can modify and return data."""
        bus = EventBus()

        def filter_handler(items: list[str]) -> list[str]:
            return [item for item in items if "keep" in item]

        bus.on(Event.COLLECTION_FINISH, filter_handler)

        result = await bus.emit_and_collect(
            Event.COLLECTION_FINISH, ["keep_a", "drop_b", "keep_c"]
        )

        assert result == ["keep_a", "keep_c"]

    @pytest.mark.asyncio
    async def test_emit_and_collect_async_handler_modifies_data(self) -> None:
        """Async handler can modify and return data."""
        bus = EventBus()

        async def async_filter(items: list[str]) -> list[str]:
            await asyncio.sleep(0)
            return [item.upper() for item in items]

        bus.on(Event.COLLECTION_FINISH, async_filter)

        result = await bus.emit_and_collect(Event.COLLECTION_FINISH, ["a", "b"])

        assert result == ["A", "B"]

    @pytest.mark.asyncio
    async def test_emit_and_collect_chains_multiple_handlers(self) -> None:
        """Multiple handlers chain their results."""
        bus = EventBus()

        def add_prefix(items: list[str]) -> list[str]:
            return [f"prefix_{item}" for item in items]

        def add_suffix(items: list[str]) -> list[str]:
            return [f"{item}_suffix" for item in items]

        bus.on(Event.COLLECTION_FINISH, add_prefix)
        bus.on(Event.COLLECTION_FINISH, add_suffix)

        result = await bus.emit_and_collect(Event.COLLECTION_FINISH, ["a", "b"])

        assert result == ["prefix_a_suffix", "prefix_b_suffix"]

    @pytest.mark.asyncio
    async def test_emit_and_collect_handler_returning_none_preserves_data(self) -> None:
        """Handler returning None keeps previous data."""
        bus = EventBus()

        def pass_through(items: list[str]) -> None:
            pass

        def transform(items: list[str]) -> list[str]:
            return [item.upper() for item in items]

        bus.on(Event.COLLECTION_FINISH, pass_through)
        bus.on(Event.COLLECTION_FINISH, transform)

        result = await bus.emit_and_collect(Event.COLLECTION_FINISH, ["a", "b"])

        assert result == ["A", "B"]

    @pytest.mark.asyncio
    async def test_emit_and_collect_handler_error_continues(self) -> None:
        """Handler error doesn't break chain, keeps previous data."""
        bus = EventBus()

        def failing_handler(items: list[str]) -> list[str]:
            raise ValueError("boom")

        def transform(items: list[str]) -> list[str]:
            return [item.upper() for item in items]

        bus.on(Event.COLLECTION_FINISH, failing_handler)
        bus.on(Event.COLLECTION_FINISH, transform)

        result = await bus.emit_and_collect(Event.COLLECTION_FINISH, ["a", "b"])

        assert result == ["A", "B"]
