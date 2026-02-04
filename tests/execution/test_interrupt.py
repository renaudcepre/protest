"""Tests for keyboard interrupt handling."""

import asyncio
import signal
from typing import Annotated
from unittest.mock import patch

import pytest

from protest import ProTestSession, Use, fixture
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

        handler._handle_signal(signal.SIGINT, None)

        assert handler.state == InterruptState.SOFT_STOP

    def test_second_signal_transitions_to_force_teardown(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given SOFT_STOP state, when signal received, then state becomes FORCE_TEARDOWN."""
        handler, _ = interrupt_handler_with_loop
        handler._handle_signal(signal.SIGINT, None)

        handler._handle_signal(signal.SIGINT, None)

        assert handler.state == InterruptState.FORCE_TEARDOWN

    def test_third_signal_sets_exit_flag_for_watchdog(self) -> None:
        """Given FORCE_TEARDOWN state, when signal received, then exit flag is set for watchdog."""
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()

        # Mock os._exit for the entire test to prevent watchdog from exiting
        with patch("protest.execution.interrupt.os._exit"):
            handler.install(loop)

            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)

            assert handler.state == InterruptState.HARD_EXIT
            assert handler._exit_flag.is_set()

            # Stop watchdog before uninstalling to prevent os._exit after mock ends
            handler._stop_watchdog.set()
            handler._watchdog.join(timeout=0.5)
            handler.uninstall()
            loop.close()


class TestInterruptEvents:
    """Tests for asyncio.Event behavior."""

    def test_soft_stop_event_set_on_first_signal(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given installed handler, when first signal, then soft_stop_event is set."""
        handler, loop = interrupt_handler_with_loop
        assert not handler.soft_stop_event.is_set()

        handler._handle_signal(signal.SIGINT, None)
        loop.run_until_complete(asyncio.sleep(0))

        assert handler.soft_stop_event.is_set()

    def test_force_teardown_event_set_on_second_signal(
        self,
        interrupt_handler_with_loop: tuple[InterruptHandler, asyncio.AbstractEventLoop],
    ) -> None:
        """Given SOFT_STOP state, when second signal, then force_teardown_event is set."""
        handler, loop = interrupt_handler_with_loop
        handler._handle_signal(signal.SIGINT, None)

        handler._handle_signal(signal.SIGINT, None)
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
            handler._handle_signal(signal.SIGINT, None)

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

    def test_uninstall_keeps_signal_handler_for_emergency_exit(self) -> None:
        """Given installed handler, when uninstalled, then signal handler stays active.

        This is intentional: we keep the handler active to catch 3rd SIGINT during
        threading._shutdown() and trigger the watchdog's os._exit().
        """
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            our_handler = signal.getsignal(signal.SIGINT)
            handler.uninstall()

            # Handler should still be ours (not restored to original)
            assert signal.getsignal(signal.SIGINT) == our_handler
        finally:
            # Cleanup: stop watchdog and restore default handler
            handler._stop_watchdog.set()
            if handler._watchdog:
                handler._watchdog.join(timeout=0.5)
            signal.signal(signal.SIGINT, signal.default_int_handler)
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
            runner._interrupt_handler._handle_signal(signal.SIGINT, None)
            return await original_main_loop()

        runner._main_loop = patched_main_loop
        result = runner.run()

        assert result.interrupted is True
        assert executed == []

    def test_teardowns_still_run_on_normal_completion(self) -> None:
        """Given test with fixture, when test passes, then teardown is executed."""
        session = ProTestSession()
        teardown_called: list[str] = []

        @fixture()
        def resource() -> str:
            yield "value"
            teardown_called.append("cleaned")

        session.bind(resource)

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
                runner._interrupt_handler._handle_signal(signal.SIGINT, None)

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
