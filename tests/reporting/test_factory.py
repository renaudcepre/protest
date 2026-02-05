"""Tests for the reporter factory."""

from __future__ import annotations

import os
from unittest.mock import patch

from protest.reporting.ascii import AsciiReporter
from protest.reporting.factory import get_reporter


class TestGetReporter:
    def test_no_color_env_returns_ascii(self) -> None:
        with patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            reporter = get_reporter()
        assert isinstance(reporter, AsciiReporter)

    def test_force_no_color_returns_ascii(self) -> None:
        reporter = get_reporter(force_no_color=True)
        assert isinstance(reporter, AsciiReporter)

    def test_term_dumb_returns_ascii(self) -> None:
        with patch.dict(os.environ, {"TERM": "dumb"}, clear=False):
            reporter = get_reporter()
        assert isinstance(reporter, AsciiReporter)

    def test_with_rich_returns_rich(self) -> None:
        with patch("rich.console.Console"):
            reporter = get_reporter()

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)

    def test_no_rich_returns_ascii(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("rich.console.Console", side_effect=ImportError("No rich")),
        ):
            reporter = get_reporter()

        assert isinstance(reporter, AsciiReporter)
