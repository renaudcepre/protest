"""Log file plugin - writes logging and stdout to .protest/"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from protest.execution.capture import (
    add_log_callback,
    add_stdout_callback,
    remove_log_callback,
    remove_stdout_callback,
)
from protest.plugin import PluginBase

if TYPE_CHECKING:
    import logging

    from protest.core.session import ProTestSession
    from protest.entities import SessionResult

_MIN_NODE_ID_PARTS = 2


class LogFilePlugin(PluginBase):
    """Writes logging and stdout to .protest/ for post-mortem debugging."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or Path(".protest")
        self._log_file = self._log_dir / "last_run.log"
        self._stdout_file = self._log_dir / "last_run_stdout"
        self._log_handle: TextIO | None = None
        self._stdout_handle: TextIO | None = None

    def setup(self, session: ProTestSession) -> None:
        self._log_dir.mkdir(exist_ok=True)
        self._log_handle = open(self._log_file, "w", encoding="utf-8")  # noqa: SIM115
        self._stdout_handle = open(self._stdout_file, "w", encoding="utf-8")  # noqa: SIM115
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_log(f"# ProTest Log - {timestamp}\n\n")
        self._write_stdout(f"# ProTest Stdout - {timestamp}\n\n")

    def on_session_start(self) -> None:
        add_log_callback(self._on_log)
        add_stdout_callback(self._on_stdout)

    def _on_log(self, node_id: str, record: logging.LogRecord) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname
        message = record.getMessage()
        test_id = self._extract_test_id(node_id)
        self._write_log(f"{timestamp} [{test_id}] {level}: {message}\n")

    def _on_stdout(self, node_id: str, data: str) -> None:
        if not data.strip():
            return
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        test_id = self._extract_test_id(node_id)
        for line in data.splitlines():
            self._write_stdout(f"{timestamp} [{test_id}] {line}\n")

    def _extract_test_id(self, node_id: str) -> str:
        """Extract readable test id from full node_id."""
        parts = node_id.split("::")
        if len(parts) >= _MIN_NODE_ID_PARTS:
            return "::".join(parts[1:])
        return node_id

    def on_session_complete(self, result: SessionResult) -> None:
        remove_log_callback(self._on_log)
        remove_stdout_callback(self._on_stdout)
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        if self._stdout_handle:
            self._stdout_handle.close()
            self._stdout_handle = None

    def _write_log(self, text: str) -> None:
        if self._log_handle:
            self._log_handle.write(text)
            self._log_handle.flush()

    def _write_stdout(self, text: str) -> None:
        if self._stdout_handle:
            self._stdout_handle.write(text)
            self._stdout_handle.flush()
