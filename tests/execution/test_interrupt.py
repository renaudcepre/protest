"""Tests for keyboard interrupt handling."""

import asyncio
import signal
from typing import Annotated

import pytest

from protest import ProTestSession, Use
from protest.core.runner import TestRunner
from protest.execution.interrupt import InterruptHandler, InterruptState


@pytest.fixture
def interrupt_handler_with_loop() -> tuple[InterruptHandler, asyncio.AbstractEventLoop]:
    """Create an interrupt handler with an installed event loop."""
    handler = InterruptHandler()
    loop = asyncio.new_event_loop()
    handler.install(loop)
    yield handler, loop
    handler.uninstall()
    loop.close()


class TestInterruptStateTransitions:
    """Tests for the interrupt state machine."""

    def test_initial_state_is_running(self) -> None:
        """Given a new handler, when created, then state is RUNNING."""
        handler = InterruptHandler()
        assert handler.state == InterruptState.RUNNING

    def test_first_signal_transitions_to_soft_stop(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given RUNNING state, when signal received, then state becomes SOFT_STOP."""
        handler, _ = interrupt_handler_with_loop

        handler.simulate_signal()

        assert handler.state == InterruptState.SOFT_STOP

    def test_second_signal_transitions_to_force_teardown(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given SOFT_STOP state, when signal received, then state becomes FORCE_TEARDOWN."""
        handler, _ = interrupt_handler_with_loop
        handler.simulate_signal()

        handler.simulate_signal()

        assert handler.state == InterruptState.FORCE_TEARDOWN

    def test_third_signal_raises_keyboard_interrupt(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given FORCE_TEARDOWN state, when signal received, then KeyboardInterrupt raised."""
        handler, _ = interrupt_handler_with_loop
        handler.simulate_signal()
        handler.simulate_signal()

        with pytest.raises(KeyboardInterrupt):
            handler.simulate_signal()

        assert handler.state == InterruptState.HARD_EXIT


class TestInterruptEvents:
    """Tests for asyncio.Event behavior."""

    def test_soft_stop_event_set_on_first_signal(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given installed handler, when first signal, then soft_stop_event is set."""
        handler, loop = interrupt_handler_with_loop
        assert not handler.soft_stop_event.is_set()

        handler.simulate_signal()
        loop.run_until_complete(asyncio.sleep(0))

        assert handler.soft_stop_event.is_set()

    def test_force_teardown_event_set_on_second_signal(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given SOFT_STOP state, when second signal, then force_teardown_event is set."""
        handler, loop = interrupt_handler_with_loop
        handler.simulate_signal()

        handler.simulate_signal()
        loop.run_until_complete(asyncio.sleep(0))

        assert handler.force_teardown_event.is_set()

    def test_events_not_available_before_install(self) -> None:
        """Given uninstalled handler, when events accessed, then RuntimeError raised."""
        handler = InterruptHandler()

        with pytest.raises(RuntimeError, match="not installed"):
            _ = handler.soft_stop_event

        with pytest.raises(RuntimeError, match="not installed"):
            _ = handler.force_teardown_event

    def test_events_available_after_install(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given installed handler, when events accessed, then they are available and not set."""
        handler, _ = interrupt_handler_with_loop

        assert handler.soft_stop_event is not None
        assert handler.force_teardown_event is not None
        assert not handler.soft_stop_event.is_set()
        assert not handler.force_teardown_event.is_set()


class TestInterruptProperties:
    """Tests for boolean query properties."""

    @pytest.mark.parametrize(
        "signal_count,expected_should_stop,expected_should_cancel,expected_should_skip_wait",
        [
            pytest.param(0, False, False, False, id="running_state"),
            pytest.param(1, True, False, False, id="soft_stop_state"),
            pytest.param(2, True, True, True, id="force_teardown_state"),
        ],
    )
    def test_boolean_properties_by_state(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
        signal_count: int,
        expected_should_stop: bool,
        expected_should_cancel: bool,
        expected_should_skip_wait: bool,
    ) -> None:
        """Given state transitions, then boolean properties reflect state correctly."""
        handler, _ = interrupt_handler_with_loop

        for _ in range(signal_count):
            handler.simulate_signal()

        assert handler.should_stop_new_tests is expected_should_stop
        assert handler.should_cancel_running is expected_should_cancel
        assert handler.should_skip_wait_pending is expected_should_skip_wait


class TestInterruptInstallUninstall:
    """Tests for install/uninstall lifecycle."""

    def test_install_registers_signal_handler(self) -> None:
        """Given uninstalled handler, when installed, then signal handler is changed."""
        original = signal.getsignal(signal.SIGINT)
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            current = signal.getsignal(signal.SIGINT)

            assert current != original
        finally:
            handler.uninstall()
            loop.close()

    def test_uninstall_restores_original_handler(self) -> None:
        """Given installed handler, when uninstalled, then original signal handler restored."""
        original = signal.getsignal(signal.SIGINT)
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler.uninstall()

            assert signal.getsignal(signal.SIGINT) == original
        finally:
            loop.close()

    def test_uninstall_clears_events(self) -> None:
        """Given installed handler, when uninstalled, then events become unavailable."""
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler.uninstall()

            with pytest.raises(RuntimeError, match="not installed"):
                _ = handler.soft_stop_event
        finally:
            loop.close()


class TestInterruptCallback:
    """Tests for optional interrupt callback."""

    @pytest.mark.parametrize(
        "signal_count,expected_states",
        [
            pytest.param(1, [InterruptState.SOFT_STOP], id="soft_stop"),
            pytest.param(
                2,
                [InterruptState.SOFT_STOP, InterruptState.FORCE_TEARDOWN],
                id="force_teardown",
            ),
        ],
    )
    def test_callback_called_on_state_transitions(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
        signal_count: int,
        expected_states: list[InterruptState],
    ) -> None:
        """Given callback set, when signals received, then callback called with correct states."""
        handler, _ = interrupt_handler_with_loop
        callback_states: list[InterruptState] = []

        def on_interrupt(state: InterruptState) -> None:
            callback_states.append(state)

        handler.set_interrupt_callback(on_interrupt)
        for _ in range(signal_count):
            handler.simulate_signal()

        assert callback_states == expected_states


class TestRunnerInterruptIntegration:
    """Integration tests with TestRunner."""

    def test_run_result_interrupted_false_on_normal_run(self) -> None:
        """Given normal test run, when completed, then interrupted is False."""
        session = ProTestSession()

        @session.test()
        def test_pass() -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        assert result.interrupted is False

    def test_run_result_interrupted_true_when_soft_stop_before_tests(self) -> None:
        """Given soft stop triggered before tests, then result.interrupted is True and no tests run."""
        session = ProTestSession()
        executed: list[str] = []

        @session.test()
        def test_one() -> None:
            executed.append("one")

        @session.test()
        def test_two() -> None:
            executed.append("two")

        runner = TestRunner(session)
        original_main_loop = runner._main_loop

        async def patched_main_loop() -> bool:
            runner._interrupt_handler.simulate_signal()
            return await original_main_loop()

        runner._main_loop = patched_main_loop
        result = runner.run()

        assert result.interrupted is True
        assert executed == []

    def test_teardowns_still_run_on_normal_completion(self) -> None:
        """Given test with fixture, when test passes, then teardown is executed."""
        session = ProTestSession()
        teardown_called: list[str] = []

        @session.fixture()
        def resource() -> str:
            yield "value"
            teardown_called.append("cleaned")

        @session.test()
        def test_with_fixture(res: Annotated[str, Use(resource)]) -> None:
            assert res == "value"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        expected_teardown_count = 1
        assert len(teardown_called) == expected_teardown_count

    def test_soft_stop_prevents_pending_tests_from_starting(self) -> None:
        """Given soft stop triggered during first test, then pending tests are skipped."""
        session = ProTestSession(concurrency=1)
        executed: list[str] = []
        runner: TestRunner | None = None

        @session.test()
        def test_first() -> None:
            executed.append("first")
            if runner:
                runner._interrupt_handler.simulate_signal()

        @session.test()
        def test_second() -> None:
            executed.append("second")

        @session.test()
        def test_third() -> None:
            executed.append("third")

        runner = TestRunner(session)
        result = runner.run()

        assert result.interrupted is True
        assert "first" in executed
        assert "second" not in executed
        assert "third" not in executed
