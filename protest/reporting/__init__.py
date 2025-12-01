import importlib.util

from protest.reporting.ascii import AsciiReporter

__all__ = ["AsciiReporter"]

if importlib.util.find_spec("rich"):
    from protest.reporting.rich_reporter import RichReporter

    __all__ += ["RichReporter"]
