"""Default console reporter implementation."""


class ConsoleReporter:
    """Simple console reporter with text output."""

    def on_session_start(self) -> None:
        print(" --- Starting session ---")
        print()

    def on_session_end(self, passed: int, failed: int) -> None:
        total = passed + failed
        print(f"\nResults: {passed}/{total} passed")

    def on_suite_start(self, suite_name: str) -> None:
        print(f"[Suite: {suite_name}]")

    def on_suite_end(self, suite_name: str) -> None:
        pass

    def on_test_pass(self, test_name: str) -> None:
        print(f"  ✓ {test_name}")

    def on_test_fail(self, test_name: str, error: Exception) -> None:
        print(f"  ✗ {test_name}: {error}")
