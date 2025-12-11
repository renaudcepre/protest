import traceback
from pathlib import Path

from rich.console import Console  # type: ignore[import-not-found]

from protest.entities import (
    HandlerInfo,
    SessionResult,
    TestItem,
    TestResult,
    TestRetryInfo,
)
from protest.plugin import PluginBase


def _format_test_name(result: TestResult) -> str:
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        escaped_suffix = suffix.replace("[", "\\[")
        return f"{result.name}{escaped_suffix}"
    return result.name


MIN_DURATION_THRESHOLD = 0.001


def _format_duration(seconds: float) -> str:
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


class RichReporter(PluginBase):
    """Rich console reporter with colors."""

    def __init__(self) -> None:
        self.console = Console(highlight=False)
        self._printed_suites: set[str | None] = set()
        self._total_tests = 0
        self._failed_results: list[TestResult] = []
        self._error_results: list[TestResult] = []

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        self._total_tests = len(items)
        return items

    def on_session_start(self) -> None:
        pass

    def on_session_setup_start(self) -> None:
        pass

    def on_session_setup_done(self, duration: float) -> None:
        pass

    def on_session_teardown_start(self) -> None:
        self.console.print("[yellow]  session teardown...[/]")

    def on_session_teardown_done(self, duration: float) -> None:
        self.console.print(
            f"[dim]  session teardown done ({_format_duration(duration)})[/]"
        )

    def on_suite_start(self, name: str) -> None:
        pass

    def _print_suite_header_if_needed(self, suite_path: str | None) -> None:
        if suite_path not in self._printed_suites:
            self._printed_suites.add(suite_path)
            if suite_path:
                self.console.print(f"[cyan]       ◈ {suite_path}[/]")

    def on_test_retry(self, info: TestRetryInfo) -> None:
        self._print_suite_header_if_needed(info.suite_path)
        delay_msg = f", retrying in {info.delay}s" if info.delay > 0 else ""
        error_name = type(info.error).__name__
        self.console.print(
            f"   [yellow]↻[/]   {info.name}: attempt {info.attempt}/{info.max_attempts} "
            f"failed ({error_name}: {info.error}){delay_msg}"
        )

    def on_test_pass(self, result: TestResult) -> None:
        self._print_suite_header_if_needed(result.suite_path)
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        retry_suffix = ""
        if result.max_attempts > 1:
            retry_suffix = (
                f" [dim]\\[attempt {result.attempt}/{result.max_attempts}][/]"
            )
        self.console.print(
            f"   [green]✓[/]   {name} [dim]({duration})[/]{retry_suffix}"
        )

    def on_test_fail(self, result: TestResult) -> None:
        self._print_suite_header_if_needed(result.suite_path)
        name = _format_test_name(result)
        retry_suffix = ""
        if result.max_attempts > 1:
            retry_suffix = f" [{result.max_attempts} attempts]"

        if result.is_fixture_error:
            self._error_results.append(result)
        else:
            self._failed_results.append(result)

        if result.is_fixture_error:
            self.console.print(
                f"   [yellow]⚠[/]   {name}: [bold yellow]\\[FIXTURE][/] {result.error}"
            )
        elif isinstance(result.error, TimeoutError) and result.timeout is not None:
            self.console.print(
                f"   [red]⏱[/]   {name}: [bold red]TIMEOUT[/] (exceeded {result.timeout}s){retry_suffix}"
            )
        else:
            self.console.print(f"   [red]✗[/]   {name}: {result.error}{retry_suffix}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                self.console.print(f"[dim]       │ {line}[/]")

    def on_test_skip(self, result: TestResult) -> None:
        self._print_suite_header_if_needed(result.suite_path)
        name = _format_test_name(result)
        self.console.print(f"   [yellow]○[/]   {name} [dim]({result.skip_reason})[/]")

    def on_test_xfail(self, result: TestResult) -> None:
        self._print_suite_header_if_needed(result.suite_path)
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        self.console.print(
            f"   [green]✗[/]   {name} [dim]({result.xfail_reason}) ({duration})[/]"
        )

    def on_test_xpass(self, result: TestResult) -> None:
        self._print_suite_header_if_needed(result.suite_path)
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        self.console.print(f"   [red]⚡[/]   {name} [red]XPASS[/] [dim]({duration})[/]")

    def on_session_interrupted(self, force_teardown: bool) -> None:
        if force_teardown:
            self.console.print(
                "\n[bold yellow]⚠ Forcing teardown... (press Ctrl+C again to kill)[/]"
            )
        else:
            self.console.print(
                "\n[bold yellow]⚠ Stopping... (press Ctrl+C again to force teardown)[/]"
            )

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

    def _format_traceback(self, error: Exception) -> str:
        lines = traceback.format_exception(type(error), error, error.__traceback__)
        return "".join(lines)

    def _print_failure_summary(self) -> None:
        if self._failed_results:
            self.console.print("\n[bold red]═══ FAILURES ═══[/]")
            for result in self._failed_results:
                self._print_failure_detail(result, is_error=False)

        if self._error_results:
            self.console.print("\n[bold yellow]═══ ERRORS ═══[/]")
            for result in self._error_results:
                self._print_failure_detail(result, is_error=True)

    def _print_failure_detail(self, result: TestResult, *, is_error: bool) -> None:
        name = _format_test_name(result)
        full_name = f"{result.suite_path}::{name}" if result.suite_path else name
        color = "yellow" if is_error else "red"
        self.console.print(f"\n[bold {color}]___ {full_name} ___[/]")

        if result.error:
            tb_text = self._format_traceback(result.error)
            for line in tb_text.rstrip().splitlines():
                escaped_line = line.replace("[", "\\[")
                self.console.print(f"[dim]{escaped_line}[/]")

        if result.output:
            self.console.print("[dim]--- Captured output ---[/]")
            for line in result.output.rstrip().splitlines():
                escaped_line = line.replace("[", "\\[")
                self.console.print(f"[dim]{escaped_line}[/]")

    def on_session_complete(self, result: SessionResult) -> None:
        if self._failed_results or self._error_results:
            self._print_failure_summary()

        total = (
            result.passed
            + result.failed
            + result.errors
            + result.skipped
            + result.xfailed
            + result.xpassed
        )
        if result.interrupted:
            status = "[bold yellow]⚠ INTERRUPTED[/]"
        elif result.failed == 0 and result.errors == 0 and result.xpassed == 0:
            status = "[bold green]✓ ALL PASSED[/]"
        else:
            status = "[bold red]✗ FAILURES[/]"

        parts = [f"{result.passed}/{total} passed"]
        if result.skipped:
            parts.append(f"[yellow]{result.skipped} skipped[/]")
        if result.xfailed:
            parts.append(f"[dim]{result.xfailed} xfailed[/]")
        if result.xpassed:
            parts.append(f"[red]{result.xpassed} xpassed[/]")
        if result.failed:
            parts.append(f"[red]{result.failed} failed[/]")
        if result.errors:
            parts.append(f"[yellow]{result.errors} errors[/]")

        duration = f"{result.duration:.2f}s"
        self.console.print(f"\n{status} │ {' │ '.join(parts)} │ {duration}")

        log_file = Path(".protest/last_run.log")
        stdout_file = Path(".protest/last_run_stdout")
        if log_file.exists() or stdout_file.exists():
            self.console.print(
                "[dim]Full output: .protest/last_run.log, .protest/last_run_stdout[/]"
            )
