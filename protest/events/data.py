"""Dataclasses for event payloads. Extensible without breaking signatures."""

from dataclasses import dataclass


@dataclass
class TestResult:
    """Result of a single test execution."""

    name: str
    error: Exception | None = None
    duration: float | None = None
    output: str = ""


@dataclass
class SessionResult:
    """Result of a test session."""

    passed: int
    failed: int
    duration: float | None = None
