from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.entities import FixtureScope, SuitePath
    from protest.events.types import Event


@dataclass(frozen=True, slots=True)
class TestCounts:
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0

    def __add__(self, other: TestCounts) -> TestCounts:
        return TestCounts(
            passed=self.passed + other.passed,
            failed=self.failed + other.failed,
            errored=self.errored + other.errored,
            skipped=self.skipped + other.skipped,
            xfailed=self.xfailed + other.xfailed,
            xpassed=self.xpassed + other.xpassed,
        )


@dataclass(frozen=True, slots=True)
class TestResult:
    name: str
    node_id: str = ""
    suite_path: SuitePath | None = None
    error: Exception | None = None
    duration: float = 0
    output: str = ""
    is_fixture_error: bool = False
    skip_reason: str | None = None
    xfail_reason: str | None = None
    timeout: float | None = None
    attempt: int = 1
    max_attempts: int = 1
    previous_errors: tuple[Exception, ...] = ()


@dataclass(frozen=True, slots=True)
class SessionResult:
    passed: int
    failed: int
    errors: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration: float = 0
    setup_duration: float = 0
    teardown_duration: float = 0
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class SuiteResult:
    name: SuitePath
    duration: float = 0
    setup_duration: float = 0
    teardown_duration: float = 0


@dataclass(frozen=True, slots=True)
class SessionSetupInfo:
    """Emitted after session fixtures are resolved, before any suite starts."""

    duration: float


@dataclass(frozen=True, slots=True)
class SuiteSetupInfo:
    """Emitted after suite fixtures are resolved, before any test starts."""

    name: SuitePath
    duration: float


@dataclass(frozen=True, slots=True)
class RunResult:
    success: bool
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class TestStartInfo:
    name: str
    node_id: str


@dataclass(frozen=True, slots=True)
class HandlerInfo:
    name: str
    event: Event
    is_async: bool
    duration: float = 0
    error: Exception | None = None


@dataclass(frozen=True, slots=True)
class FixtureInfo:
    name: str
    scope: FixtureScope
    scope_path: SuitePath | None = None
    duration: float = 0
    autouse: bool = False


@dataclass(frozen=True, slots=True)
class TestRetryInfo:
    name: str
    node_id: str
    suite_path: SuitePath | None
    attempt: int
    max_attempts: int
    error: Exception
    delay: float


@dataclass(frozen=True, slots=True)
class TestTeardownInfo:
    name: str
    node_id: str
    outcome: Event
