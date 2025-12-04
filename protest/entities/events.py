from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.events.types import Event


@dataclass
class TestCounts:
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0

    def __add__(self, other: TestCounts) -> TestCounts:
        return TestCounts(
            passed=self.passed + other.passed,
            failed=self.failed + other.failed,
            errored=self.errored + other.errored,
            skipped=self.skipped + other.skipped,
        )


@dataclass
class TestResult:
    name: str
    node_id: str = ""
    error: Exception | None = None
    duration: float = 0
    output: str = ""
    is_fixture_error: bool = False
    skip_reason: str | None = None


@dataclass
class SessionResult:
    passed: int
    failed: int
    errors: int = 0
    skipped: int = 0
    duration: float = 0


@dataclass
class TestStartInfo:
    name: str
    node_id: str


@dataclass
class HandlerInfo:
    name: str
    event: Event
    is_async: bool
    duration: float = 0
    error: Exception | None = None


@dataclass
class FixtureInfo:
    name: str
    scope: str
    duration: float = 0
