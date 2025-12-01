"""Default console reporter implementation."""

from protest.events.data import SessionResult, TestResult
from protest.plugin import PluginBase


def _format_test_name(result: TestResult) -> str:
    """Format test name with case_ids if present."""
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        return f"{result.name}{suffix}"
    return result.name


class ConsoleReporter(PluginBase):
    """Simple console reporter plugin."""

    def on_session_start(self) -> None:
        print(" --- Starting session ---")
        print()

    def on_session_complete(self, result: SessionResult) -> None:
        total = result.passed + result.failed + result.errors
        parts = [f"{result.passed}/{total} passed"]
        if result.failed:
            parts.append(f"{result.failed} failed")
        if result.errors:
            parts.append(f"{result.errors} errors")
        print(f"\nResults: {', '.join(parts)}")

    def on_suite_start(self, name: str) -> None:
        print(f"[Suite: {name}]")

    def on_test_pass(self, result: TestResult) -> None:
        print(f"  ✓ {_format_test_name(result)}")

    def on_test_fail(self, result: TestResult) -> None:
        display_name = _format_test_name(result)
        if result.is_fixture_error:
            print(f"  ⚠ {display_name}: [SETUP ERROR] {result.error}")
        else:
            print(f"  ✗ {display_name}: {result.error}")
        if result.output:
            print("    --- Captured output ---")
            for line in result.output.rstrip().splitlines():
                print(f"    {line}")
            print("    --------------------------")
