"""Tests for LogFilePlugin - writes logging and stdout to .protest/"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from protest.entities import SessionResult

if TYPE_CHECKING:
    from pathlib import Path

from protest.reporting.log_file import LogFilePlugin


class TestLogFilePluginSetup:
    def test_creates_log_directory(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()

        plugin.setup(session)

        assert log_dir.exists()
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

    def test_creates_log_and_stdout_files(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()

        plugin.setup(session)

        assert (log_dir / "last_run.log").exists()
        assert (log_dir / "last_run_stdout").exists()
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

    def test_writes_header_on_setup(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()

        plugin.setup(session)
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        log_content = (log_dir / "last_run.log").read_text()
        stdout_content = (log_dir / "last_run_stdout").read_text()
        assert "ProTest Log" in log_content
        assert "ProTest Stdout" in stdout_content


class TestLogFilePluginCallbacks:
    def test_on_log_writes_to_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test log message",
            args=(),
            exc_info=None,
        )
        plugin._on_log("module::Suite::test_example", record)
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        log_content = (log_dir / "last_run.log").read_text()
        assert "Suite::test_example" in log_content
        assert "INFO" in log_content
        assert "Test log message" in log_content

    def test_on_stdout_writes_to_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        plugin._on_stdout("module::Suite::test_example", "Test stdout output")
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        stdout_content = (log_dir / "last_run_stdout").read_text()
        assert "Suite::test_example" in stdout_content
        assert "Test stdout output" in stdout_content

    def test_on_stdout_ignores_empty_data(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        plugin._on_stdout("module::test_example", "")
        plugin._on_stdout("module::test_example", "   ")
        plugin._on_stdout("module::test_example", "\n")
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        stdout_content = (log_dir / "last_run_stdout").read_text()
        lines = [line for line in stdout_content.splitlines() if "test_example" in line]
        assert len(lines) == 0

    def test_on_stdout_handles_multiline_data(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        plugin._on_stdout("module::test_multi", "line1\nline2\nline3")
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        stdout_content = (log_dir / "last_run_stdout").read_text()
        assert "line1" in stdout_content
        assert "line2" in stdout_content
        assert "line3" in stdout_content


class TestLogFilePluginExtractTestId:
    def test_extracts_test_id_from_node_id(self) -> None:
        plugin = LogFilePlugin()
        result = plugin._extract_test_id("module::Suite::test_name")
        assert result == "Suite::test_name"

    def test_returns_node_id_for_simple_path(self) -> None:
        plugin = LogFilePlugin()
        result = plugin._extract_test_id("test_name")
        assert result == "test_name"

    def test_extracts_nested_path(self) -> None:
        plugin = LogFilePlugin()
        result = plugin._extract_test_id("module::Parent::Child::test_name")
        assert result == "Parent::Child::test_name"


class TestLogFilePluginLifecycle:
    def test_closes_files_on_session_complete(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        assert plugin._log_handle is not None
        assert plugin._stdout_handle is not None

        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        assert plugin._log_handle is None
        assert plugin._stdout_handle is None

    def test_files_are_readable_after_complete(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Final message",
            args=(),
            exc_info=None,
        )
        plugin._on_log("module::test_final", record)
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        log_content = (log_dir / "last_run.log").read_text()
        assert "Final message" in log_content


class TestLogFilePluginTimestamps:
    def test_log_timestamp_format(self, tmp_path: Path) -> None:
        log_dir = tmp_path / ".protest"
        plugin = LogFilePlugin(log_dir=log_dir)
        session = MagicMock()
        plugin.setup(session)

        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="Timestamped",
            args=(),
            exc_info=None,
        )
        plugin._on_log("module::test_ts", record)
        plugin.on_session_complete(SessionResult(passed=0, failed=0, duration=0))

        log_content = (log_dir / "last_run.log").read_text()
        timestamp_pattern = r"\d{2}:\d{2}:\d{2}\.\d{3}"
        assert re.search(timestamp_pattern, log_content)
