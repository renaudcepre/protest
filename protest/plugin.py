"""Plugin base class for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.session import ProTestSession
    from protest.events.data import SessionResult, TestResult


class PluginBase:
    """Base class for ProTest plugins. Override only the hooks you need."""

    def setup(self, session: ProTestSession) -> None:
        """Called when plugin is registered via session.use()."""

    def on_session_start(self) -> None:
        """Called before any test runs."""

    def on_session_end(self, result: SessionResult) -> None:
        """Tests done. Async handlers (Slack, etc.) start here."""

    def on_session_complete(self, result: SessionResult) -> None:
        """After wait_pending(). All async handlers finished."""

    def on_suite_start(self, name: str) -> None:
        """Called before a suite's tests run."""

    def on_suite_end(self, name: str) -> None:
        """Called after a suite's tests and SUITE teardown."""

    def on_test_pass(self, result: TestResult) -> None:
        """Called when a test passes."""

    def on_test_fail(self, result: TestResult) -> None:
        """Called when a test fails."""
