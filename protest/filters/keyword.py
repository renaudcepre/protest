from __future__ import annotations

from typing import TYPE_CHECKING

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities import TestItem


class KeywordFilterPlugin(PluginBase):
    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = patterns or []

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        if not self._patterns:
            return items
        return [item for item in items if self._matches_keyword(item)]

    def _matches_keyword(self, item: TestItem) -> bool:
        searchable = item.test_name
        if item.case_ids:
            searchable = f"{searchable}[{'-'.join(item.case_ids)}]"
        return any(pattern in searchable for pattern in self._patterns)
