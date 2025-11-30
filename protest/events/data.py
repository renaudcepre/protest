"""Dataclasses for event payloads. Extensible without breaking signatures."""

from dataclasses import dataclass


@dataclass
class TestCounts:
    """Counts of test results."""

    passed: int = 0
    failed: int = 0
    errored: int = 0

    def __add__(self, other: "TestCounts") -> "TestCounts":
        return TestCounts(
            passed=self.passed + other.passed,
            failed=self.failed + other.failed,
            errored=self.errored + other.errored,
        )


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    node_id: str = ""
    error: Exception | None = None
    duration: float | None = None
    output: str = ""
    is_fixture_error: bool = False


@dataclass
class SessionResult:
    """Result of a test session."""

    passed: int
    failed: int
    errors: int = 0
    duration: float | None = None
