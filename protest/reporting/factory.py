"""Reporter factory with environment detection."""

import os

from protest.plugin import PluginBase


def get_reporter(force_no_color: bool = False) -> PluginBase:
    """Select the best reporter based on environment."""
    if force_no_color or os.environ.get("NO_COLOR"):
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    if os.environ.get("TERM") == "dumb":
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    try:
        from rich.console import Console

        Console()
    except ImportError:
        from protest.reporting.ascii import AsciiReporter

        return AsciiReporter()

    from protest.reporting.rich_reporter import RichReporter

    return RichReporter()
