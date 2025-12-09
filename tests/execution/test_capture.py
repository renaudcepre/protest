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
    _current_node_id,
    _log_callbacks,
    _log_records,
    _stdout_callbacks,
    add_log_callback,
    add_stdout_callback,
    get_current_log_records,
    get_session_setup_output,
    get_session_teardown_output,
    remove_log_callback,
    remove_stdout_callback,
    set_log_callback,
    set_session_setup_capture,
    set_session_teardown_capture,
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

    def test_show_output_writes_to_both_buffer_and_original(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original, show_output=True)
        buffer = io.StringIO()
        token = _capture_buffer.set(buffer)

        try:
            stream.write("tee output")
        finally:
            _capture_buffer.reset(token)

        assert buffer.getvalue() == "tee output"
        assert original.getvalue() == "tee output"

    def test_show_output_false_only_writes_to_buffer(self) -> None:
        original = io.StringIO()
        stream = TaskAwareStream(original, show_output=False)
        buffer = io.StringIO()
        token = _capture_buffer.set(buffer)

        try:
            stream.write("captured only")
        finally:
            _capture_buffer.reset(token)

        assert buffer.getvalue() == "captured only"
        assert original.getvalue() == ""


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

    def test_show_output_passed_to_streams(self) -> None:
        with GlobalCapturePatch(show_output=True):
            assert isinstance(sys.stdout, TaskAwareStream)
            assert sys.stdout._show_output is True
            assert sys.stderr._show_output is True

    def test_show_output_default_false(self) -> None:
        with GlobalCapturePatch():
            assert sys.stdout._show_output is False
            assert sys.stderr._show_output is False


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

    def test_show_output_captures_and_displays(self) -> None:
        original_stdout = io.StringIO()
        sys.stdout = original_stdout

        try:
            with GlobalCapturePatch(show_output=True), CaptureCurrentTest() as buffer:
                print("visible and captured")  # noqa: T201
        finally:
            sys.stdout = sys.__stdout__

        assert buffer.getvalue() == "visible and captured\n"
        assert original_stdout.getvalue() == "visible and captured\n"

    def test_no_show_output_only_captures(self) -> None:
        original_stdout = io.StringIO()
        sys.stdout = original_stdout

        try:
            with GlobalCapturePatch(show_output=False), CaptureCurrentTest() as buffer:
                print("captured only")  # noqa: T201
        finally:
            sys.stdout = sys.__stdout__

        assert buffer.getvalue() == "captured only\n"
        assert original_stdout.getvalue() == ""

    def test_print_captured_during_session_setup(self) -> None:
        with GlobalCapturePatch():
            set_session_setup_capture(True)
            try:
                print("setup output")  # noqa: T201
            finally:
                set_session_setup_capture(False)

            output = get_session_setup_output()

        assert output == "setup output\n"

    def test_print_captured_during_session_teardown(self) -> None:
        with GlobalCapturePatch():
            set_session_teardown_capture(True)
            try:
                print("teardown output")  # noqa: T201
            finally:
                set_session_teardown_capture(False)

            output = get_session_teardown_output()

        assert output == "teardown output\n"

    def test_session_setup_capture_has_priority_over_teardown(self) -> None:
        with GlobalCapturePatch():
            set_session_setup_capture(True)
            set_session_teardown_capture(True)
            try:
                print("goes to setup")  # noqa: T201
            finally:
                set_session_setup_capture(False)
                set_session_teardown_capture(False)

            setup_output = get_session_setup_output()
            teardown_output = get_session_teardown_output()

        assert setup_output == "goes to setup\n"
        assert teardown_output == ""

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


class TestLogCallbackSystem:
    def test_set_log_callback_replaces_all(self) -> None:
        original_callbacks = list(_log_callbacks)
        try:

            def callback_one(node_id: str, record: logging.LogRecord) -> None:
                pass

            def callback_two(node_id: str, record: logging.LogRecord) -> None:
                pass

            add_log_callback(callback_one)
            assert callback_one in _log_callbacks

            set_log_callback(callback_two)
            assert callback_one not in _log_callbacks
            assert callback_two in _log_callbacks
            assert len(_log_callbacks) == 1
        finally:
            _log_callbacks.clear()
            _log_callbacks.extend(original_callbacks)

    def test_set_log_callback_none_clears(self) -> None:
        original_callbacks = list(_log_callbacks)
        try:

            def callback(node_id: str, record: logging.LogRecord) -> None:
                pass

            add_log_callback(callback)
            assert len(_log_callbacks) >= 1

            set_log_callback(None)
            assert len(_log_callbacks) == 0
        finally:
            _log_callbacks.clear()
            _log_callbacks.extend(original_callbacks)


class TestCallbackInvocation:
    def test_stdout_callback_invoked_with_node_id(self) -> None:
        original_callbacks = list(_stdout_callbacks)
        received: list[tuple[str, str]] = []

        def callback(node_id: str, data: str) -> None:
            received.append((node_id, data))

        try:
            add_stdout_callback(callback)
            node_id_token = _current_node_id.set("module::test_example")
            buffer = io.StringIO()
            capture_token = _capture_buffer.set(buffer)

            original_stdout = io.StringIO()
            stream = TaskAwareStream(original_stdout)
            stream.write("test output")

            _capture_buffer.reset(capture_token)
            _current_node_id.reset(node_id_token)

            assert len(received) == 1
            assert received[0] == ("module::test_example", "test output")
        finally:
            _stdout_callbacks.clear()
            _stdout_callbacks.extend(original_callbacks)

    def test_log_callback_invoked_with_node_id(self) -> None:
        original_callbacks = list(_log_callbacks)
        received: list[tuple[str, logging.LogRecord]] = []

        def callback(node_id: str, record: logging.LogRecord) -> None:
            received.append((node_id, record))

        try:
            add_log_callback(callback)
            node_id_token = _current_node_id.set("module::test_log")

            handler = TaskAwareLogHandler()
            handler.setLevel(logging.DEBUG)
            logger = logging.getLogger("test.callback")
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)

            logger.info("callback test message")

            _current_node_id.reset(node_id_token)
            logger.removeHandler(handler)

            assert len(received) == 1
            assert received[0][0] == "module::test_log"
            assert received[0][1].getMessage() == "callback test message"
        finally:
            _log_callbacks.clear()
            _log_callbacks.extend(original_callbacks)

    def test_stdout_callback_not_called_without_node_id(self) -> None:
        original_callbacks = list(_stdout_callbacks)
        received: list[tuple[str, str]] = []

        def callback(node_id: str, data: str) -> None:
            received.append((node_id, data))

        try:
            add_stdout_callback(callback)
            buffer = io.StringIO()
            capture_token = _capture_buffer.set(buffer)

            original_stdout = io.StringIO()
            stream = TaskAwareStream(original_stdout)
            stream.write("test output")

            _capture_buffer.reset(capture_token)

            assert len(received) == 0
        finally:
            _stdout_callbacks.clear()
            _stdout_callbacks.extend(original_callbacks)


class TestGetCurrentLogRecords:
    def test_returns_empty_list_when_not_in_context(self) -> None:
        assert _log_records.get() is None
        result = get_current_log_records()
        assert result == []
        assert isinstance(result, list)

    def test_returns_records_when_in_context(self) -> None:
        records: list[logging.LogRecord] = []
        token = _log_records.set(records)
        try:
            result = get_current_log_records()
            assert result is records
        finally:
            _log_records.reset(token)


class TestCallbackAddRemove:
    def test_add_and_remove_log_callback(self) -> None:
        original_callbacks = list(_log_callbacks)
        try:

            def callback(node_id: str, record: logging.LogRecord) -> None:
                pass

            add_log_callback(callback)
            assert callback in _log_callbacks

            remove_log_callback(callback)
            assert callback not in _log_callbacks
        finally:
            _log_callbacks.clear()
            _log_callbacks.extend(original_callbacks)

    def test_add_and_remove_stdout_callback(self) -> None:
        original_callbacks = list(_stdout_callbacks)
        try:

            def callback(node_id: str, data: str) -> None:
                pass

            add_stdout_callback(callback)
            assert callback in _stdout_callbacks

            remove_stdout_callback(callback)
            assert callback not in _stdout_callbacks
        finally:
            _stdout_callbacks.clear()
            _stdout_callbacks.extend(original_callbacks)

    def test_remove_nonexistent_callback_is_safe(self) -> None:
        def callback(node_id: str, record: logging.LogRecord) -> None:
            pass

        remove_log_callback(callback)

        def stdout_callback(node_id: str, data: str) -> None:
            pass

        remove_stdout_callback(stdout_callback)
