"""Example: Built-in fixtures (tmp_path, caplog, mocker).

ProTest provides ready-to-use fixtures for common testing needs.
No setup required - just import and use with Annotated[Type, Use(fixture)].
"""

import logging
from pathlib import Path
from typing import Annotated

from protest import Mocker, ProTestSession, ProTestSuite, Use, caplog, mocker, tmp_path
from protest.entities import LogCapture

session = ProTestSession()
suite = ProTestSuite("Builtins")
session.add_suite(suite)


# =============================================================================
# tmp_path - Temporary directory with automatic cleanup
# =============================================================================


@suite.test()
def test_tmp_path_basic(tmp: Annotated[Path, Use(tmp_path)]) -> None:
    """tmp_path provides a unique temporary directory."""
    assert tmp.is_dir()

    # Create and read files
    test_file = tmp / "data.txt"
    test_file.write_text("hello world")
    assert test_file.read_text() == "hello world"


@suite.test()
def test_tmp_path_nested(tmp: Annotated[Path, Use(tmp_path)]) -> None:
    """Create nested directory structures."""
    nested = tmp / "a" / "b" / "c"
    nested.mkdir(parents=True)

    config = nested / "config.json"
    config.write_text('{"key": "value"}')

    assert config.exists()
    # Directory is automatically cleaned up after test


# =============================================================================
# caplog - Capture log records
# =============================================================================


@suite.test()
def test_caplog_basic(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """caplog captures log messages during the test."""
    logging.info("Starting operation")
    logging.warning("Something suspicious")
    logging.error("Operation failed")

    expected_count = 3
    assert len(logs.records) == expected_count
    assert "suspicious" in logs.text


@suite.test()
def test_caplog_filter_level(logs: Annotated[LogCapture, Use(caplog)]) -> None:
    """Filter logs by level."""
    logging.debug("Debug message")
    logging.info("Info message")
    logging.warning("Warning message")
    logging.error("Error message")

    warnings_and_above = logs.at_level("WARNING")
    expected_warnings = 2
    assert len(warnings_and_above) == expected_warnings


# =============================================================================
# mocker - Patching and mocking
# =============================================================================


def external_api_call() -> str:
    """Simulate an external API call."""
    raise NotImplementedError("Would call external service")


def process_data() -> str:
    """Process data using external API."""
    return external_api_call()


@suite.test()
def test_mocker_patch(m: Annotated[Mocker, Use(mocker)]) -> None:
    """Patch functions to control their behavior."""
    # Patch using __name__ for portability
    mock_api = m.patch(f"{__name__}.external_api_call")
    mock_api.return_value = "mocked response"

    result = process_data()

    assert result == "mocked response"
    mock_api.assert_called_once()


class Calculator:
    """Simple class for spy example."""

    def add(self, a: int, b: int) -> int:
        return a + b


@suite.test()
def test_mocker_spy(m: Annotated[Mocker, Use(mocker)]) -> None:
    """Spy on real methods to track calls while keeping real behavior."""
    calc = Calculator()
    spy = m.spy(calc, "add")

    a, b = 2, 3
    result = calc.add(a, b)

    expected = 5
    assert result == expected  # Real method was called
    spy.assert_called_once_with(a, b)


@suite.test()
def test_mocker_stub(m: Annotated[Mocker, Use(mocker)]) -> None:
    """Create stub callables for callbacks."""
    callback = m.stub("on_complete")
    callback.return_value = "done"

    # Simulate code that calls the callback
    result = callback("arg1", key="value")

    assert result == "done"
    callback.assert_called_once_with("arg1", key="value")


# =============================================================================
# Combining builtins
# =============================================================================


@suite.test()
def test_combined_builtins(
    tmp: Annotated[Path, Use(tmp_path)],
    logs: Annotated[LogCapture, Use(caplog)],
    m: Annotated[Mocker, Use(mocker)],
) -> None:
    """Use multiple builtins together."""
    # Mock file processing
    mock_process = m.stub("file_processor")
    mock_process.return_value = True

    # Create test file
    data_file = tmp / "input.txt"
    data_file.write_text("test data")

    # Simulate processing
    logging.info(f"Processing {data_file}")
    result = mock_process(data_file)
    logging.info("Processing complete")

    assert result is True
    expected_logs = 2
    assert len(logs.records) == expected_logs
    mock_process.assert_called_once_with(data_file)
