import logging
import sys
import traceback
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from rich.console import Console  # type: ignore[import-not-found]
from rich.table import Table  # type: ignore[import-not-found]
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
from protest.evals.types import EvalSuiteReport
from protest.plugin import PluginBase, PluginContext
from protest.reporting.verbosity import Verbosity


def _short_label(name: str, node_id: str) -> str:
    """name + [case_id] from node_id."""
    if "[" in node_id:
        suffix = node_id[node_id.index("[") :]
        return f"{name}{suffix}"
    return name


def _format_test_name(result: TestResult) -> str:
    label = _short_label(result.name, result.node_id)
    return label.replace("[", "\\[")


MIN_DURATION_THRESHOLD = 0.001


def _format_duration(seconds: float) -> str:
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _format_eval_scores_inline(result: TestResult) -> str:
    """Format eval scores for inline display (e.g. ' bg_score=0.8 char_id=1.0')."""
    if not result.eval_payload:
        return ""
    parts = []
    for name, entry in result.eval_payload.scores.items():
        if entry.skipped:
            parts.append(f"{name}=⊘")
            continue
        val = entry.value
        if isinstance(val, bool):
            parts.append(f"{name}={'✓' if val else '✗'}")
        elif isinstance(val, float):
            parts.append(f"{name}={val:.2f}")
        else:
            parts.append(f"{name}={val}")
    return f" [dim]{' '.join(parts)}[/]" if parts else ""


class RichReporter(PluginBase):
    """Rich console reporter with colors."""

    name = "rich-reporter"
    description = "Rich console reporter with colors"

    def __init__(
        self,
        verbosity: int = 0,
        show_logs: str | None = None,
        show_output: bool = False,
    ) -> None:
        self.console = Console(highlight=False)
        self._verbosity = verbosity
        self._show_logs = show_logs
        self._show_output = show_output
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
        group.add_argument(
            "--show-logs",
            dest="show_logs",
            nargs="?",
            const="INFO",
            default=None,
            metavar="LEVEL",
            help="Show captured log records (default: INFO+)",
        )
        group.add_argument(
            "--show-output",
            dest="show_output",
            action="store_true",
            help="Show eval inputs/output/expected per case",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self | None:
        if ctx.get("no_color", False):
            return None
        return cls(
            verbosity=ctx.get("verbosity", 0),
            show_logs=ctx.get("show_logs"),
            show_output=ctx.get("show_output", False),
        )

    def _print(self, message: str) -> None:
        self.console.print(message)

    def _print_eval_detail(self, result: TestResult) -> None:
        """Print eval inputs/output/expected for -vv verbosity."""
        p = result.eval_payload
        if not p:
            return
        if p.inputs is not None:
            inp = str(p.inputs)[:200]
            self._print(f"[dim]       │ inputs: {inp}[/]")
        if p.output is not None:
            out = str(p.output)[:200]
            self._print(f"[dim]       │ output: {out}[/]")
        if p.expected_output is not None:
            exp = str(p.expected_output)[:200]
            self._print(f"[dim]       │ expected: {exp}[/]")

    def _maybe_show_logs(self, result: TestResult) -> None:
        """Show captured log records if --show-logs is active."""
        if not self._show_logs or not result.log_records:
            return
        min_level = getattr(logging, self._show_logs.upper(), logging.INFO)
        for record in result.log_records:
            if record.levelno >= min_level:
                level = record.levelname
                color = (
                    "red"
                    if record.levelno >= logging.ERROR
                    else "yellow"
                    if record.levelno >= logging.WARNING
                    else "dim"
                )
                self._print(
                    f"[{color}]       LOG [{level}] {record.name}: {record.getMessage()}[/]"
                )

    def _print_bypass(self, message: str) -> None:
        """Print bypassing capture (for lifecycle messages emitted during tests)."""
        stream = getattr(sys.stdout, "_original", sys.stdout)
        Console(file=stream, highlight=False).print(message)

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
        if self._verbosity >= Verbosity.NORMAL:
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
            label = _short_label(info.name, info.node_id).replace("[", "\\[")
            self._print_bypass(f"[dim]       → {label} setup done[/]")

    def on_test_teardown_start(self, info: TestTeardownInfo) -> None:
        if self._verbosity >= Verbosity.FIXTURES:
            label = _short_label(info.name, info.node_id).replace("[", "\\[")
            self._print_bypass(f"[dim]       ← {label} teardown...[/]")

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
            scores_str = _format_eval_scores_inline(result) if result.is_eval else ""
            self._print(
                f"   [green]✓[/]   {name} [dim]({duration})[/]{scores_str}{retry_suffix}"
            )
            if self._show_output and result.is_eval:
                self._print_eval_detail(result)
            self._maybe_show_logs(result)

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
            lines = result.output.rstrip().splitlines()
            max_lines = 20
            for line in lines[:max_lines]:
                self._print(f"[dim]       │ {line}[/]")
            if len(lines) > max_lines:
                self._print(
                    f"[dim]       │ ... ({len(lines) - max_lines} more lines in .protest/last_run_stdout)[/]"
                )
        if result.is_eval:
            self._print_eval_detail(result)  # always show on fail
        self._maybe_show_logs(result)

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
        non_eval_failures = [r for r in self._failed_results if not r.is_eval]
        if non_eval_failures:
            self._print("\n[bold red]═══ FAILURES ═══[/]")
            for result in non_eval_failures:
                self._print_failure_detail(result, is_error=False)

        non_eval_errors = [r for r in self._error_results if not r.is_eval]
        if non_eval_errors:
            self._print("\n[bold yellow]═══ ERRORS ═══[/]")
            for result in non_eval_errors:
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

    def on_user_print(self, data: Any) -> None:
        msg, raw = data
        # Write to the real stdout, bypassing capture
        stream = getattr(sys.stdout, "_original", sys.stdout)
        c = Console(file=stream, highlight=False)
        if raw:
            c.print(msg, markup=False)
        else:
            c.print(f"[dim]       │[/] {msg}")

    def on_eval_suite_end(self, report: Any) -> None:
        if not isinstance(report, EvalSuiteReport):
            return
        stats = report.all_score_stats()
        self._print("")
        if stats:
            table = Table(
                title=f"Eval: {report.suite_name} ({report.total_count} cases)",
                show_header=True,
                header_style="bold cyan",
                padding=(0, 1),
            )
            table.add_column("Score", style="cyan", no_wrap=True)
            table.add_column("mean", justify="right")
            table.add_column("p50", justify="right")
            table.add_column("p5", justify="right", style="dim")
            table.add_column("p95", justify="right", style="dim")
            for s in stats:
                table.add_row(
                    s.name,
                    f"{s.mean:.2f}",
                    f"{s.median:.2f}",
                    f"{s.p5:.2f}",
                    f"{s.p95:.2f}",
                )
            self.console.print(table)
        else:
            self._print(
                f"  [cyan]Eval: {report.suite_name} ({report.total_count} cases)[/]"
            )
        full_pass = 100
        half_pass = 50
        rate_pct = report.pass_rate * full_pass
        color = (
            "green"
            if rate_pct >= full_pass
            else "yellow"
            if rate_pct >= half_pass
            else "red"
        )
        self._print(
            f"  [{color}]Passed: {report.passed_count}/{report.total_count} ({rate_pct:.1f}%)[/]"
        )

    def on_session_complete(self, result: SessionResult) -> None:
        has_non_eval_failures = any(not r.is_eval for r in self._failed_results)
        has_non_eval_errors = any(not r.is_eval for r in self._error_results)
        if has_non_eval_failures or has_non_eval_errors:
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
