"""Test runner orchestration."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from protest.core.collector import Collector
from protest.core.execution import ParallelExecutor, SuiteManager, TestExecutor
from protest.core.outcome import OutcomeBuilder
from protest.core.session import ProTestSession  # noqa: TC001 — used at runtime
from protest.core.tracker import SuiteTracker
from protest.entities import (
    RunResult,
    SessionResult,
    SessionSetupInfo,
    TestCounts,
)
from protest.evals.types import EvalCaseResult, EvalScore, EvalSuiteReport
from protest.events.types import Event
from protest.execution.capture import (
    GlobalCapturePatch,
    reset_event_bus,
    set_event_bus,
    set_session_setup_capture,
)
from protest.execution.context import cancellation_event
from protest.execution.interrupt import InterruptHandler

if TYPE_CHECKING:
    from protest.entities.events import TestResult


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
        self._eval_results: dict[str, list[EvalCaseResult]] = {}

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

    def _collect_eval_result(self, result: TestResult) -> None:
        """Internal handler: collect eval results from TEST_PASS/FAIL events."""
        if not result.is_eval or result.eval_payload is None:
            return
        suite_name = result.suite_path.root_name if result.suite_path else "evals"
        case_result = _build_eval_case_result(result)
        self._eval_results.setdefault(suite_name, []).append(case_result)

    async def _main_loop(self) -> bool:  # noqa: PLR0915
        """The main async loop for running tests."""
        session_start = time.perf_counter()

        # Register internal eval collector before tests run
        self._eval_results.clear()
        self._session.events.on(Event.TEST_PASS, self._collect_eval_result)
        self._session.events.on(Event.TEST_FAIL, self._collect_eval_result)

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
        bus_token = set_event_bus(self._session.events)
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
                        # Emit EVAL_SUITE_END for eval suites
                        await self._emit_eval_suite_end(suite_path)

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
            reset_event_bus(bus_token)

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
        # Unregister eval collector
        self._session.events.off(Event.TEST_PASS, self._collect_eval_result)
        self._session.events.off(Event.TEST_FAIL, self._collect_eval_result)

        return (
            total_counts.failed == 0
            and total_counts.errored == 0
            and total_counts.xpassed == 0
        )

    async def _emit_eval_suite_end(self, suite_path: Any) -> None:
        """Emit EVAL_SUITE_END if this suite_path corresponds to an eval suite."""
        suite_name = (
            suite_path.root_name
            if hasattr(suite_path, "root_name")
            else str(suite_path)
        )
        eval_cases = self._eval_results.get(suite_name)
        if not eval_cases:
            return
        report = EvalSuiteReport(
            suite_name=suite_name,
            cases=tuple(eval_cases),
            duration=sum(c.duration for c in eval_cases),
        )
        await self._session.events.emit(Event.EVAL_SUITE_END, report)


def _build_eval_case_result(result: TestResult) -> EvalCaseResult:
    """Build EvalCaseResult from a TestResult with eval_payload."""
    payload = result.eval_payload
    assert payload is not None
    return EvalCaseResult(
        case_name=payload.case_name or "",
        node_id=result.node_id,
        scores=tuple(
            EvalScore(
                name=name,
                value=entry.value,
            )
            for name, entry in payload.scores.items()
        ),
        duration=payload.task_duration,
        passed=not (result.error is not None or not payload.passed),
        inputs=payload.inputs,
        output=payload.output,
        expected_output=payload.expected_output,
        case_hash=payload.case_hash,
        eval_hash=payload.eval_hash,
    )
