"""Dataclasses for event payloads. Extensible without breaking signatures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.events.types import Event


@dataclass
class TestCounts:
    """Counts of test results."""

    passed: int = 0
    failed: int = 0
    errored: int = 0

    def __add__(self, other: TestCounts) -> TestCounts:
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
    duration: float = -1
    output: str = ""
    is_fixture_error: bool = False


@dataclass
class SessionResult:
    """Result of a test session."""

    passed: int
    failed: int
    errors: int = 0
    duration: float | None = None


@dataclass
class TestStartInfo:
    """Info emitted when a test begins execution."""

    name: str
    node_id: str


@dataclass
class HandlerInfo:
    """Info about a handler execution."""

    name: str
    event: Event
    is_async: bool
    duration: float | None = None
    error: Exception | None = None
