"""Custom plugins for Yorkshire tests - because dogs have opinions too."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import Self

from protest.plugin import PluginBase, PluginContext

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from protest.entities import TestResult


class BarkPlugin(PluginBase):
    """Barks when tests fail. Good boy."""

    name = "bark"
    description = "Vocal feedback for Yorkshire terriers"

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        group = parser.add_argument_group(f"{cls.name} - {cls.description}")
        group.add_argument(
            "--bark",
            dest="bark_enabled",
            action="store_true",
            help="WOOF! when tests fail (recommended for debugging)",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self | None:
        if not ctx.get("bark_enabled", False):
            return None
        return cls(enabled=True)

    def on_test_fail(self, result: TestResult) -> None:
        if self._enabled:
            print(f"WOOF! WOOF! Bad test! ({result.node_id})")  # noqa: T201 - intentional plugin output
