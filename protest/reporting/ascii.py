from protest.entities import HandlerInfo, SessionResult, TestResult
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


class AsciiReporter(PluginBase):
    """Plain ASCII reporter. No colors, no emojis. Works everywhere."""

    def on_session_start(self) -> None:
        print(">> Starting session")
        print()

    def on_suite_start(self, name: str) -> None:
        print(f"[] {name}")

    def on_test_pass(self, result: TestResult) -> None:
        name = _format_test_name(result)
        duration = _format_duration(result.duration)
        print(f"  OK {name} ({duration})")

    def on_test_fail(self, result: TestResult) -> None:
        name = _format_test_name(result)
        if result.is_fixture_error:
            print(f"  !! {name}:  {result.error}")
        else:
            print(f"  XX {name}: {result.error}")

        if result.output:
            for line in result.output.rstrip().splitlines():
                print(f"    | {line}")

    def on_test_skip(self, result: TestResult) -> None:
        name = _format_test_name(result)
        print(f"  -- {name} ({result.skip_reason})")

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
        total = result.passed + result.failed + result.errors + result.skipped

        if result.failed == 0 and result.errors == 0:
            status = "OK ALL PASSED"
        else:
            status = "XX FAILURES"

        parts = [f"{result.passed}/{total} passed"]
        if result.skipped:
            parts.append(f"{result.skipped} skipped")
        if result.failed:
            parts.append(f"{result.failed} failed")
        if result.errors:
            parts.append(f"{result.errors} errors")

        duration = f"{result.duration:.2f}s"
        print(f"\n{status} | {' | '.join(parts)} | {duration}")
