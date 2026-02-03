from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.entities import SuitePath, TestItem


@dataclass
class SuiteTracker:
    """Track test completion per suite for cross-suite parallelism."""

    _counts: dict[SuitePath | None, int] = field(default_factory=dict)
    _completed: dict[SuitePath | None, int] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def from_items(cls, items: list[TestItem]) -> SuiteTracker:
        """Build tracker from collected test items.

        Counts include descendant tests: a parent suite's count includes
        all tests from child suites, ensuring proper teardown ordering.
        Parent suites only complete when ALL descendant tests are done.
        """
        tracker = cls()
        for item in items:
            # Walk up the suite hierarchy, counting for each ancestor
            suite = item.suite
            while suite:
                suite_path = suite.full_path
                tracker._counts[suite_path] = tracker._counts.get(suite_path, 0) + 1
                if suite_path not in tracker._completed:
                    tracker._completed[suite_path] = 0
                suite = suite._parent_suite

            # Also track standalone tests (no suite)
            if item.suite is None:
                tracker._counts[None] = tracker._counts.get(None, 0) + 1
                if None not in tracker._completed:
                    tracker._completed[None] = 0

        return tracker

    async def mark_completed(self, suite_path: SuitePath | None) -> bool:
        """Mark one test completed. Returns True if suite is fully done."""
        async with self._lock:
            self._completed[suite_path] = self._completed.get(suite_path, 0) + 1
            return self._completed[suite_path] >= self._counts.get(suite_path, 0)
