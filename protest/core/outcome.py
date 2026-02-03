"""Test outcome classification and building."""

from dataclasses import dataclass
from enum import Enum, auto

from protest.entities import SuitePath, TestCounts, TestOutcome, TestResult
from protest.events.types import Event


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


class OutcomeBuilder:
    """Builds TestOutcome from test execution results."""

    def build(self, exec_result: TestExecutionResult) -> TestOutcome:
        """Build a TestOutcome from execution result by classifying and constructing."""
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
        """Classify execution result into outcome type."""
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

    def _build_skip(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            skip_reason=exec_result.skip_reason,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(skipped=1), Event.TEST_SKIP)

    def _build_pass(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            duration=exec_result.duration,
            output=exec_result.output,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(passed=1), Event.TEST_PASS)

    def _build_xpass(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            duration=exec_result.duration,
            output=exec_result.output,
            xfail_reason=exec_result.xfail_reason,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(xpassed=1), Event.TEST_XPASS)

    def _build_error(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            error=exec_result.error,
            duration=exec_result.duration,
            output=exec_result.output,
            is_fixture_error=True,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(errored=1), Event.TEST_FAIL)

    def _build_xfail(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            error=exec_result.error,
            duration=exec_result.duration,
            output=exec_result.output,
            xfail_reason=exec_result.xfail_reason,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(xfailed=1), Event.TEST_XFAIL)

    def _build_fail(self, exec_result: TestExecutionResult) -> TestOutcome:
        result = TestResult(
            name=exec_result.test_name,
            node_id=exec_result.node_id,
            suite_path=exec_result.suite_path,
            error=exec_result.error,
            duration=exec_result.duration,
            output=exec_result.output,
            timeout=exec_result.timeout,
            attempt=exec_result.attempt,
            max_attempts=exec_result.max_attempts,
            previous_errors=exec_result.previous_errors,
        )
        return TestOutcome(result, TestCounts(failed=1), Event.TEST_FAIL)
