from dataclasses import FrozenInstanceError

import pytest

from protest.entities import (
    FixtureInfo,
    FixtureScope,
    HandlerInfo,
    SessionResult,
    TestCounts,
    TestResult,
    TestStartInfo,
    format_fixture_scope,
)
from protest.events.types import Event


class TestTestCounts:
    """Tests for TestCounts dataclass - aggregating test statistics."""

    def test_default_values(self) -> None:
        """TestCounts defaults to all zeros."""
        counts = TestCounts()

        assert counts.passed == 0
        assert counts.failed == 0
        assert counts.errored == 0

    def test_add_counts(self) -> None:
        """TestCounts can be added together."""
        counts_a = TestCounts(passed=1, failed=2, errored=3)
        counts_b = TestCounts(passed=4, failed=5, errored=6)

        result = counts_a + counts_b

        assert result.passed == 5
        assert result.failed == 7
        assert result.errored == 9

    def test_add_to_zero_counts(self) -> None:
        """Adding to zero counts works correctly."""
        zero = TestCounts()
        counts = TestCounts(passed=1, failed=2, errored=3)

        result = zero + counts

        assert result.passed == 1
        assert result.failed == 2
        assert result.errored == 3

    def test_add_returns_new_instance(self) -> None:
        """Adding creates a new instance, doesn't mutate."""
        counts_a = TestCounts(passed=1)
        counts_b = TestCounts(passed=2)

        result = counts_a + counts_b

        assert counts_a.passed == 1
        assert counts_b.passed == 2
        assert result.passed == 3


class TestTestResult:
    """Tests for TestResult dataclass."""

    def test_minimal_result(self) -> None:
        """TestResult with only name."""
        result = TestResult(name="my_test")

        assert result.name == "my_test"
        assert result.node_id == ""
        assert result.error is None
        assert result.duration == 0
        assert result.output == ""
        assert result.is_fixture_error is False

    def test_full_result(self) -> None:
        """TestResult with all fields."""
        error = ValueError("boom")
        result = TestResult(
            name="my_test",
            node_id="mod::Suite::my_test",
            error=error,
            duration=1.5,
            output="some output",
            is_fixture_error=True,
        )

        assert result.name == "my_test"
        assert result.node_id == "mod::Suite::my_test"
        assert result.error is error
        assert result.duration == 1.5
        assert result.output == "some output"
        assert result.is_fixture_error is True


class TestSessionResult:
    """Tests for SessionResult dataclass."""

    def test_minimal_session_result(self) -> None:
        """SessionResult with required fields."""
        result = SessionResult(passed=5, failed=2)

        assert result.passed == 5
        assert result.failed == 2
        assert result.errors == 0
        assert result.duration == 0

    def test_full_session_result(self) -> None:
        """SessionResult with all fields."""
        result = SessionResult(passed=5, failed=2, errors=1, duration=10.5)

        assert result.passed == 5
        assert result.failed == 2
        assert result.errors == 1
        assert result.duration == 10.5


class TestFrozenDataclasses:
    """Event dataclasses are frozen to prevent race conditions in async handlers."""

    def test_test_counts_is_immutable(self) -> None:
        counts = TestCounts(passed=1)

        with pytest.raises(FrozenInstanceError):
            counts.passed = 2  # type: ignore[misc]

    def test_test_result_is_immutable(self) -> None:
        result = TestResult(name="test")

        with pytest.raises(FrozenInstanceError):
            result.output = "mutated"  # type: ignore[misc]

    def test_session_result_is_immutable(self) -> None:
        result = SessionResult(passed=1, failed=0)

        with pytest.raises(FrozenInstanceError):
            result.passed = 999  # type: ignore[misc]

    def test_test_start_info_is_immutable(self) -> None:
        info = TestStartInfo(name="test", node_id="mod::test")

        with pytest.raises(FrozenInstanceError):
            info.name = "mutated"  # type: ignore[misc]

    def test_handler_info_is_immutable(self) -> None:
        info = HandlerInfo(name="handler", event=Event.TEST_PASS, is_async=True)

        with pytest.raises(FrozenInstanceError):
            info.duration = 999.0  # type: ignore[misc]

    def test_fixture_info_is_immutable(self) -> None:
        info = FixtureInfo(name="db", scope=FixtureScope.SESSION)

        with pytest.raises(FrozenInstanceError):
            info.scope = FixtureScope.TEST  # type: ignore[misc]


class TestFormatFixtureScope:
    """Tests for format_fixture_scope helper function."""

    def test_session_scope(self) -> None:
        result = format_fixture_scope(FixtureScope.SESSION)

        assert result == "session"

    def test_session_scope_ignores_path(self) -> None:
        result = format_fixture_scope(FixtureScope.SESSION, "ignored")

        assert result == "session"

    def test_suite_scope_with_path(self) -> None:
        result = format_fixture_scope(FixtureScope.SUITE, "API::Users")

        assert result == "suite 'API::Users'"

    def test_suite_scope_with_simple_path(self) -> None:
        result = format_fixture_scope(FixtureScope.SUITE, "API")

        assert result == "suite 'API'"

    def test_test_scope(self) -> None:
        result = format_fixture_scope(FixtureScope.TEST)

        assert result == "test"

    def test_test_scope_ignores_path(self) -> None:
        result = format_fixture_scope(FixtureScope.TEST, "ignored")

        assert result == "test"
