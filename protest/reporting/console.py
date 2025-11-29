"""Default console reporter implementation."""

from protest.events.bus import EventBus
from protest.events.data import SessionResult, TestResult
from protest.events.types import Event


class ConsoleReporter:
    """Simple console reporter. Register handlers on an EventBus."""

    def register(self, events: EventBus) -> None:
        """Register all handlers on the event bus."""
        events.on(Event.SESSION_START, self.on_session_start)
        events.on(Event.SESSION_COMPLETE, self.on_session_complete)
        events.on(Event.SUITE_START, self.on_suite_start)
        events.on(Event.SUITE_END, self.on_suite_end)
        events.on(Event.TEST_PASS, self.on_test_pass)
        events.on(Event.TEST_FAIL, self.on_test_fail)

    def on_session_start(self) -> None:
        print(" --- Starting session ---")
        print()

    def on_session_complete(self, result: SessionResult) -> None:
        total = result.passed + result.failed
        print(f"\nResults: {result.passed}/{total} passed")

    def on_suite_start(self, suite_name: str) -> None:
        print(f"[Suite: {suite_name}]")

    def on_suite_end(self, suite_name: str) -> None:
        pass

    def on_test_pass(self, result: TestResult) -> None:
        print(f"  ✓ {result.name}")

    def on_test_fail(self, result: TestResult) -> None:
        print(f"  ✗ {result.name}: {result.error}")
