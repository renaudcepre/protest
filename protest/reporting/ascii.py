from pathlib import Path

from protest.entities import HandlerInfo, SessionResult, TestItem, TestResult
from protest.plugin import PluginBase

_MIN_NODE_ID_PARTS = 2


def _extract_suite_from_node_id(node_id: str) -> str | None:
    """Extract suite path from node_id like 'module::Suite::test_name'."""
    parts = node_id.split("::")
    if len(parts) >= _MIN_NODE_ID_PARTS:
        suite_parts = parts[1:-1]
        if suite_parts:
            return "::".join(suite_parts)
    return None


def _format_test_name(result: TestResult, include_suite: bool = False) -> str:
    """Format test name with optional suite prefix and case_ids."""
    name = result.name
    if include_suite:
        suite = _extract_suite_from_node_id(result.node_id)
        if suite:
            name = f"{suite}::{name}"
    if "[" in result.node_id:
        suffix = result.node_id[result.node_id.index("[") :]
        return f"{name}{suffix}"
    return name


MIN_DURATION_THRESHOLD = 0.001


def _format_duration(seconds: float) -> str:
    """Format duration: ms for fast, s for slow."""
    if seconds < MIN_DURATION_THRESHOLD:
        return "<1ms"
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


class AsciiReporter(PluginBase):
    """Plain ASCII reporter. No colors, no emojis. Works everywhere."""

    def __init__(self) -> None:
        self._is_parallel = False

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        self._is_parallel = len(items) > 1
        return items

    def on_session_start(self) -> None:
        print(">> Starting session")
        print()

    def on_suite_start(self, name: str) -> None:
        if not self._is_parallel:
            print(f"[] {name}")

    def on_test_pass(self, result: TestResult) -> None:
        name = _format_test_name(result, include_suite=self._is_parallel)
        duration = _format_duration(result.duration)
        print(f"  OK {name} ({duration})")

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result, include_suite=self._is_parallel)
        if result.is_fixture_error:
            print(f"  !! {name}:  {result.error}")
        elif isinstance(result.error, TimeoutError) and result.timeout is not None:
            print(f"  TO {name}: TIMEOUT (exceeded {result.timeout}s)")
        else:
            print(f"  XX {name}: {result.error}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                print(f"    | {line}")

    def on_test_skip(self, result: TestResult) -> None:
        name = _format_test_name(result, include_suite=self._is_parallel)
        print(f"  -- {name} ({result.skip_reason})")

    def on_test_xfail(self, result: TestResult) -> None:
        name = _format_test_name(result, include_suite=self._is_parallel)
        duration = _format_duration(result.duration)
        print(f"  xf {name} ({result.xfail_reason}) ({duration})")

    def on_test_xpass(self, result: TestResult) -> None:
        name = _format_test_name(result, include_suite=self._is_parallel)
        duration = _format_duration(result.duration)
        print(f"  XP {name} UNEXPECTED PASS ({duration})")

    def on_waiting_handlers(self, pending_count: int) -> None:
        print(f"\n.. Async handlers ({pending_count})")

    def on_handler_end(self, info: HandlerInfo) -> None:
        if not info.is_async:
            return
        if info.error:
            print(f"  XX {info.name}: {info.error}")
        else:
            duration = _format_duration(info.duration)
            print(f"  OK {info.name} ({duration})")

    def on_session_complete(self, result: SessionResult) -> None:
        total = (
            result.passed
            + result.failed
            + result.errors
            + result.skipped
            + result.xfailed
            + result.xpassed
        )

        if result.failed == 0 and result.errors == 0 and result.xpassed == 0:
            status = "OK ALL PASSED"
        else:
            status = "XX FAILURES"

        parts = [f"{result.passed}/{total} passed"]
        if result.skipped:
            parts.append(f"{result.skipped} skipped")
        if result.xfailed:
            parts.append(f"{result.xfailed} xfailed")
        if result.xpassed:
            parts.append(f"{result.xpassed} xpassed")
        if result.failed:
            parts.append(f"{result.failed} failed")
        if result.errors:
            parts.append(f"{result.errors} errors")

        duration = f"{result.duration:.2f}s"
        print(f"\n{status} | {' | '.join(parts)} | {duration}")

        log_file = Path(".protest/last_run.log")
        stdout_file = Path(".protest/last_run_stdout")
        if log_file.exists() or stdout_file.exists():
            print("Full output: .protest/last_run.log, .protest/last_run_stdout")
