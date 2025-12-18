from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from protest.core.session import ProTestSession
    from protest.entities import (
        FixtureInfo,
        HandlerInfo,
        SessionResult,
        SuiteResult,
        TestItem,
        TestResult,
        TestRetryInfo,
        TestStartInfo,
        TestTeardownInfo,
    )


class PluginBase:
    """Base class for ProTest plugins. Methods can be sync or async.

    Methods are ordered chronologically following the event timeline.
    """

    # ─────────────────────────────────────────────────────────────────────
    # Metadata (for CLI --help organization)
    # ─────────────────────────────────────────────────────────────────────

    name: str = ""  # e.g. "ctrf", "cache", "tag-filter"
    description: str = ""  # e.g. "CTRF JSON reporter for CI/CD"

    # ─────────────────────────────────────────────────────────────────────
    # CLI Integration
    # ─────────────────────────────────────────────────────────────────────

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        """Override to add CLI options for this plugin.

        Example:
            group = parser.add_argument_group("My Plugin")
            group.add_argument("--my-option", help="...")
        """

    @classmethod
    def from_cli(cls, args: Namespace) -> Self | None:
        """Create instance from CLI args. Return None to skip activation.

        Default: always instantiate with no args.
        Override to check CLI flags and potentially return None.
        """
        return cls()

    # ─────────────────────────────────────────────────────────────────────
    # Registration
    # ─────────────────────────────────────────────────────────────────────

    def setup(self, session: ProTestSession) -> None:
        """Called when plugin instance is wired to event bus."""

    # ─────────────────────────────────────────────────────────────────────
    # Collection
    # ─────────────────────────────────────────────────────────────────────

    def on_collection_finish(
        self, items: list[TestItem]
    ) -> list[TestItem] | Awaitable[list[TestItem]]:
        """Called after collection. Can filter/sort items."""
        return items

    # ─────────────────────────────────────────────────────────────────────
    # Session lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def on_session_start(self) -> None | Awaitable[None]:
        """Called before any test runs."""

    def on_session_end(self, result: SessionResult) -> None | Awaitable[None]:
        """Tests done, teardown complete. result.setup_duration and teardown_duration available."""

    def on_waiting_handlers(self, pending_count: int) -> None | Awaitable[None]:
        """Called when waiting for async handlers to complete."""

    def on_session_complete(self, result: SessionResult) -> None | Awaitable[None]:
        """After wait_pending(). All async handlers finished."""

    # ─────────────────────────────────────────────────────────────────────
    # Suite lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def on_suite_start(self, name: str) -> None | Awaitable[None]:
        """Called before a suite's tests run."""

    def on_suite_end(self, result: SuiteResult) -> None | Awaitable[None]:
        """Called after a suite's tests and teardown complete."""

    # ─────────────────────────────────────────────────────────────────────
    # Fixture lifecycle
    # ─────────────────────────────────────────────────────────────────────

    def on_fixture_setup_start(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called before a fixture setup begins."""

    def on_fixture_setup_done(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called after a fixture setup completes. info.duration = setup duration."""

    def on_fixture_teardown_start(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called before a fixture teardown begins."""

    def on_fixture_teardown_done(self, info: FixtureInfo) -> None | Awaitable[None]:
        """Called after a fixture teardown completes. info.duration = fixture lifetime."""

    # ─────────────────────────────────────────────────────────────────────
    # Test lifecycle
    # ─────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────
    # Test outcomes
    # ─────────────────────────────────────────────────────────────────────

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

    # ─────────────────────────────────────────────────────────────────────
    # Handler events (meta)
    # ─────────────────────────────────────────────────────────────────────

    def on_handler_start(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler starts executing."""

    def on_handler_end(self, info: HandlerInfo) -> None | Awaitable[None]:
        """Called when an event handler completes."""

    # ─────────────────────────────────────────────────────────────────────
    # Interruption
    # ─────────────────────────────────────────────────────────────────────

    def on_session_interrupted(self, force_teardown: bool) -> None | Awaitable[None]:
        """Called when Ctrl+C is pressed. force_teardown=True on 2nd Ctrl+C."""
