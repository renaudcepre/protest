"""Cache plugin for --lf (last-failed) and --cache-clear functionality."""

from __future__ import annotations

from argparse import ArgumentParser
from typing import TYPE_CHECKING

from typing_extensions import Self

from protest.plugin import PluginBase, PluginContext

if TYPE_CHECKING:
    from protest.cache.storage import CacheStorage
    from protest.core.session import ProTestSession
    from protest.entities import SessionResult, TestItem, TestResult


class CachePlugin(PluginBase):
    """Plugin that caches test results and provides --lf filtering."""

    name = "cache"
    description = "Test result caching with --lf support"

    def __init__(self, last_failed: bool = False, cache_clear: bool = False) -> None:
        self._last_failed = last_failed
        self._cache_clear = cache_clear
        self._cache: CacheStorage | None = None

    @classmethod
    def add_cli_options(cls, parser: ArgumentParser) -> None:
        group = parser.add_argument_group(f"{cls.name} - {cls.description}")
        group.add_argument(
            "--lf",
            "--last-failed",
            dest="last_failed",
            action="store_true",
            help="Re-run only failed tests from last run",
        )
        group.add_argument(
            "--cache-clear",
            dest="cache_clear",
            action="store_true",
            help="Clear cache before run",
        )

    @classmethod
    def activate(cls, ctx: PluginContext) -> Self:
        return cls(
            last_failed=ctx.get("last_failed", False),
            cache_clear=ctx.get("cache_clear", False),
        )

    def setup(self, session: ProTestSession) -> None:
        self._cache = session.cache
        if self._cache_clear:
            self._cache.clear()
        else:
            self._cache.load()

    def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
        """Filter tests based on --lf flag."""
        if self._last_failed and self._cache is not None:
            return self._filter_last_failed(items)
        return items

    def on_test_pass(self, result: TestResult) -> None:
        if self._cache is not None:
            self._cache.set_result(result.node_id, "passed", result.duration)

    def on_test_fail(self, result: TestResult) -> None:
        if self._cache is not None:
            status = "error" if result.is_fixture_error else "failed"
            self._cache.set_result(result.node_id, status, result.duration)

    def on_session_end(self, result: SessionResult) -> None:
        if self._cache is not None:
            self._cache.save()

    def _filter_last_failed(self, items: list[TestItem]) -> list[TestItem]:
        """Keep only tests that failed in the last run.

        If no failed tests exist in cache, returns all items.
        If failed tests exist but none match current items, returns empty list.
        """
        if self._cache is None:
            raise RuntimeError(
                "CachePlugin improperly configured: setup() must be called before "
                "filtering. This indicates a bug in the plugin lifecycle."
            )
        failed_ids = self._cache.get_failed_node_ids()
        if not failed_ids:
            return items
        return [item for item in items if item.node_id in failed_ids]
