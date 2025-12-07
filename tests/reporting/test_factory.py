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

    def test_ci_env_returns_rich(self) -> None:
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            with patch("rich.console.Console") as mock_console:
                mock_console.return_value.is_terminal = True
                reporter = get_reporter()

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)

    def test_force_no_live_returns_rich(self) -> None:
        with patch("rich.console.Console") as mock_console:
            mock_console.return_value.is_terminal = True
            reporter = get_reporter(force_no_live=True)

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)

    def test_tty_returns_live(self) -> None:
        # Clear CI env var to test TTY behavior (CI would force RichReporter)
        env_without_ci = {k: v for k, v in os.environ.items() if k != "CI"}
        with patch.dict(os.environ, env_without_ci, clear=True):
            with patch("rich.console.Console") as mock_console:
                mock_console.return_value.is_terminal = True
                reporter = get_reporter()

        from protest.reporting.live_reporter import LiveReporter

        assert isinstance(reporter, LiveReporter)

    def test_no_tty_returns_rich(self) -> None:
        with patch("rich.console.Console") as mock_console:
            mock_console.return_value.is_terminal = False
            reporter = get_reporter()

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)

    def test_force_live_with_tty(self) -> None:
        with patch("rich.console.Console") as mock_console:
            mock_console.return_value.is_terminal = True
            reporter = get_reporter(force_live=True)

        from protest.reporting.live_reporter import LiveReporter

        assert isinstance(reporter, LiveReporter)

    def test_force_live_without_tty_returns_rich(self) -> None:
        with patch("rich.console.Console") as mock_console:
            mock_console.return_value.is_terminal = False
            reporter = get_reporter(force_live=True)

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)

    def test_force_live_bypasses_ci(self) -> None:
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            with patch("rich.console.Console") as mock_console:
                mock_console.return_value.is_terminal = True
                reporter = get_reporter(force_live=True)

        from protest.reporting.live_reporter import LiveReporter

        assert isinstance(reporter, LiveReporter)

    def test_priority_no_color_over_force_live(self) -> None:
        reporter = get_reporter(force_live=True, force_no_color=True)
        assert isinstance(reporter, AsciiReporter)

    def test_priority_force_no_live_over_force_live(self) -> None:
        with patch("rich.console.Console") as mock_console:
            mock_console.return_value.is_terminal = True
            reporter = get_reporter(force_live=True, force_no_live=True)

        from protest.reporting.rich_reporter import RichReporter

        assert isinstance(reporter, RichReporter)
