"""Default console reporter implementation."""

from protest.events.data import SessionResult, TestResult
from protest.plugin import PluginBase


class ConsoleReporter(PluginBase):
    """Simple console reporter plugin."""

    def on_session_start(self) -> None:
        print(" --- Starting session ---")
        print()

    def on_session_complete(self, result: SessionResult) -> None:
        total = result.passed + result.failed
        print(f"\nResults: {result.passed}/{total} passed")

    def on_suite_start(self, name: str) -> None:
        print(f"[Suite: {name}]")

    def on_test_pass(self, result: TestResult) -> None:
        print(f"  ✓ {result.name}")

    def on_test_fail(self, result: TestResult) -> None:
        print(f"  ✗ {result.name}: {result.error}")
        if result.output:
            print("    --- Captured output ---")
            for line in result.output.rstrip().splitlines():
                print(f"    {line}")
            print("    --------------------------")
