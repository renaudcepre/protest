from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.entities import TestItem


@dataclass
class SuiteTracker:
    """Track test completion per suite for cross-suite parallelism."""

    _counts: dict[str | None, int] = field(default_factory=dict)
    _completed: dict[str | None, int] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    def from_items(cls, items: list[TestItem]) -> SuiteTracker:
        """Build tracker from collected test items."""
        tracker = cls()
        for item in items:
            suite_path = item.suite.full_path if item.suite else None
            tracker._counts[suite_path] = tracker._counts.get(suite_path, 0) + 1
            tracker._completed[suite_path] = 0
        return tracker

    async def mark_completed(self, suite_path: str | None) -> bool:
        """Mark one test completed. Returns True if suite is fully done."""
        async with self._lock:
            self._completed[suite_path] = self._completed.get(suite_path, 0) + 1
            return self._completed[suite_path] >= self._counts.get(suite_path, 0)
