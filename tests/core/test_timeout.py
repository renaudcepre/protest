"""Tests for the timeout feature."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from protest import ProTestSession, ProTestSuite
from protest.core.runner import TestRunner
from protest.events.types import Event

if TYPE_CHECKING:
    from protest.entities import TestResult


class TestTimeoutBasic:
    """Basic timeout functionality tests."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession(default_reporter=False, default_cache=False)

    def test_async_timeout_exceeded(self, session: ProTestSession) -> None:
        """Async test exceeding timeout fails with TimeoutError."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_FAIL, lambda result: results.append(result))

        @session.test(timeout=0.1)
        async def test_slow() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        success = runner.run()

        assert not success
        assert len(results) == 1
        assert isinstance(results[0].error, TimeoutError)
        assert results[0].timeout == 0.1

    def test_async_within_timeout_passes(self, session: ProTestSession) -> None:
        """Async test completing within timeout passes."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, lambda result: results.append(result))

        @session.test(timeout=1.0)
        async def test_fast() -> None:
            await asyncio.sleep(0.01)

        runner = TestRunner(session)
        success = runner.run()

        assert success
        assert len(results) == 1
        assert results[0].timeout == 1.0

    def test_sync_timeout_exceeded(self, session: ProTestSession) -> None:
        """Sync test in executor exceeding timeout fails."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_FAIL, lambda result: results.append(result))

        @session.test(timeout=0.1)
        def test_slow_sync() -> None:
            time.sleep(1.0)

        runner = TestRunner(session)
        success = runner.run()

        assert not success
        assert len(results) == 1
        assert isinstance(results[0].error, TimeoutError)

    def test_no_timeout_runs_long(self, session: ProTestSession) -> None:
        """Test without timeout runs without limit."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, lambda result: results.append(result))

        @session.test()
        async def test_long() -> None:
            await asyncio.sleep(0.2)

        runner = TestRunner(session)
        success = runner.run()

        assert success
        assert len(results) == 1
        assert results[0].timeout is None


class TestTimeoutWithXfail:
    """Timeout interaction with xfail."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession(default_reporter=False, default_cache=False)

    def test_xfail_timeout_is_xfail(self, session: ProTestSession) -> None:
        """xfail=True + timeout → XFAIL."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_XFAIL, lambda result: results.append(result))

        @session.test(xfail="Known slow", timeout=0.1)
        async def test_expected_timeout() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        success = runner.run()

        assert success
        assert len(results) == 1
        assert results[0].xfail_reason == "Known slow"

    def test_xfail_within_timeout_is_xpass(self, session: ProTestSession) -> None:
        """xfail=True + passes within timeout → XPASS."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_XPASS, lambda result: results.append(result))

        @session.test(xfail="Expected to fail", timeout=1.0)
        async def test_unexpected_pass() -> None:
            await asyncio.sleep(0.01)

        runner = TestRunner(session)
        success = runner.run()

        assert not success
        assert len(results) == 1


class TestTimeoutWithSkip:
    """Timeout interaction with skip."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession(default_reporter=False, default_cache=False)

    def test_skip_ignores_timeout(self, session: ProTestSession) -> None:
        """Skipped test does not run, timeout never applies."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_SKIP, lambda result: results.append(result))

        @session.test(skip="Not ready", timeout=0.001)
        async def test_skipped() -> None:
            await asyncio.sleep(100)

        runner = TestRunner(session)
        success = runner.run()

        assert success
        assert len(results) == 1
        assert results[0].skip_reason == "Not ready"


class TestTimeoutValidation:
    """Timeout parameter validation."""

    def test_negative_timeout_raises(self) -> None:
        """Negative timeout raises ValueError at decoration time."""
        session = ProTestSession(default_reporter=False, default_cache=False)

        with pytest.raises(ValueError, match="timeout must be non-negative"):

            @session.test(timeout=-1.0)
            async def test_invalid() -> None:
                pass

    def test_zero_timeout_allowed(self) -> None:
        """Zero timeout is valid (immediate timeout)."""
        session = ProTestSession(default_reporter=False, default_cache=False)

        @session.test(timeout=0.0)
        async def test_zero() -> None:
            pass

        assert session.tests[0].timeout == 0.0


class TestTimeoutWithSuite:
    """Timeout with suite decorator."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession(default_reporter=False, default_cache=False)

    def test_suite_test_timeout(self, session: ProTestSession) -> None:
        """Suite test can have timeout."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_FAIL, lambda result: results.append(result))

        suite = ProTestSuite("API")
        session.add_suite(suite)

        @suite.test(timeout=0.1)
        async def test_api_slow() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        success = runner.run()

        assert not success
        assert len(results) == 1
        assert isinstance(results[0].error, TimeoutError)

    def test_suite_negative_timeout_raises(self) -> None:
        """Suite test with negative timeout raises ValueError."""
        suite = ProTestSuite("API")

        with pytest.raises(ValueError, match="timeout must be non-negative"):

            @suite.test(timeout=-5.0)
            async def test_invalid() -> None:
                pass


class TestTimeoutResult:
    """TestResult contains timeout information."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession(default_reporter=False, default_cache=False)

    def test_result_contains_timeout_value(self, session: ProTestSession) -> None:
        """TestResult.timeout contains configured value."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, lambda result: results.append(result))

        timeout_value = 5.0

        @session.test(timeout=timeout_value)
        async def test_with_timeout() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        assert results[0].timeout == timeout_value

    def test_result_error_is_timeout_error(self, session: ProTestSession) -> None:
        """TestResult.error is TimeoutError on timeout."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_FAIL, lambda result: results.append(result))

        @session.test(timeout=0.05)
        async def test_timeout() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        error = results[0].error
        assert isinstance(error, TimeoutError)
        assert "exceeded timeout of 0.05s" in str(error)
