"""Tests for the retries feature.

Note: This file intentionally does NOT use `from __future__ import annotations`
because some tests define fixtures locally within test methods. With PEP 563,
get_type_hints() cannot resolve local variables from enclosing scopes.
"""

import asyncio
import time
from typing import TYPE_CHECKING, Annotated

import pytest

from protest import ProTestSession, ProTestSuite, Retry
from protest.core.runner import TestRunner
from protest.di.decorators import fixture
from protest.di.markers import Use
from protest.entities import SuitePath
from protest.events.types import Event

if TYPE_CHECKING:
    from protest.entities import TestResult, TestRetryInfo


class TestRetriesBasic:
    """Basic retry functionality tests."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_retry_succeeds_after_failure(self, session: ProTestSession) -> None:
        """Test passes after initial failure with retry."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_PASS, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        call_count = 0

        @session.test(retry=2)
        def test_flaky() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Flaky failure")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert len(results) == 1
        assert results[0].attempt == 2
        assert results[0].max_attempts == 3
        assert len(results[0].previous_errors) == 1
        assert isinstance(results[0].previous_errors[0], ValueError)
        assert len(retry_events) == 1

    def test_retry_exhausted_fails(self, session: ProTestSession) -> None:
        """Test fails after exhausting all retries."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        call_count = 0

        @session.test(retry=2)
        def test_always_fails() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Failure {call_count}")

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert call_count == 3
        assert len(results) == 1
        assert results[0].attempt == 3
        assert results[0].max_attempts == 3
        assert len(results[0].previous_errors) == 2
        assert len(retry_events) == 2

    def test_no_retry_on_first_success(self, session: ProTestSession) -> None:
        """Test that passes on first try doesn't trigger retry."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_PASS, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(retry=3)
        def test_stable() -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert len(results) == 1
        assert results[0].attempt == 1
        assert results[0].max_attempts == 4
        assert len(results[0].previous_errors) == 0
        assert len(retry_events) == 0

    def test_retries_zero_no_retry(self, session: ProTestSession) -> None:
        """Test with retry=0 fails immediately without retry."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(retry=0)
        def test_no_retry() -> None:
            raise ValueError("Immediate failure")

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert len(results) == 1
        assert results[0].attempt == 1
        assert results[0].max_attempts == 1
        assert len(retry_events) == 0


class TestRetryOn:
    """Tests for retry_on exception filtering."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_retry_on_matching_exception(self, session: ProTestSession) -> None:
        """Retry triggers when exception matches retry_on."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(retry=Retry(times=2, on=ConnectionError))
        def test_connection() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection failed")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2
        assert results[0].attempt == 2

    def test_no_retry_on_non_matching_exception(self, session: ProTestSession) -> None:
        """No retry when exception doesn't match retry_on."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        call_count = 0

        @session.test(retry=Retry(times=3, on=ConnectionError))
        def test_wrong_exception() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a ConnectionError")

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert call_count == 1
        assert len(retry_events) == 0
        assert results[0].attempt == 1

    def test_retry_on_tuple_of_exceptions(self, session: ProTestSession) -> None:
        """Retry triggers for any exception in tuple."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(retry=Retry(times=3, on=(ConnectionError, TimeoutError)))
        def test_multiple_exceptions() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Connection failed")
            if call_count == 2:
                raise TimeoutError("Timed out")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 3
        assert results[0].attempt == 3

    def test_retry_on_subclass(self, session: ProTestSession) -> None:
        """Retry triggers for subclass of retry_on exception."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(retry=Retry(times=2, on=OSError))
        def test_subclass() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Subclass of OSError")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2

    def test_retry_on_none_retries_all(self, session: ProTestSession) -> None:
        """retry_on=None (default) retries on any exception."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(retry=2)
        def test_any_exception() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Any error")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2


class TestRetryDelay:
    """Tests for retry_delay timing."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_retry_delay_applied(self, session: ProTestSession) -> None:
        """Delay is applied between retries."""
        timestamps: list[float] = []

        @session.test(retry=Retry(times=2, delay=0.1))
        def test_with_delay() -> None:
            timestamps.append(time.perf_counter())
            if len(timestamps) < 3:
                raise ValueError("Retry me")

        runner = TestRunner(session)
        runner.run()

        assert len(timestamps) == 3
        delay_between_1_and_2 = timestamps[1] - timestamps[0]
        delay_between_2_and_3 = timestamps[2] - timestamps[1]
        expected_min_delay = 0.08
        assert delay_between_1_and_2 >= expected_min_delay
        assert delay_between_2_and_3 >= expected_min_delay

    def test_no_delay_when_zero(self, session: ProTestSession) -> None:
        """No delay when retry_delay=0."""
        timestamps: list[float] = []

        @session.test(retry=Retry(times=1, delay=0))
        def test_no_delay() -> None:
            timestamps.append(time.perf_counter())
            if len(timestamps) < 2:
                raise ValueError("Retry me")

        runner = TestRunner(session)
        runner.run()

        assert len(timestamps) == 2
        delay = timestamps[1] - timestamps[0]
        max_expected_delay = 0.05
        assert delay < max_expected_delay

    def test_retry_info_contains_delay(self, session: ProTestSession) -> None:
        """TestRetryInfo contains configured delay."""
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_RETRY, retry_events.append)

        delay_value = 0.5

        @session.test(retry=Retry(times=1, delay=delay_value))
        def test_delay_info() -> None:
            raise ValueError("Fail")

        runner = TestRunner(session)
        runner.run()

        assert len(retry_events) == 1
        assert retry_events[0].delay == delay_value


class TestRetriesWithSkip:
    """Retry interaction with skip."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_skip_ignores_retries(self, session: ProTestSession) -> None:
        """Skipped test does not run, retries never apply."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_SKIP, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        call_count = 0

        @session.test(skip="Not ready", retry=5)
        def test_skipped() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("Should never run")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 0
        assert len(results) == 1
        assert results[0].skip_reason == "Not ready"
        assert len(retry_events) == 0


class TestRetriesWithXfail:
    """Retry interaction with xfail."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_xfail_with_retries_exhausted_is_xfail(
        self, session: ProTestSession
    ) -> None:
        """xfail + retries exhausted → XFAIL."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_XFAIL, results.append)

        @session.test(xfail="Known flaky", retry=2)
        def test_expected_failure() -> None:
            raise ValueError("Always fails")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert len(results) == 1
        assert results[0].xfail_reason == "Known flaky"
        assert results[0].attempt == 3

    def test_xfail_with_retry_success_is_xpass(self, session: ProTestSession) -> None:
        """xfail + passes after retry → XPASS."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_XPASS, results.append)

        call_count = 0

        @session.test(xfail="Expected to fail", retry=2)
        def test_unexpected_pass() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Fail first time")

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert len(results) == 1
        assert results[0].xfail_reason == "Expected to fail"
        assert results[0].attempt == 2


class TestRetriesWithTimeout:
    """Retry interaction with timeout."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_timeout_triggers_retry(self, session: ProTestSession) -> None:
        """Timeout on first attempt triggers retry."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(timeout=0.1, retry=2)
        async def test_timeout_then_fast() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                await asyncio.sleep(1.0)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2
        assert results[0].attempt == 2

    def test_timeout_exhausts_retries(self, session: ProTestSession) -> None:
        """Timeout on all attempts exhausts retries."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(timeout=0.05, retry=1)
        async def test_always_slow() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert len(results) == 1
        assert isinstance(results[0].error, TimeoutError)
        assert results[0].attempt == 2
        assert len(retry_events) == 1

    def test_timeout_with_retry_on_filters(self, session: ProTestSession) -> None:
        """retry_on can filter TimeoutError."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(timeout=0.05, retry=Retry(times=2, on=ValueError))
        async def test_timeout_not_retried() -> None:
            await asyncio.sleep(1.0)

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert results[0].attempt == 1
        assert len(retry_events) == 0

    def test_timeout_retry_integration(self, session: ProTestSession) -> None:
        """Integration test: timeout triggers retry, tracks events and previous errors."""
        pass_results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_PASS, pass_results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        call_count = 0
        timestamps: list[float] = []

        @session.test(timeout=0.1, retry=Retry(times=2, delay=0.05))
        async def test_slow_then_fast() -> None:
            nonlocal call_count
            call_count += 1
            timestamps.append(time.perf_counter())
            if call_count in {1, 2}:
                await asyncio.sleep(1.0)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 3

        expected_retry_count = 2
        assert len(retry_events) == expected_retry_count
        assert retry_events[0].attempt == 1
        assert retry_events[1].attempt == 2
        assert isinstance(retry_events[0].error, TimeoutError)
        assert isinstance(retry_events[1].error, TimeoutError)
        assert retry_events[0].delay == 0.05

        assert len(pass_results) == 1
        assert pass_results[0].attempt == 3
        assert pass_results[0].max_attempts == 3
        expected_previous_errors_count = 2
        assert len(pass_results[0].previous_errors) == expected_previous_errors_count
        assert all(
            isinstance(err, TimeoutError) for err in pass_results[0].previous_errors
        )

        expected_min_delay = 0.04
        delay_1_to_2 = timestamps[1] - timestamps[0]
        delay_2_to_3 = timestamps[2] - timestamps[1]
        assert delay_1_to_2 >= expected_min_delay
        assert delay_2_to_3 >= expected_min_delay


class TestRetriesWithFixtureErrors:
    """Fixture errors should not trigger retries."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_fixture_error_no_retry(self, session: ProTestSession) -> None:
        """Fixture error does not trigger retry."""
        results: list[TestResult] = []
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_FAIL, results.append)
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @fixture()
        def broken_fixture() -> str:
            raise RuntimeError("Fixture broken")

        session.bind(broken_fixture)

        @session.test(retry=3)
        def test_with_broken_fixture(
            value: Annotated[str, Use(broken_fixture)],
        ) -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert len(results) == 1
        assert results[0].is_fixture_error
        assert results[0].attempt == 1
        assert len(retry_events) == 0


class TestRetriesValidation:
    """Retry parameter validation."""

    def test_negative_retries_raises(self) -> None:
        """Negative retry times raises ValueError at Retry creation time."""
        with pytest.raises(ValueError, match="retry times must be non-negative"):
            Retry(times=-1)

    def test_negative_retry_delay_raises(self) -> None:
        """Negative retry delay raises ValueError at Retry creation time."""
        with pytest.raises(ValueError, match="retry delay must be non-negative"):
            Retry(times=1, delay=-0.5)

    def test_zero_retries_allowed(self) -> None:
        """Zero retries is valid (default behavior)."""
        session = ProTestSession()

        @session.test(retry=0)
        def test_zero() -> None:
            pass

        assert session.tests[0].retry is not None
        assert session.tests[0].retry.times == 0

    def test_zero_retry_delay_allowed(self) -> None:
        """Zero retry_delay is valid (no delay)."""
        session = ProTestSession()

        @session.test(retry=Retry(times=1, delay=0.0))
        def test_zero_delay() -> None:
            pass

        assert session.tests[0].retry is not None
        assert session.tests[0].retry.delay == 0.0

    def test_retry_on_single_exception_normalized_to_tuple(self) -> None:
        """Single exception class is normalized to tuple."""
        retry_config = Retry(times=2, on=ConnectionError)
        assert retry_config.on == (ConnectionError,)

    def test_retry_on_tuple_stays_tuple(self) -> None:
        """Tuple of exceptions stays as tuple."""
        retry_config = Retry(times=2, on=(ConnectionError, TimeoutError))
        assert retry_config.on == (ConnectionError, TimeoutError)

    def test_retry_on_default_is_exception_tuple(self) -> None:
        """Default on value is (Exception,)."""
        retry_config = Retry(times=2)
        assert retry_config.on == (Exception,)


class TestRetriesWithSuite:
    """Retry with suite decorator."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_suite_test_retries(self, session: ProTestSession) -> None:
        """Suite test can have retries."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        suite = ProTestSuite("API")
        session.add_suite(suite)

        call_count = 0

        @suite.test(retry=2)
        def test_api_flaky() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("API flaky")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2
        assert results[0].attempt == 2

    def test_suite_negative_retries_raises(self) -> None:
        """Suite test with negative retry times raises ValueError at Retry creation."""
        with pytest.raises(ValueError, match="retry times must be non-negative"):
            Retry(times=-1)


class TestRetryEvent:
    """TEST_RETRY event tests."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_retry_event_emitted(self, session: ProTestSession) -> None:
        """TEST_RETRY event is emitted on each retry."""
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(retry=3)
        def test_multiple_retries() -> None:
            raise ValueError("Always fails")

        runner = TestRunner(session)
        runner.run()

        assert len(retry_events) == 3
        for idx, event in enumerate(retry_events, start=1):
            assert event.attempt == idx
            assert event.max_attempts == 4
            assert isinstance(event.error, ValueError)

    def test_retry_event_contains_correct_info(self, session: ProTestSession) -> None:
        """TestRetryInfo contains all expected fields."""
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_RETRY, retry_events.append)

        suite = ProTestSuite("MySuite")
        session.add_suite(suite)

        @suite.test(retry=Retry(times=1, delay=0.25))
        def test_info() -> None:
            raise RuntimeError("Test error")

        runner = TestRunner(session)
        runner.run()

        assert len(retry_events) == 1
        info = retry_events[0]
        assert info.name == "test_info"
        assert "MySuite" in info.node_id
        assert info.suite_path == SuitePath("MySuite")
        assert info.attempt == 1
        assert info.max_attempts == 2
        assert isinstance(info.error, RuntimeError)
        assert info.delay == 0.25

    def test_no_retry_event_on_success(self, session: ProTestSession) -> None:
        """No TEST_RETRY event when test passes first time."""
        retry_events: list[TestRetryInfo] = []
        session.events.on(Event.TEST_RETRY, retry_events.append)

        @session.test(retry=3)
        def test_passes() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(retry_events) == 0


class TestRetriesAsync:
    """Retry with async tests."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_async_retry_succeeds(self, session: ProTestSession) -> None:
        """Async test retries work correctly."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_PASS, results.append)

        call_count = 0

        @session.test(retry=2)
        async def test_async_flaky() -> None:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            if call_count < 2:
                raise ValueError("Async flaky")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert call_count == 2
        assert results[0].attempt == 2
