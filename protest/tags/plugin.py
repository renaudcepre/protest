"""Tag filtering plugin for ProTest."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import Self

from protest.plugin import PluginBase, PluginContext

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from protest.entities import TestItem


class TagFilterPlugin(PluginBase):
    """Filters tests based on include/exclude tags."""

    name = "tag-filter"
    description = "Filter tests by tags"

    def __init__(
        self,
        include_tags: set[str] | None = None,
        exclude_tags: set[str] | None = None,
    ) -> None:
        self._include_tags = include_tags or set()
        self._exclude_tags = exclude_tags or set()

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        group = parser.add_argument_group(f"{cls.name} - {cls.description}")
        group.add_argument(
            "-t",
            "--tag",
            dest="tags",
            action="append",
            default=[],
            help="Run only tests with this tag (can be used multiple times, OR logic)",
        )
        group.add_argument(
            "--no-tag",
            dest="exclude_tags",
            action="append",
            default=[],
            help="Exclude tests with this tag (can be used multiple times)",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self | None:
        tags = ctx.get("tags", []) or []
        exclude_tags = ctx.get("exclude_tags", []) or []
        if not tags and not exclude_tags:
            return None
        return cls(
            include_tags=set(tags) if tags else None,
            exclude_tags=set(exclude_tags) if exclude_tags else None,
        )

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
