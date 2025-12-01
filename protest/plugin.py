"""Plugin base class for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from protest.core.collector import TestItem
    from protest.core.session import ProTestSession
    from protest.events.data import (
        HandlerInfo,
        SessionResult,
        TestResult,
        TestStartInfo,
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

    def on_session_end(self, result: SessionResult) -> None | Awaitable[None]:
        """Tests done. Async handlers (Slack, etc.) start here."""

    def on_waiting_handlers(self, pending_count: int) -> None | Awaitable[None]:
        """Called when waiting for async handlers to complete."""

    def on_session_complete(self, result: SessionResult) -> None | Awaitable[None]:
        """After wait_pending(). All async handlers finished."""

    def on_suite_start(self, name: str) -> None | Awaitable[None]:
        """Called before a suite's tests run."""

    def on_suite_end(self, name: str) -> None | Awaitable[None]:
        """Called after a suite's tests and SUITE teardown."""

    def on_test_start(self, info: TestStartInfo) -> None | Awaitable[None]:
        """Called when a test begins (before fixtures)."""

    def on_test_setup_done(self, info: TestStartInfo) -> None | Awaitable[None]:
        """Called after fixtures resolved, before test execution."""

    def on_test_pass(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test passes."""

    def on_test_fail(self, result: TestResult) -> None | Awaitable[None]:
        """Called when a test fails."""

    def on_handler_start(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler starts executing."""

    def on_handler_end(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler completes."""
