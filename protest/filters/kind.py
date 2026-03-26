"""KindFilterPlugin — filters tests by suite kind (test/eval)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from protest.plugin import PluginBase

if TYPE_CHECKING:
    from protest.entities import TestItem
    from protest.plugin import PluginContext


class KindFilterPlugin(PluginBase):
    """Filters collected tests by suite kind ('test' or 'eval')."""

    name = "kind-filter"
    description = "Filter by suite kind"

    def __init__(self, kind: str) -> None:
        self._kind = kind

    @classmethod
    def activate(cls, ctx: PluginContext) -> KindFilterPlugin | None:
        kind = ctx.get("kind_filter")
        if kind:
            return cls(kind=kind)
        return None

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        return [item for item in items if self._matches(item)]

    def _matches(self, item: TestItem) -> bool:
        if item.suite is None:
            return self._kind == "test"
        return item.suite.kind == self._kind
