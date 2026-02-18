import os
import time
import traceback
from argparse import ArgumentParser
from pathlib import Path

from rich.console import Console  # type: ignore[import-not-found]
from rich.live import Live  # type: ignore[import-not-found]
from rich.text import Text  # type: ignore[import-not-found]
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


def _format_test_name(result: TestResult) -> str:
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        escaped_suffix = suffix.replace("[", "\\[")
        return f"{result.name}{escaped_suffix}"
    return result.name


MIN_DURATION_THRESHOLD = 0.001
LIVE_REFRESH_PER_SECOND = 4


def _format_duration(seconds: float) -> str:
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


class RichReporter(PluginBase):
    """Rich console reporter with colors and live status footer."""

    name = "rich-reporter"
    description = "Rich console reporter with colors"

    def __init__(self, verbosity: int = 0) -> None:
        self.console = Console(highlight=False)
        self._verbosity = verbosity
        self._total_tests = 0
        self._failed_results: list[TestResult] = []
        self._error_results: list[TestResult] = []

        self._live: Live | None = None
        self._start_time: float = 0
        self._passed = 0
        self._failed = 0
        self._errors = 0
        self._skipped = 0
        self._xfailed = 0
        self._xpassed = 0
        # Progress tracking for visual squares
        self._test_statuses: list[str] = []  # "pass", "fail", "error", "skip", "xfail", "xpass"

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

    def _make_progress_squares(self) -> str:
        """Build visual progress indicator with colored squares."""
        max_squares = 100  # Condense to bar if more tests

        if self._total_tests <= max_squares:
            # Individual squares for each test
            squares = []
            for status in self._test_statuses:
                if status == "pass":
                    squares.append("[green]■[/]")
                elif status == "fail":
                    squares.append("[red]■[/]")
                elif status == "error":
                    squares.append("[yellow]■[/]")
                elif status == "skip":
                    squares.append("[dim]■[/]")
                elif status == "xfail":
                    squares.append("[dim green]■[/]")
                else:  # xpass
                    squares.append("[red]■[/]")
            # Pending tests
            pending = self._total_tests - len(self._test_statuses)
            squares.extend(["[dim]□[/]"] * pending)
            return "".join(squares)
        else:
            # Condensed progress bar for many tests
            bar_width = 30
            done = len(self._test_statuses)
            filled = int((done / self._total_tests) * bar_width) if self._total_tests else 0
            empty = bar_width - filled

            # Color based on failures
            if self._failed > 0 or self._errors > 0:
                bar_color = "red"
            else:
                bar_color = "green"

            return f"[{bar_color}]{'█' * filled}[/][dim]{'░' * empty}[/]"

    def _make_status_line(self) -> Text:
        elapsed = time.perf_counter() - self._start_time if self._start_time else 0
        total_done = (
            self._passed
            + self._failed
            + self._errors
            + self._skipped
            + self._xfailed
            + self._xpassed
        )

        progress_visual = self._make_progress_squares()

        if self._failed == 0 and self._errors == 0 and self._xpassed == 0:
            status = "[bold cyan]⋯[/]"
        else:
            status = "[bold red]✗[/]"

        duration = f"{elapsed:.2f}s"
        count = f"{total_done}/{self._total_tests}"

        return Text.from_markup(
            f"{status} {progress_visual} │ {count} │ {duration}"
        )

    def _print(self, message: str) -> None:
        if self._live and self._live.is_started:
            self._live.console.print(message)  # pragma: no cover
        else:
            self.console.print(message)

    def _update_live(self) -> None:
        if self._live and self._live.is_started:
            self._live.update(self._make_status_line())  # pragma: no cover

    def _stop_live(self) -> None:
        if self._live and self._live.is_started:  # pragma: no cover
            self._live.stop()
            self._live = None

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        self._total_tests = len(items)
        self._start_time = time.perf_counter()

        # Disable Live in CI (some CI systems have pseudo-TTYs)
        if self.console.is_terminal and not os.environ.get("CI"):
            self._live = Live(
                self._make_status_line(),
                console=self.console,
                refresh_per_second=LIVE_REFRESH_PER_SECOND,
                transient=False,  # Keep visible at end for debugging
            )
            self._live.start()

        return items

    def on_session_start(self) -> None:
        if self._verbosity >= 2:
            self._print("[dim]  session setup...[/]")

    def on_session_setup_done(self, info: SessionSetupInfo) -> None:
        if self._verbosity >= 2:
            self._print(
                f"[dim]  session setup done ({_format_duration(info.duration)})[/]"
            )

    def on_suite_setup_done(self, info: SuiteSetupInfo) -> None:
        # Suite headers at verbosity >= 1
        if self._verbosity >= 1:
            self._print(f"[cyan]       ◈ {info.name}[/]")
        # At verbosity 0, suite headers are hidden (progress bar shows status)

    def on_session_teardown_start(self) -> None:
        if self._verbosity >= 2:
            self._print("[dim]  session teardown...[/]")

    def on_suite_teardown_start(self, path: SuitePath) -> None:
        if self._verbosity >= 2:
            self._print(f"[dim]  suite '{path}' teardown...[/]")

    def on_suite_end(self, result: SuiteResult) -> None:
        if self._verbosity >= 2 and result.teardown_duration > 0:
            self._print(
                f"[dim]  {result.name} teardown done ({_format_duration(result.teardown_duration)})[/]"
            )

    def on_session_end(self, result: SessionResult) -> None:
        if self._verbosity >= 2 and result.teardown_duration > 0:
            self._print(
                f"[dim]  session teardown done ({_format_duration(result.teardown_duration)})[/]"
            )

    def on_suite_start(self, info: SuiteStartInfo) -> None:
        if self._verbosity >= 2:
            self._print(f"[dim]  suite '{info.name}' setup...[/]")

    def on_fixture_setup_start(self, info: FixtureInfo) -> None:
        if self._verbosity >= 3:
            scope_str = f"[dim]({info.scope.value})[/]"
            self._print(f"[dim]    ↳ fixture '{info.name}' setup... {scope_str}[/]")

    def on_fixture_setup_done(self, info: FixtureInfo) -> None:
        if self._verbosity >= 3:
            self._print(
                f"[dim]    ↳ fixture '{info.name}' ready ({_format_duration(info.duration)})[/]"
            )

    def on_fixture_teardown_start(self, info: FixtureInfo) -> None:
        if self._verbosity >= 3:
            self._print(f"[dim]    ↳ fixture '{info.name}' teardown...[/]")

    def on_fixture_teardown_done(self, info: FixtureInfo) -> None:
        if self._verbosity >= 3:
            self._print(
                f"[dim]    ↳ fixture '{info.name}' cleaned ({_format_duration(info.duration)})[/]"
            )

    def on_test_setup_done(self, info: TestStartInfo) -> None:
        if self._verbosity >= 3:
            self._print(f"[dim]       → {info.name} setup done[/]")

    def on_test_teardown_start(self, info: TestTeardownInfo) -> None:
        if self._verbosity >= 3:
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
        self._test_statuses.append("pass")
        if self._verbosity >= 1:
            name = _format_test_name(result)
            duration = _format_duration(result.duration)
            retry_suffix = ""
            if result.max_attempts > 1:
                retry_suffix = (
                    f" [dim]\\[attempt {result.attempt}/{result.max_attempts}][/]"
                )
            self._print(f"   [green]✓[/]   {name} [dim]({duration})[/]{retry_suffix}")
        self._update_live()

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result)
        retry_suffix = ""
        if result.max_attempts > 1:
            retry_suffix = f" [{result.max_attempts} attempts]"

        if result.is_fixture_error:
            self._error_results.append(result)
            self._errors += 1
            self._test_statuses.append("error")
        else:
            self._failed_results.append(result)
            self._failed += 1
            self._test_statuses.append("fail")

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

        self._update_live()

    def on_test_skip(self, result: TestResult) -> None:
        self._skipped += 1
        self._test_statuses.append("skip")
        if self._verbosity >= 1:
            name = _format_test_name(result)
            self._print(f"   [yellow]○[/]   {name} [dim]({result.skip_reason})[/]")
        self._update_live()

    def on_test_xfail(self, result: TestResult) -> None:
        self._xfailed += 1
        self._test_statuses.append("xfail")
        if self._verbosity >= 1:
            name = _format_test_name(result)
            duration = _format_duration(result.duration)
            self._print(
                f"   [green]✗[/]   {name} [dim]({result.xfail_reason}) ({duration})[/]"
            )
        self._update_live()

    def on_test_xpass(self, result: TestResult) -> None:
        self._xpassed += 1
        self._test_statuses.append("xpass")
        # xpass is a problem - always show it like failures
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        self._print(f"   [red]⚡[/]   {name} [red]XPASS[/] [dim]({duration})[/]")
        self._update_live()

    def on_session_interrupted(self, force_teardown: bool) -> None:
        self._stop_live()
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
        # Print failures ABOVE the live progress bar
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

        # Stop live at the very end - progress bar stays at bottom
        self._stop_live()
