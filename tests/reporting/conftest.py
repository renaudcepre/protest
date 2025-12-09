from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from protest.reporting.ctrf import CTRFReporter

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def ctrf_output_path(tmp_path: Path) -> Path:
    """Return the path for CTRF report output."""
    return tmp_path / "ctrf-report.json"


@pytest.fixture
def ctrf_reporter(ctrf_output_path: Path) -> CTRFReporter:
    """Create a CTRFReporter with temporary output path."""
    return CTRFReporter(output_path=ctrf_output_path)


@pytest.fixture
def read_ctrf_report(ctrf_output_path: Path) -> Any:
    """Factory fixture to read the CTRF report as JSON."""

    def _read() -> dict[str, Any]:
        return json.loads(ctrf_output_path.read_text())

    return _read
