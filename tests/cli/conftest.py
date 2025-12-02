from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class CLIResult:
    exit_code: int
    stdout: str
    stderr: str

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
    def _run(*args: str, app_dir: Path | None = None, timeout: int = 30) -> CLIResult:
        cmd = [sys.executable, "-m", "protest.cli.main", *args]
        effective_app_dir = app_dir or fixtures_dir
        result = subprocess.run(  # noqa: S603
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={
                **dict(__import__("os").environ),
                "PYTHONPATH": str(effective_app_dir.parent.parent.parent),
            },
            cwd=str(effective_app_dir),
            check=False,
        )
        return CLIResult(result.returncode, result.stdout, result.stderr)

    return _run
