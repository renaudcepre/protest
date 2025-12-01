"""Default console reporter implementation."""

from protest.events.data import SessionResult, TestResult
from protest.plugin import PluginBase
from protest.reporting.colors import Fg, Style, colorize


def _format_test_name(result: TestResult) -> str:
    """Format test name with case_ids if present."""
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        return f"{result.name}{suffix}"
    return result.name


class ConsoleReporter(PluginBase):
    """Console reporter with colors. No spinner - use RichReporter for that."""

    def on_session_start(self) -> None:
        print(colorize("🚀 Starting session", Fg.CYAN, Style.BOLD))
        print()

    def on_suite_start(self, name: str) -> None:
        print(colorize(f"📦 {name}", Fg.CYAN))

    def on_test_pass(self, result: TestResult) -> None:
        name = _format_test_name(result)
        duration = colorize(f"({result.duration:.3f}s)", Fg.GRAY)
        print(f"  {colorize('✓', Fg.GREEN)} {name} {duration}")

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result)
        if result.is_fixture_error:
            tag = colorize("[FIXTURE]", Fg.YELLOW, Style.BOLD)
            symbol = colorize("⚠", Fg.YELLOW)
            print(f"  {symbol} {name}: {tag} {result.error}")
        else:
            symbol = colorize("✗", Fg.RED)
            print(f"  {symbol} {name}: {result.error}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                print(colorize(f"    │ {line}", Fg.GRAY, Style.DIM))

    def on_waiting_handlers(self, pending_count: int) -> None:
        print(
            colorize(f"\n⏳ Waiting for {pending_count} async handler(s)...", Fg.GRAY)
        )

    def on_session_complete(self, result: SessionResult) -> None:
        total = result.passed + result.failed + result.errors

        if result.failed == 0 and result.errors == 0:
            status = colorize("✓ ALL PASSED", Fg.GREEN, Style.BOLD)
        else:
            status = colorize("✗ FAILURES", Fg.RED, Style.BOLD)

        parts = [
            f"{result.passed}/{total} passed",
        ]
        if result.failed:
            parts.append(colorize(f"{result.failed} failed", Fg.RED))
        if result.errors:
            parts.append(colorize(f"{result.errors} errors", Fg.YELLOW))

        duration = f"{result.duration:.2f}s"
        print(f"\n{status} │ {' │ '.join(parts)} │ {duration}")
