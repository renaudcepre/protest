from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import Self

from protest.plugin import PluginBase, PluginContext

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from protest.entities import TestItem


class KeywordFilterPlugin(PluginBase):
    """Filters tests by keyword pattern matching."""

    name = "keyword-filter"
    description = "Filter tests by keyword pattern"

    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = patterns or []

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        group = parser.add_argument_group(f"{cls.name} - {cls.description}")
        group.add_argument(
            "-k",
            "--keyword",
            dest="keywords",
            action="append",
            default=[],
            help="Run only tests matching pattern (substring, can be used multiple times, OR logic)",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self | None:
        keywords = ctx.get("keywords", []) or []
        if not keywords:
            return None
        return cls(patterns=keywords)

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        if not self._patterns:
            return items
        return [item for item in items if self._matches_keyword(item)]

    def _matches_keyword(self, item: TestItem) -> bool:
        searchable = item.test_name
        if item.case_ids:
            searchable = f"{searchable}[{'-'.join(item.case_ids)}]"
        return any(pattern in searchable for pattern in self._patterns)
