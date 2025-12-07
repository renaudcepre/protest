"""Reporter factory with environment and flag detection."""

import os

from protest.plugin import PluginBase


def get_reporter(
    force_live: bool = False,
    force_no_live: bool = False,
    force_no_color: bool = False,
) -> PluginBase:
    """Select the best reporter based on environment and flags."""
    if force_no_color or os.environ.get("NO_COLOR"):
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    if os.environ.get("TERM") == "dumb":
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    try:
        from rich.console import Console  # type: ignore[import-not-found]

        console = Console()
    except ImportError:
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    if force_no_live:
        from protest.reporting.rich_reporter import RichReporter

        return RichReporter()

    if force_live and console.is_terminal:
        from protest.reporting.live_reporter import LiveReporter

        return LiveReporter()

    if os.environ.get("CI"):
        from protest.reporting.rich_reporter import RichReporter

        return RichReporter()

    if console.is_terminal:
        from protest.reporting.live_reporter import LiveReporter

        return LiveReporter()

    from protest.reporting.rich_reporter import RichReporter

    return RichReporter()
