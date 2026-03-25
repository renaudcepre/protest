"""Test outcome classification and building."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from protest.entities import SuitePath, TestCounts, TestOutcome, TestResult
from protest.events.types import Event

if TYPE_CHECKING:
    from protest.entities.events import EvalPayload


class OutcomeType(Enum):
    """Classification of test execution outcomes."""

    SKIP = auto()
    PASS = auto()
    XPASS = auto()
    FAIL = auto()
    XFAIL = auto()
    ERROR = auto()


@dataclass(slots=True)
class TestExecutionResult:
    """Internal result of test execution before outcome determination."""

    test_name: str
    node_id: str
    suite_path: SuitePath | None = None
    duration: float = 0
    output: str = ""
    error: Exception | None = None
    is_fixture_error: bool = False
    skip_reason: str | None = None
    xfail_reason: str | None = None
    timeout: float | None = None
    attempt: int = 1
    max_attempts: int = 1
    previous_errors: tuple[Exception, ...] = ()
    is_eval: bool = False
    eval_payload: EvalPayload | None = None
    log_records: tuple[Any, ...] = ()


class OutcomeBuilder:
    """Builds TestOutcome from test execution results."""

    def build(self, exec_result: TestExecutionResult) -> TestOutcome:
        """Build a TestOutcome from execution result."""
        outcome_type = self._classify(exec_result)

        match outcome_type:
            case OutcomeType.SKIP:
                return self._build_skip(exec_result)
            case OutcomeType.PASS:
                return self._build_pass(exec_result)
            case OutcomeType.XPASS:
                return self._build_xpass(exec_result)
            case OutcomeType.ERROR:
                return self._build_error(exec_result)
            case OutcomeType.XFAIL:
                return self._build_xfail(exec_result)
            case OutcomeType.FAIL:
                return self._build_fail(exec_result)

    def _classify(self, exec_result: TestExecutionResult) -> OutcomeType:
        match (
            exec_result.skip_reason,
            exec_result.error,
            exec_result.is_fixture_error,
            exec_result.xfail_reason,
        ):
            case (str(), _, _, _):
                return OutcomeType.SKIP
            case (None, None, _, str()):
                return OutcomeType.XPASS
            case (None, None, _, None):
                return OutcomeType.PASS
            case (None, Exception(), True, _):
                return OutcomeType.ERROR
            case (None, Exception(), False, str()):
                return OutcomeType.XFAIL
            case _:
                return OutcomeType.FAIL

    def _base_kwargs(self, er: TestExecutionResult) -> dict[str, object]:
        """Common TestResult kwargs from an execution result."""
        return {
            "name": er.test_name,
            "node_id": er.node_id,
            "suite_path": er.suite_path,
            "duration": er.duration,
            "output": er.output,
            "timeout": er.timeout,
            "attempt": er.attempt,
            "max_attempts": er.max_attempts,
            "previous_errors": er.previous_errors,
            "is_eval": er.is_eval,
            "eval_payload": er.eval_payload,
            "log_records": er.log_records,
        }

    def _build_skip(self, er: TestExecutionResult) -> TestOutcome:
        kw = self._base_kwargs(er)
        kw.update(duration=0, output="", skip_reason=er.skip_reason)
        return TestOutcome(TestResult(**kw), TestCounts(skipped=1), Event.TEST_SKIP)  # type: ignore[arg-type]

    def _build_pass(self, er: TestExecutionResult) -> TestOutcome:
        return TestOutcome(
            TestResult(**self._base_kwargs(er)), TestCounts(passed=1), Event.TEST_PASS
        )  # type: ignore[arg-type]

    def _build_xpass(self, er: TestExecutionResult) -> TestOutcome:
        kw = self._base_kwargs(er)
        kw["xfail_reason"] = er.xfail_reason
        return TestOutcome(TestResult(**kw), TestCounts(xpassed=1), Event.TEST_XPASS)  # type: ignore[arg-type]

    def _build_error(self, er: TestExecutionResult) -> TestOutcome:
        kw = self._base_kwargs(er)
        kw.update(error=er.error, is_fixture_error=True)
        return TestOutcome(TestResult(**kw), TestCounts(errored=1), Event.TEST_FAIL)  # type: ignore[arg-type]

    def _build_xfail(self, er: TestExecutionResult) -> TestOutcome:
        kw = self._base_kwargs(er)
        kw.update(error=er.error, xfail_reason=er.xfail_reason)
        return TestOutcome(TestResult(**kw), TestCounts(xfailed=1), Event.TEST_XFAIL)  # type: ignore[arg-type]

    def _build_fail(self, er: TestExecutionResult) -> TestOutcome:
        kw = self._base_kwargs(er)
        kw["error"] = er.error
        return TestOutcome(TestResult(**kw), TestCounts(failed=1), Event.TEST_FAIL)  # type: ignore[arg-type]
