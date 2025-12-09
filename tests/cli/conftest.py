from __future__ import annotations

import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from protest.cli.main import main

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str = ""
    _stdout_capture: StringIO = field(default_factory=StringIO, repr=False)

    def assert_success(self) -> None:
        assert self.exit_code == 0, (
            f"Expected success, got exit code {self.exit_code}\nstderr: {self.stderr}\nstdout: {self.stdout}"
        )

    def assert_failure(self) -> None:
        assert self.exit_code == 1, (
            f"Expected failure (exit code 1), got {self.exit_code}\nstdout: {self.stdout}"
        )

    def assert_output_contains(self, text: str) -> None:
        assert text in self.stdout, f"'{text}' not found in output:\n{self.stdout}"

    def assert_stderr_contains(self, text: str) -> None:
        assert text in self.stderr, f"'{text}' not found in stderr:\n{self.stderr}"


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def run_protest(fixtures_dir: Path) -> Callable[..., CLIResult]:
    def _run(*args: str, app_dir: Path | None = None) -> CLIResult:
        effective_app_dir = str(app_dir or fixtures_dir)

        original_argv = sys.argv.copy()
        original_path = sys.path.copy()

        modules_before = set(sys.modules.keys())

        stdout_capture = StringIO()
        stderr_capture = StringIO()

        sys.argv = ["protest", *args]

        if effective_app_dir not in sys.path:
            sys.path.insert(0, effective_app_dir)

        exit_code = 0
        try:
            with (
                patch("sys.stdout", stdout_capture),
                patch("sys.stderr", stderr_capture),
            ):
                main()
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 1
        finally:
            sys.argv = original_argv
            sys.path = original_path

            modules_to_remove = set(sys.modules.keys()) - modules_before
            for mod in modules_to_remove:
                del sys.modules[mod]

        return CLIResult(
            exit_code=exit_code,
            stdout=stdout_capture.getvalue(),
            stderr=stderr_capture.getvalue(),
        )

    return _run
