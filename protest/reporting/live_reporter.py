import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rich.console import (  # type: ignore[import-not-found]
    Console,
    Group,
    RenderableType,
)
from rich.live import Live  # type: ignore[import-not-found]
from rich.padding import Padding  # type: ignore[import-not-found]
from rich.spinner import Spinner  # type: ignore[import-not-found]
from rich.table import Table  # type: ignore[import-not-found]
from rich.text import Text  # type: ignore[import-not-found]

from protest.entities import (
    HandlerInfo,
    SessionResult,
    TestItem,
    TestResult,
    TestStartInfo,
)
from protest.execution.capture import add_log_callback, remove_log_callback
from protest.plugin import PluginBase


class TestPhase(Enum):
    PENDING = "pending"
    WAITING = "waiting"
    SETUP = "setup"
    RUNNING = "running"
    TEARDOWN = "teardown"
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAILED = "xfailed"
    XPASSED = "xpassed"


@dataclass
class ActiveTest:
    node_id: str
    name: str
    phase: TestPhase
    start_time: float
    suite_path: str | None = None
    phase_start_time: float = field(default_factory=time.perf_counter)
    duration: float = 0
    result_info: str = ""


PHASE_LABELS = {
    TestPhase.PENDING: "[dim]·[/]",
    TestPhase.WAITING: "[dim]…[/]",
    TestPhase.SETUP: "[cyan]setup[/]",
    TestPhase.RUNNING: "[green]running[/]",
    TestPhase.TEARDOWN: "[yellow]teardown[/]",
    TestPhase.PASSED: "[green]✓[/]",
    TestPhase.FAILED: "[red]✗[/]",
    TestPhase.TIMEOUT: "[red]⏱[/]",
    TestPhase.ERROR: "[yellow]⚠[/]",
    TestPhase.SKIPPED: "[yellow]○[/]",
    TestPhase.XFAILED: "[green]✗[/]",
    TestPhase.XPASSED: "[red]⚡[/]",
}

MIN_DURATION_THRESHOLD = 0.001
PHASE_DISPLAY_THRESHOLD = 0.1


def _format_duration(seconds: float) -> str:
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


def _format_test_name(result: TestResult, escape_markup: bool = True) -> str:
    """Format test name with case_ids suffix.

    Args:
        escape_markup: If True, escape brackets for Rich markup strings.
                      If False, return raw text (for Text() objects).
    """
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        if escape_markup:
            suffix = suffix.replace("[", "\\[")
        return f"{result.name}{suffix}"
    return result.name


def _format_active_test_name(test: ActiveTest) -> str:
    """Format test name for Text() objects (no markup escaping needed)."""
    if "[" in test.node_id:
        suffix = test.node_id[test.node_id.index("[") :]
        return f"{test.name}{suffix}"
    return test.name


@dataclass
class SuiteTeardown:
    name: str
    start_time: float
    done: bool = False
    duration: float = 0


class LiveReporter(PluginBase):
    def __init__(self) -> None:
        self._console = Console(highlight=False)
        self._live: Live | None = None
        self._active_tests: dict[str, ActiveTest] = {}
        self._test_order: list[str] = []
        self._suite_teardowns: dict[str, SuiteTeardown] = {}
        self._last_logs: dict[str, str] = {}
        self._collected_items: dict[str, TestItem] = {}
        self._current_suite: str | None = None
        self._passed = 0
        self._failed = 0
        self._errors = 0
        self._skipped = 0
        self._xfailed = 0
        self._xpassed = 0
        self._start_time: float = 0
        self._is_parallel = False
        self._is_live_mode = False

    def _should_use_live_mode(self) -> bool:
        if not self._console.is_terminal:
            return False
        if os.environ.get("CI"):
            return False
        return self._is_parallel

    def _is_finished(self, phase: TestPhase) -> bool:
        return phase in (
            TestPhase.PASSED,
            TestPhase.FAILED,
            TestPhase.TIMEOUT,
            TestPhase.ERROR,
            TestPhase.SKIPPED,
            TestPhase.XFAILED,
            TestPhase.XPASSED,
        )

    def _is_running(self, phase: TestPhase) -> bool:
        return phase in (
            TestPhase.SETUP,
            TestPhase.RUNNING,
            TestPhase.TEARDOWN,
        )

    def _build_active_tests_table(self) -> Table:
        terminal_width = self._console.size.width
        table_width = min(terminal_width, 140)
        table = Table(show_header=False, box=None, padding=(0, 1), width=table_width)
        table.add_column("status", width=4, no_wrap=True)
        table.add_column("name", ratio=2, no_wrap=True, overflow="ellipsis")
        table.add_column(
            "info", ratio=1, justify="right", no_wrap=True, overflow="ellipsis"
        )

        current_suite: str | None = "__unset__"

        for node_id in self._test_order:
            test = self._active_tests.get(node_id)
            if test is None:
                continue

            if test.suite_path != current_suite:
                current_suite = test.suite_path
                self._add_suite_header_row(table, current_suite)

            name_col = Text(_format_active_test_name(test), overflow="ellipsis")

            if self._is_finished(test.phase):
                status_col = Text.from_markup(f"  {PHASE_LABELS[test.phase]}")
                info_col = Text(test.result_info, style="dim")
                table.add_row(status_col, name_col, info_col)
            elif self._is_running(test.phase):
                status_col = Padding(Spinner("dots", style="cyan"), (0, 0, 0, 2))
                phase_duration = time.perf_counter() - test.phase_start_time
                if phase_duration < PHASE_DISPLAY_THRESHOLD:
                    info_col = Text.from_markup(PHASE_LABELS[test.phase])
                else:
                    info_col = Text.from_markup(
                        f"{PHASE_LABELS[test.phase]} {_format_duration(phase_duration)}",
                    )

                if last_log := self._last_logs.get(node_id):
                    name_col.append(f" → {last_log}", style="dim")
                table.add_row(status_col, name_col, info_col)
            else:
                status_col = Text.from_markup(f"  {PHASE_LABELS[test.phase]}")
                info_col = Text("")
                table.add_row(status_col, name_col, info_col)

        return table

    def _add_suite_header_row(self, table: Table, suite_path: str | None) -> None:
        suite_label = suite_path if suite_path else "(standalone)"
        teardown = self._suite_teardowns.get(suite_path) if suite_path else None
        suite_text = Text(f"◈ {suite_label}", style="cyan", overflow="ellipsis")

        if teardown is None:
            table.add_row(Text(""), suite_text, Text(""))
        elif teardown.done:
            table.add_row(
                Text(""),
                suite_text,
                Text(f"teardown ({_format_duration(teardown.duration)})", style="dim"),
            )
        else:
            elapsed = time.perf_counter() - teardown.start_time
            if elapsed < PHASE_DISPLAY_THRESHOLD:
                info = Text("teardown", style="yellow")
            else:
                info = Text(f"teardown {_format_duration(elapsed)}", style="yellow")
            table.add_row(
                Padding(Spinner("dots", style="yellow"), (0, 0, 0, 2)),
                suite_text,
                info,
            )

    def _build_summary_line(self) -> Text:
        elapsed = time.perf_counter() - self._start_time
        total = len(self._active_tests)
        done = (
            self._passed
            + self._failed
            + self._errors
            + self._skipped
            + self._xfailed
            + self._xpassed
        )
        all_done = done == total and total > 0

        if all_done:
            if self._failed or self._errors or self._xpassed:
                status = "[bold red]✗ FAILURES[/]"
            else:
                status = "[bold green]✓ ALL PASSED[/]"
        elif self._failed or self._errors or self._xpassed:
            status = "[bold red]RUNNING[/]"
        else:
            status = "[bold cyan]RUNNING[/]"

        parts = [f"{self._passed}/{total} passed"]
        if self._skipped:
            parts.append(f"[yellow]{self._skipped} skipped[/]")
        if self._xfailed:
            parts.append(f"[dim]{self._xfailed} xfailed[/]")
        if self._xpassed:
            parts.append(f"[red]{self._xpassed} xpassed[/]")
        if self._failed:
            parts.append(f"[red]{self._failed} failed[/]")
        if self._errors:
            parts.append(f"[yellow]{self._errors} errors[/]")

        return Text.from_markup(
            f"{status} | {' | '.join(parts)} | {_format_duration(elapsed)}"
        )

    def _build_display(self) -> RenderableType:
        elements: list[RenderableType] = []

        if self._active_tests:
            elements.append(self._build_active_tests_table())

        elements.append(self._build_summary_line())

        return Group(*elements)

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._build_display())

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        self._is_parallel = len(items) > 1
        self._is_live_mode = self._should_use_live_mode()
        self._collected_items = {item.node_id: item for item in items}
        return items

    def _on_log(self, node_id: str, record: logging.LogRecord) -> None:
        """Handle a log record from a test."""
        self._last_logs[node_id] = record.getMessage()
        if self._is_live_mode:
            self._refresh()

    def on_session_start(self) -> None:
        self._start_time = time.perf_counter()

        if self._is_live_mode:
            add_log_callback(self._on_log)
            self._live = Live(
                self._build_display(),
                console=self._console,
                refresh_per_second=10,
                transient=False,
            )
            self._live.start()

    def on_suite_start(self, name: str) -> None:
        self._current_suite = name
        if self._is_live_mode:
            self._refresh()
        else:
            self._console.print(f"[cyan]{name}[/]")

    def on_suite_end(self, name: str) -> None:
        pass

    def on_suite_teardown_start(self, name: str) -> None:
        self._suite_teardowns[name] = SuiteTeardown(
            name=name,
            start_time=time.perf_counter(),
        )
        if self._is_live_mode:
            self._refresh()

    def on_suite_teardown_done(self, name: str) -> None:
        if teardown := self._suite_teardowns.get(name):
            teardown.done = True
            teardown.duration = time.perf_counter() - teardown.start_time
        if self._is_live_mode:
            self._refresh()

    def on_test_start(self, info: TestStartInfo) -> None:
        if info.node_id not in self._active_tests:
            now = time.perf_counter()
            item = self._collected_items.get(info.node_id)
            suite_path = item.suite_path if item else None
            self._test_order.append(info.node_id)
            self._active_tests[info.node_id] = ActiveTest(
                node_id=info.node_id,
                name=info.name,
                phase=TestPhase.WAITING,
                start_time=now,
                suite_path=suite_path,
                phase_start_time=now,
            )
        else:
            test = self._active_tests[info.node_id]
            test.phase = TestPhase.WAITING
            test.phase_start_time = time.perf_counter()

        if self._is_live_mode:
            self._refresh()

    def on_test_acquired(self, info: TestStartInfo) -> None:
        if test := self._active_tests.get(info.node_id):
            test.phase = TestPhase.SETUP
            test.phase_start_time = time.perf_counter()

        if self._is_live_mode:
            self._refresh()

    def on_test_setup_done(self, info: TestStartInfo) -> None:
        if test := self._active_tests.get(info.node_id):
            test.phase = TestPhase.RUNNING
            test.phase_start_time = time.perf_counter()

        if self._is_live_mode:
            self._refresh()

    def on_test_teardown_start(self, info: TestStartInfo) -> None:
        if test := self._active_tests.get(info.node_id):
            test.phase = TestPhase.TEARDOWN
            test.phase_start_time = time.perf_counter()

        if self._is_live_mode:
            self._refresh()

    def _finish_test(self, node_id: str, phase: TestPhase, info: str) -> None:
        if test := self._active_tests.get(node_id):
            test.phase = phase
            test.result_info = info
        self._last_logs.pop(node_id, None)

    def on_test_pass(self, result: TestResult) -> None:
        self._passed += 1
        duration = _format_duration(result.duration)
        self._finish_test(result.node_id, TestPhase.PASSED, f"({duration})")

        if self._is_live_mode:
            self._refresh()
        else:
            name = _format_test_name(result)
            self._console.print(f"  [green]✓[/] {name} [dim]({duration})[/]")

    def on_test_fail(self, result: TestResult) -> None:
        if result.is_fixture_error:
            self._errors += 1
            phase = TestPhase.ERROR
            info = f"[FIXTURE] {result.error}"
        elif isinstance(result.error, TimeoutError) and result.timeout is not None:
            self._failed += 1
            phase = TestPhase.TIMEOUT
            info = f"TIMEOUT (exceeded {result.timeout}s)"
        else:
            self._failed += 1
            phase = TestPhase.FAILED
            info = str(result.error)

        self._finish_test(result.node_id, phase, info)

        if self._is_live_mode:
            self._refresh()
        else:
            self._console.print(self._format_failure(result))

    def _format_failure(self, result: TestResult) -> str:
        name = _format_test_name(result)
        if result.is_fixture_error:
            line = f"  [yellow]⚠[/] {name}: [bold yellow]\\[FIXTURE][/] {result.error}"
        elif isinstance(result.error, TimeoutError) and result.timeout is not None:
            line = (
                f"  [red]⏱[/] {name}: [bold red]TIMEOUT[/] (exceeded {result.timeout}s)"
            )
        else:
            line = f"  [red]✗[/] {name}: {result.error}"

        if result.output:
            output_lines = [
                f"[dim]    │ {ln}[/]" for ln in result.output.rstrip().splitlines()
            ]
            line += "\n" + "\n".join(output_lines)

        return line

    def on_test_skip(self, result: TestResult) -> None:
        self._skipped += 1
        self._finish_test(result.node_id, TestPhase.SKIPPED, f"({result.skip_reason})")

        if self._is_live_mode:
            self._refresh()
        else:
            name = _format_test_name(result)
            self._console.print(f"  [yellow]○[/] {name} [dim]({result.skip_reason})[/]")

    def on_test_xfail(self, result: TestResult) -> None:
        self._xfailed += 1
        duration = _format_duration(result.duration)
        self._finish_test(
            result.node_id, TestPhase.XFAILED, f"({result.xfail_reason}) ({duration})"
        )

        if self._is_live_mode:
            self._refresh()
        else:
            name = _format_test_name(result)
            self._console.print(
                f"  [green]✗[/] {name} [dim]({result.xfail_reason}) ({duration})[/]"
            )

    def on_test_xpass(self, result: TestResult) -> None:
        self._xpassed += 1
        duration = _format_duration(result.duration)
        self._finish_test(result.node_id, TestPhase.XPASSED, f"XPASS ({duration})")

        if self._is_live_mode:
            self._refresh()
        else:
            name = _format_test_name(result)
            self._console.print(
                f"  [red]⚡[/] {name} [red]XPASS[/] [dim]({duration})[/]"
            )

    def on_waiting_handlers(self, pending_count: int) -> None:
        if self._is_live_mode and self._live is not None:
            self._live.stop()
            self._live = None
        self._console.print(f"\n[cyan].. Async handlers ({pending_count})[/]")

    def on_handler_end(self, info: HandlerInfo) -> None:
        if not info.is_async:
            return
        if info.error:
            self._console.print(f"  [red]✗[/] {info.name}: {info.error}")
        else:
            duration = _format_duration(info.duration)
            self._console.print(f"  [green]✓[/] {info.name} [dim]({duration})[/]")

    def on_session_complete(self, result: SessionResult) -> None:
        if self._is_live_mode:
            remove_log_callback(self._on_log)

        if self._is_live_mode and self._live is not None:
            self._refresh()
            self._live.stop()
            self._live = None
            self._print_log_file_hint()
            return

        total = (
            result.passed
            + result.failed
            + result.errors
            + result.skipped
            + result.xfailed
            + result.xpassed
        )

        if result.failed == 0 and result.errors == 0 and result.xpassed == 0:
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
        self._console.print(f"\n{status} | {' | '.join(parts)} | {duration}")
        self._print_log_file_hint()

    def _print_log_file_hint(self) -> None:
        log_file = Path(".protest/last_run.log")
        stdout_file = Path(".protest/last_run_stdout")
        if log_file.exists() or stdout_file.exists():
            self._console.print(
                "[dim]Full output: .protest/last_run.log, .protest/last_run_stdout[/]"
            )
