from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from protest.core.session import ProTestSession
    from protest.entities import (
        FixtureInfo,
        HandlerInfo,
        SessionResult,
        TestItem,
        TestResult,
        TestRetryInfo,
        TestStartInfo,
        TestTeardownInfo,
    )


class PluginBase:
    """Base class for ProTest plugins. Methods can be sync or async."""

    def setup(self, session: ProTestSession) -> None:
        """Called when plugin is registered via session.use()."""

    def on_collection_finish(
        self, items: list[TestItem]
    ) -> list[TestItem] | Awaitable[list[TestItem]]:
        """Called after collection. Can filter/sort items."""
        return items

    def on_session_start(self) -> None | Awaitable[None]:
        """Called before any test runs."""

    def on_session_setup_start(self) -> None | Awaitable[None]:
        """Called before session fixtures are resolved."""

    def on_session_setup_done(self, duration: float) -> None | Awaitable[None]:
        """Called after session fixtures are resolved."""

    def on_session_teardown_start(self) -> None | Awaitable[None]:
        """Called before session fixture teardown begins."""

    def on_session_teardown_done(self, duration: float) -> None | Awaitable[None]:
        """Called after session fixture teardown completes."""

    def on_session_end(self, result: SessionResult) -> None | Awaitable[None]:
        """Tests done. Async handlers (Slack, etc.) start here."""

    def on_waiting_handlers(self, pending_count: int) -> None | Awaitable[None]:
        """Called when waiting for async handlers to complete."""

    def on_session_complete(self, result: SessionResult) -> None | Awaitable[None]:
        """After wait_pending(). All async handlers finished."""

    def on_suite_start(self, name: str) -> None | Awaitable[None]:
        """Called before a suite's tests run."""

    def on_suite_end(self, name: str) -> None | Awaitable[None]:
        """Called after a suite's tests complete."""

    def on_suite_teardown_start(self, name: str) -> None | Awaitable[None]:
        """Called before suite fixture teardown begins."""

    def on_suite_teardown_done(self, name: str) -> None | Awaitable[None]:
        """Called after suite fixture teardown completes."""

    def on_test_start(self, info: TestStartInfo) -> None | Awaitable[None]:
        """Called when a test begins (waiting for execution slot)."""

    def on_test_acquired(self, info: TestStartInfo) -> None | Awaitable[None]:
        """Called when test acquires execution slot (entering setup phase)."""

    def on_test_setup_done(self, info: TestStartInfo) -> None | Awaitable[None]:
        """Called after fixtures resolved, before test execution."""

    def on_test_teardown_start(self, info: TestTeardownInfo) -> None | Awaitable[None]:
        """Called after test body, before fixture teardown."""

    def on_test_retry(self, info: TestRetryInfo) -> None | Awaitable[None]:
        """Called when a test fails and will be retried."""

    def on_test_pass(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test passes."""

    def on_test_fail(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test fails."""

    def on_test_skip(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test is skipped."""

    def on_test_xfail(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test fails as expected (xfail)."""

    def on_test_xpass(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test marked xfail unexpectedly passes."""

    def on_handler_start(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler starts executing."""

    def on_handler_end(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler completes."""

    def on_fixture_setup(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called when a fixture starts setup."""

    def on_fixture_teardown(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called when a fixture is torn down."""

    def on_session_interrupted(self, force_teardown: bool) -> None | Awaitable[None]:
        """Called when Ctrl+C is pressed. force_teardown=True on 2nd Ctrl+C."""
