from __future__ import annotations

from typing import TYPE_CHECKING

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities import TestItem


class SuiteFilterPlugin(PluginBase):
    def __init__(self, suite_filter: str | None = None) -> None:
        self._suite_filter = suite_filter

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        if not self._suite_filter:
            return items
        return [item for item in items if self._matches_suite(item)]

    def _matches_suite(self, item: TestItem) -> bool:
        if item.suite_path is None:
            return False
        suite_lower = item.suite_path.lower()
        filter_lower = self._suite_filter.lower() if self._suite_filter else ""
        return suite_lower == filter_lower or suite_lower.startswith(
            f"{filter_lower}::"
        )
