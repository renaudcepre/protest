"""Rich console reporter with colors and emojis. Requires 'rich' package."""

from rich.console import Console  # type: ignore[import-not-found]

from protest.events.data import HandlerInfo, SessionResult, TestResult
from protest.plugin import PluginBase


def _format_test_name(result: TestResult) -> str:
    """Format test name with case_ids if present."""
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        return f"{result.name}{suffix}"
    return result.name


MIN_DURATION_THRESHOLD = 0.001


def _format_duration(seconds: float) -> str:
    """Format duration: ms for fast, s for slow."""
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


class RichReporter(PluginBase):
    """Rich console reporter with colors and emojis."""

    def __init__(self) -> None:
        self.console = Console(highlight=False)

    def on_session_start(self) -> None:
        self.console.print("[bold cyan]🚀 Starting session[/]")
        self.console.print()

    def on_suite_start(self, name: str) -> None:
        self.console.print(f"[cyan]📦 {name}[/]")

    def on_test_pass(self, result: TestResult) -> None:
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        self.console.print(f"  [green]✓[/] {name} [dim]({duration})[/]")

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result)
        if result.is_fixture_error:
            self.console.print(
                f"  [yellow]⚠[/] {name}: [bold yellow]\\[FIXTURE][/] {result.error}"
            )
        else:
            self.console.print(f"  [red]✗[/] {name}: {result.error}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                self.console.print(f"[dim]    │ {line}[/]")

    def on_waiting_handlers(self, pending_count: int) -> None:
        self.console.print(f"\n[cyan]⏳ Async handlers ({pending_count})[/]")

    def on_handler_end(self, info: HandlerInfo) -> None:
        if not info.is_async:
            return
        if info.error:
            self.console.print(f"  [red]✗[/] {info.name}: {info.error}")
        else:
            duration = _format_duration(info.duration)
            self.console.print(f"  [green]✓[/] {info.name} [dim]({duration})[/]")

    def on_session_complete(self, result: SessionResult) -> None:
        total = result.passed + result.failed + result.errors

        if result.failed == 0 and result.errors == 0:
            status = "[bold green]✓ ALL PASSED[/]"
        else:
            status = "[bold red]✗ FAILURES[/]"

        parts = [f"{result.passed}/{total} passed"]
        if result.failed:
            parts.append(f"[red]{result.failed} failed[/]")
        if result.errors:
            parts.append(f"[yellow]{result.errors} errors[/]")

        duration = f"{result.duration:.2f}s"
        self.console.print(f"\n{status} │ {' │ '.join(parts)} │ {duration}")
