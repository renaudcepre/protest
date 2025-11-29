"""Plugin base class for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.session import ProTestSession
    from protest.events.data import SessionResult, TestResult


class PluginBase:
    """Base class for ProTest plugins. Override only the hooks you need."""

    def setup(self, session: ProTestSession) -> None:
        pass

    def on_session_start(self) -> None:
        pass

    def on_session_end(self, result: SessionResult) -> None:
        pass

    def on_session_complete(self, result: SessionResult) -> None:
        pass

    def on_suite_start(self, name: str) -> None:
        pass

    def on_suite_end(self, name: str) -> None:
        pass

    def on_test_pass(self, result: TestResult) -> None:
        pass

    def on_test_fail(self, result: TestResult) -> None:
        pass
