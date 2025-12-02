import asyncio
import io
import logging
import sys

import pytest

from protest.execution.capture import (
    CaptureCurrentTest,
    GlobalCapturePatch,
    TaskAwareLogHandler,
    TaskAwareStream,
    _capture_buffer,
    _log_records,
)


class TestTaskAwareStream:
    """Tests for TaskAwareStream - context-aware stdout/stderr wrapper."""

    def test_writes_to_original_when_no_buffer_set(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original)

        stream.write("hello")

        assert original.getvalue() == "hello"

    def test_writes_to_buffer_when_buffer_set(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original)
        buffer = io.StringIO()
        token = _capture_buffer.set(buffer)

        try:
            stream.write("captured")
        finally:
            _capture_buffer.reset(token)

        assert buffer.getvalue() == "captured"
        assert original.getvalue() == ""

    def test_flush_flushes_both_buffer_and_original(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original)
        buffer = io.StringIO()
        token = _capture_buffer.set(buffer)

        try:
            stream.write("data")
            stream.flush()
        finally:
            _capture_buffer.reset(token)

        assert buffer.getvalue() == "data"

    def test_delegates_unknown_attributes_to_original(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original)

        assert stream.readable() == original.readable()  # type: ignore[operator]
        assert stream.writable() == original.writable()  # type: ignore[operator]


class TestCaptureCurrentTest:
    """Tests for CaptureCurrentTest context manager."""

    def test_captures_output_within_context(self) -> None:
        with CaptureCurrentTest() as buffer:
            token = _capture_buffer.set(buffer)
            try:
                buffer.write("test output")
            finally:
                _capture_buffer.reset(token)

        assert buffer.getvalue() == "test output"

    def test_returns_string_io_buffer(self) -> None:
        with CaptureCurrentTest() as buffer:
            assert isinstance(buffer, io.StringIO)

    def test_resets_context_var_on_exit(self) -> None:
        with CaptureCurrentTest():
            assert _capture_buffer.get() is not None

        assert _capture_buffer.get() is None


class TestGlobalCapturePatch:
    """Tests for GlobalCapturePatch - global stdout/stderr patching."""

    def test_replaces_stdout_with_task_aware_stream(self) -> None:
        original_stdout = sys.stdout

        with GlobalCapturePatch():
            assert isinstance(sys.stdout, TaskAwareStream)

        assert sys.stdout is original_stdout

    def test_replaces_stderr_with_task_aware_stream(self) -> None:
        original_stderr = sys.stderr

        with GlobalCapturePatch():
            assert isinstance(sys.stderr, TaskAwareStream)

        assert sys.stderr is original_stderr

    def test_restores_streams_on_exception(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        with pytest.raises(ValueError), GlobalCapturePatch():
            raise ValueError("test error")

        assert sys.stdout is original_stdout
        assert sys.stderr is original_stderr


class TestCaptureIntegration:
    """Integration tests for stdout/stderr capture in test execution."""

    def test_print_captured_within_context(self) -> None:
        with GlobalCapturePatch(), CaptureCurrentTest() as buffer:
            print("hello from print")  # noqa: T201

        assert buffer.getvalue() == "hello from print\n"

    def test_print_not_captured_outside_capture_context(self) -> None:
        original_stdout = io.StringIO()
        sys.stdout = original_stdout

        try:
            with GlobalCapturePatch():
                print("not captured")  # noqa: T201
        finally:
            sys.stdout = sys.__stdout__

        assert original_stdout.getvalue() == "not captured\n"

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_capture(self) -> None:
        results: dict[str, str] = {}

        async def task_with_output(name: str, delay: float) -> None:
            with CaptureCurrentTest() as buffer:
                print(f"[{name}] start")  # noqa: T201
                await asyncio.sleep(delay)
                print(f"[{name}] end")  # noqa: T201
                results[name] = buffer.getvalue()

        with GlobalCapturePatch():
            await asyncio.gather(
                task_with_output("A", 0.02),
                task_with_output("B", 0.01),
            )

        assert results["A"] == "[A] start\n[A] end\n"
        assert results["B"] == "[B] start\n[B] end\n"

    @pytest.mark.asyncio
    async def test_interleaved_prints_stay_isolated(self) -> None:
        results: dict[str, str] = {}

        async def interleaved_task(name: str) -> None:
            with CaptureCurrentTest() as buffer:
                for step in range(3):
                    print(f"[{name}] step {step}")  # noqa: T201
                    await asyncio.sleep(0.005)
                results[name] = buffer.getvalue()

        with GlobalCapturePatch():
            await asyncio.gather(
                interleaved_task("X"),
                interleaved_task("Y"),
                interleaved_task("Z"),
            )

        assert results["X"] == "[X] step 0\n[X] step 1\n[X] step 2\n"
        assert results["Y"] == "[Y] step 0\n[Y] step 1\n[Y] step 2\n"
        assert results["Z"] == "[Z] step 0\n[Z] step 1\n[Z] step 2\n"


class TestTaskAwareLogHandler:
    """Tests for TaskAwareLogHandler - context-aware log record capture."""

    def test_does_not_capture_when_no_records_list(self) -> None:
        handler = TaskAwareLogHandler()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("test.no_capture")
        logger.addHandler(handler)

        try:
            logger.info("should not be captured")
        finally:
            logger.removeHandler(handler)

        assert _log_records.get() is None

    def test_captures_when_records_list_set(self) -> None:
        handler = TaskAwareLogHandler()
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger("test.capture")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        records: list[logging.LogRecord] = []
        token = _log_records.set(records)

        try:
            logger.info("captured message")
        finally:
            _log_records.reset(token)
            logger.removeHandler(handler)

        assert len(records) == 1
        assert records[0].getMessage() == "captured message"


class TestCaptureCurrentTestLogs:
    """Tests for log capture within CaptureCurrentTest context."""

    def test_captures_logs_in_context(self) -> None:
        handler = TaskAwareLogHandler()
        handler.setLevel(logging.DEBUG)
        logging.root.addHandler(handler)
        original_level = logging.root.level
        logging.root.setLevel(logging.NOTSET)

        try:
            with CaptureCurrentTest():
                records = _log_records.get()
                assert records is not None
                logging.info("test log message")

            assert len(records) == 1
            assert records[0].getMessage() == "test log message"
        finally:
            logging.root.removeHandler(handler)
            logging.root.setLevel(original_level)

    def test_no_capture_outside_context(self) -> None:
        handler = TaskAwareLogHandler()
        handler.setLevel(logging.DEBUG)
        logging.root.addHandler(handler)

        try:
            logging.info("outside context")
            assert _log_records.get() is None
        finally:
            logging.root.removeHandler(handler)

    def test_resets_log_records_on_exit(self) -> None:
        with CaptureCurrentTest():
            assert _log_records.get() is not None

        assert _log_records.get() is None


class TestLogCaptureIntegration:
    """Integration tests for log capture across concurrent async tasks."""

    def test_global_patch_installs_and_removes_handler(self) -> None:
        initial_handler_count = len(logging.root.handlers)

        with GlobalCapturePatch():
            handler_count_during = len(logging.root.handlers)

        final_handler_count = len(logging.root.handlers)

        assert handler_count_during == initial_handler_count + 1
        assert final_handler_count == initial_handler_count

    def test_global_patch_sets_log_level_to_notset(self) -> None:
        logging.root.setLevel(logging.WARNING)

        try:
            with GlobalCapturePatch():
                assert logging.root.level == logging.NOTSET

            assert logging.root.level == logging.WARNING
        finally:
            logging.root.setLevel(logging.WARNING)

    def test_full_log_capture_flow(self) -> None:
        with GlobalCapturePatch(), CaptureCurrentTest():
            records = _log_records.get()
            assert records is not None
            logging.debug("debug msg")
            logging.info("info msg")
            logging.warning("warning msg")

        assert len(records) == 3
        assert records[0].levelname == "DEBUG"
        assert records[1].levelname == "INFO"
        assert records[2].levelname == "WARNING"

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_logs(self) -> None:
        results: dict[str, list[logging.LogRecord]] = {}

        async def task_with_logs(name: str, delay: float) -> None:
            with CaptureCurrentTest():
                records = _log_records.get()
                assert records is not None
                logging.info(f"[{name}] start")
                await asyncio.sleep(delay)
                logging.info(f"[{name}] end")
                results[name] = list(records)

        with GlobalCapturePatch():
            await asyncio.gather(
                task_with_logs("A", 0.02),
                task_with_logs("B", 0.01),
            )

        assert len(results["A"]) == 2
        assert results["A"][0].getMessage() == "[A] start"
        assert results["A"][1].getMessage() == "[A] end"

        assert len(results["B"]) == 2
        assert results["B"][0].getMessage() == "[B] start"
        assert results["B"][1].getMessage() == "[B] end"

    @pytest.mark.asyncio
    async def test_interleaved_logs_stay_isolated(self) -> None:
        results: dict[str, list[logging.LogRecord]] = {}

        async def interleaved_task(name: str) -> None:
            with CaptureCurrentTest():
                records = _log_records.get()
                assert records is not None
                for step in range(3):
                    logging.info(f"[{name}] step {step}")
                    await asyncio.sleep(0.005)
                results[name] = list(records)

        with GlobalCapturePatch():
            await asyncio.gather(
                interleaved_task("X"),
                interleaved_task("Y"),
                interleaved_task("Z"),
            )

        expected_message_count = 3
        for name in ["X", "Y", "Z"]:
            assert len(results[name]) == expected_message_count
            for step in range(3):
                assert results[name][step].getMessage() == f"[{name}] step {step}"
