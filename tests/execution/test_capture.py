import asyncio
import io
import sys

import pytest

from protest.execution.capture import (
    CaptureCurrentTest,
    GlobalCapturePatch,
    TaskAwareStream,
    _capture_buffer,
)


class TestTaskAwareStream:
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

        assert stream.readable() == original.readable()
        assert stream.writable() == original.writable()


class TestCaptureCurrentTest:
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

        with pytest.raises(ValueError):
            with GlobalCapturePatch():
                raise ValueError("test error")

        assert sys.stdout is original_stdout
        assert sys.stderr is original_stderr


class TestCaptureIntegration:
    def test_print_captured_within_context(self) -> None:
        with GlobalCapturePatch():
            with CaptureCurrentTest() as buffer:
                print("hello from print")

        assert buffer.getvalue() == "hello from print\n"

    def test_print_not_captured_outside_capture_context(self) -> None:
        original_stdout = io.StringIO()
        sys.stdout = original_stdout

        try:
            with GlobalCapturePatch():
                print("not captured")
        finally:
            sys.stdout = sys.__stdout__

        assert original_stdout.getvalue() == "not captured\n"

    @pytest.mark.asyncio
    async def test_concurrent_tasks_have_isolated_capture(self) -> None:
        results: dict[str, str] = {}

        async def task_with_output(name: str, delay: float) -> None:
            with CaptureCurrentTest() as buffer:
                print(f"[{name}] start")
                await asyncio.sleep(delay)
                print(f"[{name}] end")
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
                    print(f"[{name}] step {step}")
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
