"""Tests for keyboard interrupt handling."""

import asyncio
import signal
from typing import Annotated

import pytest

from protest import ProTestSession, Use
from protest.core.runner import TestRunner
from protest.execution.interrupt import InterruptHandler, InterruptState


class TestInterruptStateTransitions:
    """Tests for the interrupt state machine."""

    def test_initial_state_is_running(self) -> None:
        handler = InterruptHandler()
        assert handler.state == InterruptState.RUNNING

    def test_first_signal_transitions_to_soft_stop(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.state == InterruptState.SOFT_STOP
        finally:
            handler.uninstall()
            loop.close()

    def test_second_signal_transitions_to_force_teardown(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.state == InterruptState.FORCE_TEARDOWN
        finally:
            handler.uninstall()
            loop.close()

    def test_third_signal_raises_keyboard_interrupt(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)

            with pytest.raises(KeyboardInterrupt):
                handler._handle_signal(signal.SIGINT, None)

            assert handler.state == InterruptState.HARD_EXIT
        finally:
            handler.uninstall()
            loop.close()


class TestInterruptEvents:
    """Tests for asyncio.Event behavior."""

    def test_soft_stop_event_set_on_first_signal(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            assert not handler.soft_stop_event.is_set()

            handler._handle_signal(signal.SIGINT, None)
            loop.run_until_complete(asyncio.sleep(0))

            assert handler.soft_stop_event.is_set()
        finally:
            handler.uninstall()
            loop.close()

    def test_force_teardown_event_set_on_second_signal(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            loop.run_until_complete(asyncio.sleep(0))

            assert handler.force_teardown_event.is_set()
        finally:
            handler.uninstall()
            loop.close()

    def test_events_not_available_before_install(self) -> None:
        handler = InterruptHandler()

        with pytest.raises(RuntimeError, match="not installed"):
            _ = handler.soft_stop_event

        with pytest.raises(RuntimeError, match="not installed"):
            _ = handler.force_teardown_event

    def test_events_available_after_install(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            assert handler.soft_stop_event is not None
            assert handler.force_teardown_event is not None
            assert not handler.soft_stop_event.is_set()
            assert not handler.force_teardown_event.is_set()
        finally:
            handler.uninstall()
            loop.close()


class TestInterruptProperties:
    """Tests for boolean query properties."""

    def test_should_stop_new_tests_false_when_running(self) -> None:
        handler = InterruptHandler()
        assert handler.should_stop_new_tests is False

    def test_should_stop_new_tests_true_when_soft_stop(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_stop_new_tests is True
        finally:
            handler.uninstall()
            loop.close()

    def test_should_stop_new_tests_true_when_force_teardown(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_stop_new_tests is True
        finally:
            handler.uninstall()
            loop.close()

    def test_should_cancel_running_false_when_running(self) -> None:
        handler = InterruptHandler()
        assert handler.should_cancel_running is False

    def test_should_cancel_running_false_when_soft_stop(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_cancel_running is False
        finally:
            handler.uninstall()
            loop.close()

    def test_should_cancel_running_true_when_force_teardown(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_cancel_running is True
        finally:
            handler.uninstall()
            loop.close()

    def test_should_skip_wait_pending_false_when_soft_stop(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_skip_wait_pending is False
        finally:
            handler.uninstall()
            loop.close()

    def test_should_skip_wait_pending_true_when_force_teardown(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)
            assert handler.should_skip_wait_pending is True
        finally:
            handler.uninstall()
            loop.close()


class TestInterruptInstallUninstall:
    """Tests for install/uninstall lifecycle."""

    def test_install_registers_signal_handler(self) -> None:
        original = signal.getsignal(signal.SIGINT)
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        try:
            handler.install(loop)
            current = signal.getsignal(signal.SIGINT)
            assert current != original
            assert current == handler._handle_signal
        finally:
            handler.uninstall()
            loop.close()

    def test_uninstall_restores_original_handler(self) -> None:
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

    def test_callback_called_on_soft_stop(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        callback_states: list[InterruptState] = []

        def on_interrupt(state: InterruptState) -> None:
            callback_states.append(state)

        try:
            handler.set_interrupt_callback(on_interrupt)
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)

            expected_callback_count = 1
            assert len(callback_states) == expected_callback_count
            assert callback_states[0] == InterruptState.SOFT_STOP
        finally:
            handler.uninstall()
            loop.close()

    def test_callback_called_on_force_teardown(self) -> None:
        handler = InterruptHandler()
        loop = asyncio.new_event_loop()
        callback_states: list[InterruptState] = []

        def on_interrupt(state: InterruptState) -> None:
            callback_states.append(state)

        try:
            handler.set_interrupt_callback(on_interrupt)
            handler.install(loop)
            handler._handle_signal(signal.SIGINT, None)
            handler._handle_signal(signal.SIGINT, None)

            expected_callback_count = 2
            assert len(callback_states) == expected_callback_count
            assert callback_states[0] == InterruptState.SOFT_STOP
            assert callback_states[1] == InterruptState.FORCE_TEARDOWN
        finally:
            handler.uninstall()
            loop.close()


class TestRunnerInterruptIntegration:
    """Integration tests with TestRunner."""

    def test_run_result_interrupted_false_on_normal_run(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_pass() -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        assert result.interrupted is False

    def test_run_result_interrupted_true_when_soft_stop_before_tests(self) -> None:
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
            runner._interrupt_handler._state = InterruptState.SOFT_STOP
            runner._interrupt_handler._soft_stop_event.set()
            return await original_main_loop()

        runner._main_loop = patched_main_loop
        result = runner.run()

        assert result.interrupted is True
        assert executed == []

    def test_teardowns_still_run_on_normal_completion(self) -> None:
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
        session = ProTestSession(concurrency=1)
        executed: list[str] = []
        runner: TestRunner | None = None

        @session.test()
        def test_first() -> None:
            executed.append("first")
            if runner:
                runner._interrupt_handler._state = InterruptState.SOFT_STOP
                runner._interrupt_handler._soft_stop_event.set()

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

    def test_keyboard_interrupt_returns_interrupted_result(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_raises_kb() -> None:
            raise KeyboardInterrupt

        runner = TestRunner(session)
        result = runner.run()

        assert result.interrupted is True
        assert result.success is False
