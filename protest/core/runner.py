"""Test runner orchestration."""

import asyncio
import time

from protest.core.collector import Collector
from protest.core.execution import ParallelExecutor, SuiteManager, TestExecutor
from protest.core.outcome import OutcomeBuilder
from protest.core.session import ProTestSession
from protest.core.tracker import SuiteTracker
from protest.entities import (
    RunResult,
    SessionResult,
    SessionSetupInfo,
    TestCounts,
)
from protest.events.types import Event
from protest.execution.capture import (
    GlobalCapturePatch,
    set_session_setup_capture,
)
from protest.execution.context import cancellation_event
from protest.execution.interrupt import InterruptHandler


class TestRunner:
    """Executes tests with parallel support and fixture lifecycle management.

    Runs all tests in parallel (cross-suite) and automatically triggers
    suite fixture teardown when all tests of a suite complete.
    """

    def __init__(self, session: ProTestSession) -> None:
        self._session = session
        self._outcome_builder = OutcomeBuilder()
        self._interrupt_handler = InterruptHandler()
        self._interrupted = False
        self._force_interrupt_emitted = False

        # Extracted components
        self._suite_manager = SuiteManager(session)
        self._test_executor = TestExecutor(session, self._outcome_builder)
        self._parallel_executor = ParallelExecutor(
            session=session,
            test_executor=self._test_executor,
            suite_manager=self._suite_manager,
            interrupt_handler=self._interrupt_handler,
        )

    def run(self) -> RunResult:
        """Run the test session synchronously. Returns RunResult with success and interrupted status."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._interrupt_handler.install(loop)
        try:
            success = loop.run_until_complete(self._main_loop())
            return RunResult(success=success, interrupted=self._interrupted)
        except KeyboardInterrupt:
            return RunResult(success=False, interrupted=True)
        finally:
            self._interrupt_handler.uninstall()
            loop.close()

    async def _main_loop(self) -> bool:
        """The main async loop for running tests."""
        session_start = time.perf_counter()

        collector = Collector()
        items = collector.collect(self._session)

        items = await self._session.events.emit_and_collect(
            Event.COLLECTION_FINISH, items
        )

        await self._session.events.emit(Event.SESSION_START)

        tracker = SuiteTracker.from_items(items)
        suite_semaphores = self._parallel_executor.build_suite_semaphores(items)

        total_counts = TestCounts()
        # Inject cancellation event into context for teardown awareness
        cancel_token = cancellation_event.set(
            self._interrupt_handler.force_teardown_event
        )
        try:
            with GlobalCapturePatch(show_output=not self._session.capture):
                async with self._session:
                    setup_start = time.perf_counter()
                    set_session_setup_capture(True)
                    try:
                        await self._session.resolve_autouse()
                    finally:
                        set_session_setup_capture(False)
                    setup_duration = time.perf_counter() - setup_start
                    self._session.set_setup_duration(setup_duration)
                    await self._session.events.emit(
                        Event.SESSION_SETUP_DONE,
                        SessionSetupInfo(duration=setup_duration),
                    )

                    self._suite_manager.reset()

                    total_counts = await self._parallel_executor.run(
                        items,
                        suite_semaphores,
                        tracker,
                    )

                    # Emit suite results in reverse order (LIFO)
                    for suite_path in reversed(
                        list(self._suite_manager.started_suites)
                    ):
                        suite_result = self._suite_manager.build_result(suite_path)
                        await self._session.events.emit(Event.SUITE_END, suite_result)

                    await self._session.events.emit(Event.SESSION_TEARDOWN_START)
        finally:
            # Emit SESSION_INTERRUPTED if force_teardown was triggered during teardown
            # (only if not already emitted during test execution)
            if (
                self._interrupt_handler.force_teardown_event.is_set()
                and not self._parallel_executor.force_interrupt_emitted
            ):
                await self._session.events.emit(Event.SESSION_INTERRUPTED, True)
                self._force_interrupt_emitted = True
            cancellation_event.reset(cancel_token)

        if self._interrupt_handler.should_stop_new_tests:
            self._interrupted = True

        session_duration = time.perf_counter() - session_start
        session_result = SessionResult(
            passed=total_counts.passed,
            failed=total_counts.failed,
            errors=total_counts.errored,
            skipped=total_counts.skipped,
            xfailed=total_counts.xfailed,
            xpassed=total_counts.xpassed,
            duration=session_duration,
            setup_duration=self._session.setup_duration,
            teardown_duration=self._session.teardown_duration,
            interrupted=self._interrupted,
        )
        await self._session.events.emit(Event.SESSION_END, session_result)

        if not self._interrupt_handler.should_skip_wait_pending:
            if self._session.events.pending_count > 0:
                await self._session.events.emit(
                    Event.WAITING_HANDLERS, self._session.events.pending_count
                )
            await self._session.events.wait_pending()

        await self._session.events.emit(Event.SESSION_COMPLETE, session_result)
        return (
            total_counts.failed == 0
            and total_counts.errored == 0
            and total_counts.xpassed == 0
        )
