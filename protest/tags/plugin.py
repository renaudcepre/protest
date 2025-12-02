"""Tag filtering plugin for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.core.collector import TestItem


class TagFilterPlugin(PluginBase):
    """Filters tests based on include/exclude tags."""

    def __init__(
        self,
        include_tags: set[str] | None = None,
        exclude_tags: set[str] | None = None,
    ) -> None:
        self._include_tags = include_tags or set()
        self._exclude_tags = exclude_tags or set()

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        """Filter items based on tags (OR for include, exclude always applies)."""
        if not self._include_tags and not self._exclude_tags:
            return items

        filtered: list[TestItem] = []
        for item in items:
            if self._exclude_tags and item.tags & self._exclude_tags:
                continue

            if self._include_tags:
                if item.tags & self._include_tags:
                    filtered.append(item)
            else:
                filtered.append(item)

        return filtered
