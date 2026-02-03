import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from protest.core.suite import ProTestSuite
from protest.entities import SessionResult, SuitePath, SuiteResult, TestItem, TestResult
from protest.plugin import PluginBase
from tests.factories.test_items import make_test_item

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def test_item_factory() -> "Callable[..., TestItem]":
    """Fixture providing the make_test_item factory function."""
    return make_test_item


@dataclass
class ConcurrencyTracker:
    """Tracks concurrent test execution for validating parallelism."""

    current: int = 0
    max_seen: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def track_execution(self, delay: float = 0.05) -> None:
        """Track entering and exiting a concurrent section."""
        async with self.lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)
        await asyncio.sleep(delay)
        async with self.lock:
            self.current -= 1


def register_concurrent_tests(
    suite: ProTestSuite,
    count: int,
    tracker: ConcurrencyTracker,
    delay: float = 0.05,
) -> None:
    """Register multiple tests that track concurrent execution on a suite."""
    for idx in range(count):

        @suite.test()
        async def concurrent_test(
            tracker: ConcurrencyTracker = tracker, delay: float = delay
        ) -> None:
            await tracker.track_execution(delay)

        concurrent_test.__name__ = f"test_concurrent_{idx}"


@dataclass
class CollectedEvents:
    """Container for events collected during test execution."""

    test_passes: list[TestResult] = field(default_factory=list)
    test_fails: list[TestResult] = field(default_factory=list)
    session_results: list[SessionResult] = field(default_factory=list)
    collection_items: list[TestItem] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    suite_events: list[tuple[str, SuitePath | SuiteResult]] = field(default_factory=list)


@pytest.fixture
def event_collector() -> tuple[PluginBase, CollectedEvents]:
    """Fixture providing a plugin that collects all events during test execution.

    Returns a tuple of (plugin_instance, collected_events).
    """
    collected = CollectedEvents()

    class EventCollectorPlugin(PluginBase):
        def on_session_start(self) -> None:
            collected.events.append("session_start")

        def on_session_end(self, result: SessionResult) -> None:
            collected.session_results.append(result)
            collected.events.append("session_end")

        def on_session_complete(self, result: SessionResult) -> None:
            collected.events.append("session_complete")

        def on_test_pass(self, result: TestResult) -> None:
            collected.test_passes.append(result)

        def on_test_fail(self, result: TestResult) -> None:
            collected.test_fails.append(result)

        def on_suite_start(self, path: SuitePath) -> None:
            collected.suite_events.append(("start", path))

        def on_suite_end(self, result: SuiteResult) -> None:
            collected.suite_events.append(("end", result))

        def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
            collected.collection_items.extend(items)
            return items

    return EventCollectorPlugin(), collected
