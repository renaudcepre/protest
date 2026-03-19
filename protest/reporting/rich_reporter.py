import traceback
from argparse import ArgumentParser
from pathlib import Path

from rich.console import Console  # type: ignore[import-not-found]
from typing_extensions import Self

from protest.entities import (
    FixtureInfo,
    HandlerInfo,
    SessionResult,
    SessionSetupInfo,
    SuitePath,
    SuiteResult,
    SuiteSetupInfo,
    SuiteStartInfo,
    TestItem,
    TestResult,
    TestRetryInfo,
    TestStartInfo,
    TestTeardownInfo,
)
from protest.plugin import PluginBase, PluginContext
from protest.reporting.verbosity import Verbosity


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

    name = "rich-reporter"
    description = "Rich console reporter with colors"

    def __init__(self, verbosity: int = 0) -> None:
        self.console = Console(highlight=False)
        self._verbosity = verbosity
        self._failed_results: list[TestResult] = []
        self._error_results: list[TestResult] = []

        self._passed = 0
        self._failed = 0
        self._errors = 0
        self._skipped = 0
        self._xfailed = 0
        self._xpassed = 0

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        group = parser.add_argument_group(f"{cls.name} - {cls.description}")
        group.add_argument(
            "--no-color",
            dest="no_color",
            action="store_true",
            help="Disable colors (plain ASCII output)",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self | None:
        if ctx.get("no_color", False):
            return None
        return cls(verbosity=ctx.get("verbosity", 0))

    def _print(self, message: str) -> None:
        self.console.print(message)

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        return items

    def on_session_start(self) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE:
            self._print("[dim]  session setup...[/]")

    def on_session_setup_done(self, info: SessionSetupInfo) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE:
            self._print(
                f"[dim]  session setup done ({_format_duration(info.duration)})[/]"
            )

    def on_suite_setup_done(self, info: SuiteSetupInfo) -> None:
        if self._verbosity >= Verbosity.NORMAL:
            self._print(f"[cyan]       ◈ {info.name}[/]")

    def on_session_teardown_start(self) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE:
            self._print("[dim]  session teardown...[/]")

    def on_suite_teardown_start(self, path: SuitePath) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE:
            self._print(f"[dim]  suite '{path}' teardown...[/]")

    def on_suite_end(self, result: SuiteResult) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE and result.teardown_duration > 0:
            self._print(
                f"[dim]  {result.name} teardown done ({_format_duration(result.teardown_duration)})[/]"
            )

    def on_session_end(self, result: SessionResult) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE and result.teardown_duration > 0:
            self._print(
                f"[dim]  session teardown done ({_format_duration(result.teardown_duration)})[/]"
            )

    def on_suite_start(self, info: SuiteStartInfo) -> None:
        if self._verbosity >= Verbosity.LIFECYCLE:
            self._print(f"[dim]  suite '{info.name}' setup...[/]")

    def on_fixture_setup_start(self, info: FixtureInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            scope_str = f"[dim]({info.scope.value})[/]"
            self._print(f"[dim]    ↳ fixture '{info.name}' setup... {scope_str}[/]")

    def on_fixture_setup_done(self, info: FixtureInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            self._print(
                f"[dim]    ↳ fixture '{info.name}' ready ({_format_duration(info.duration)})[/]"
            )

    def on_fixture_teardown_start(self, info: FixtureInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            self._print(f"[dim]    ↳ fixture '{info.name}' teardown...[/]")

    def on_fixture_teardown_done(self, info: FixtureInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            self._print(
                f"[dim]    ↳ fixture '{info.name}' cleaned ({_format_duration(info.duration)})[/]"
            )

    def on_test_setup_done(self, info: TestStartInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            self._print(f"[dim]       → {info.name} setup done[/]")

    def on_test_teardown_start(self, info: TestTeardownInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            self._print(f"[dim]       ← {info.name} teardown...[/]")

    def on_test_retry(self, info: TestRetryInfo) -> None:
        delay_msg = f", retrying in {info.delay}s" if info.delay > 0 else ""
        error_name = type(info.error).__name__
        self._print(
            f"   [yellow]↻[/]   {info.name}: attempt {info.attempt}/{info.max_attempts} "
            f"failed ({error_name}: {info.error}){delay_msg}"
        )

    def on_test_pass(self, result: TestResult) -> None:
        self._passed += 1
        if self._verbosity >= Verbosity.NORMAL:
            name = _format_test_name(result)
            duration = _format_duration(result.duration)
            retry_suffix = ""
            if result.max_attempts > 1:
                retry_suffix = (
                    f" [dim]\\[attempt {result.attempt}/{result.max_attempts}][/]"
                )
            self._print(f"   [green]✓[/]   {name} [dim]({duration})[/]{retry_suffix}")

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result)
        retry_suffix = ""
        if result.max_attempts > 1:
            retry_suffix = f" [{result.max_attempts} attempts]"

        if result.is_fixture_error:
            self._error_results.append(result)
            self._errors += 1
        else:
            self._failed_results.append(result)
            self._failed += 1

        # Failures ALWAYS show regardless of verbosity
        if result.is_fixture_error:
            self._print(
                f"   [yellow]⚠[/]   {name}: [bold yellow]\\[FIXTURE][/] {result.error}"
            )
        elif isinstance(result.error, TimeoutError) and result.timeout is not None:
            self._print(
                f"   [red]⏱[/]   {name}: [bold red]TIMEOUT[/] (exceeded {result.timeout}s){retry_suffix}"
            )
        else:
            self._print(f"   [red]✗[/]   {name}: {result.error}{retry_suffix}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                self._print(f"[dim]       │ {line}[/]")

    def on_test_skip(self, result: TestResult) -> None:
        self._skipped += 1
        if self._verbosity >= Verbosity.NORMAL:
            name = _format_test_name(result)
            self._print(f"   [yellow]○[/]   {name} [dim]({result.skip_reason})[/]")

    def on_test_xfail(self, result: TestResult) -> None:
        self._xfailed += 1
        if self._verbosity >= Verbosity.NORMAL:
            name = _format_test_name(result)
            duration = _format_duration(result.duration)
            self._print(
                f"   [green]✗[/]   {name} [dim]({result.xfail_reason}) ({duration})[/]"
            )

    def on_test_xpass(self, result: TestResult) -> None:
        self._xpassed += 1
        # xpass is a problem - always show it like failures
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        self._print(f"   [red]⚡[/]   {name} [red]XPASS[/] [dim]({duration})[/]")

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
        self._print(f"\n[cyan]⏳ Async handlers ({pending_count})[/]")

    def on_handler_end(self, info: HandlerInfo) -> None:
        if not info.is_async:
            return
        if info.error:
            self._print(f"  [red]✗[/] {info.name}: {info.error}")
        else:
            duration = _format_duration(info.duration)
            self._print(f"  [green]✓[/] {info.name} [dim]({duration})[/]")

    def _format_traceback(self, error: Exception) -> str:
        lines = traceback.format_exception(type(error), error, error.__traceback__)
        return "".join(lines)

    def _print_failure_summary(self) -> None:
        if self._failed_results:
            self._print("\n[bold red]═══ FAILURES ═══[/]")
            for result in self._failed_results:
                self._print_failure_detail(result, is_error=False)

        if self._error_results:
            self._print("\n[bold yellow]═══ ERRORS ═══[/]")
            for result in self._error_results:
                self._print_failure_detail(result, is_error=True)

    def _print_failure_detail(self, result: TestResult, *, is_error: bool) -> None:
        name = _format_test_name(result)
        full_name = (
            f"{result.suite_path}{SuitePath.SEPARATOR}{name}"
            if result.suite_path
            else name
        )
        color = "yellow" if is_error else "red"
        self._print(f"\n[bold {color}]___ {full_name} ___[/]")

        if result.error:
            tb_text = self._format_traceback(result.error)
            for line in tb_text.rstrip().splitlines():
                escaped_line = line.replace("[", "\\[")
                self._print(f"[dim]{escaped_line}[/]")

        if result.output:
            self._print("[dim]--- Captured output ---[/]")
            for line in result.output.rstrip().splitlines():
                escaped_line = line.replace("[", "\\[")
                self._print(f"[dim]{escaped_line}[/]")

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

        log_file = Path(".protest/last_run.log")
        stdout_file = Path(".protest/last_run_stdout")
        if log_file.exists() or stdout_file.exists():
            self._print(
                "Full output: [dim].protest/last_run.log, .protest/last_run_stdout[/]"
            )

        duration = f"{result.duration:.2f}s"
        self._print(f"\n{status} │ {' │ '.join(parts)} │ {duration}")
