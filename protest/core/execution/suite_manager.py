"""Suite lifecycle management."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from protest.entities import SuitePath, SuiteResult, SuiteSetupInfo, SuiteStartInfo
from protest.events.types import Event
from protest.execution.capture import (
    set_session_setup_capture,
    set_session_teardown_capture,
)

if TYPE_CHECKING:
    from protest.core.session import ProTestSession


class SuiteManager:
    """Manages suite lifecycle: lazy initialization and teardown."""

    def __init__(self, session: ProTestSession) -> None:
        self._session = session
        self._started_suites: set[SuitePath] = set()
        self._suite_start_times: dict[SuitePath, float] = {}
        self._suite_setup_durations: dict[SuitePath, float] = {}
        self._suite_teardown_durations: dict[SuitePath, float] = {}
        self._lock = asyncio.Lock()

    @property
    def started_suites(self) -> set[SuitePath]:
        """Return the set of started suite paths."""
        return self._started_suites.copy()

    def reset(self) -> None:
        """Reset state for a new run."""
        self._started_suites = set()
        self._suite_start_times = {}
        self._suite_setup_durations = {}
        self._suite_teardown_durations = {}

    async def ensure_hierarchy_started(self, suite_path: SuitePath) -> None:
        """Ensure suite and all parent suites are started with autouse resolved."""
        for ancestor in suite_path.ancestors():
            if ancestor in self._started_suites:
                continue
            async with self._lock:
                if ancestor in self._started_suites:
                    continue
                self._suite_start_times[ancestor] = time.perf_counter()
                await self._session.events.emit(
                    Event.SUITE_START, SuiteStartInfo(name=ancestor)
                )
                suite_setup_start = time.perf_counter()
                set_session_setup_capture(True)
                try:
                    await self._session.resolver.resolve_suite_autouse(ancestor)
                finally:
                    set_session_setup_capture(False)
                suite_setup_duration = time.perf_counter() - suite_setup_start
                self._suite_setup_durations[ancestor] = suite_setup_duration
                await self._session.events.emit(
                    Event.SUITE_SETUP_DONE,
                    SuiteSetupInfo(name=ancestor, duration=suite_setup_duration),
                )
                self._started_suites.add(ancestor)

    async def teardown(self, suite_path: SuitePath) -> None:
        """Teardown suite fixtures after all its tests complete."""
        await self._session.events.emit(Event.SUITE_TEARDOWN_START, suite_path)
        teardown_start = time.perf_counter()
        set_session_teardown_capture(True)
        try:
            await self._session.resolver.teardown_suite(suite_path)
        finally:
            set_session_teardown_capture(False)
            self._suite_teardown_durations[suite_path] = (
                time.perf_counter() - teardown_start
            )

    def build_result(self, suite_path: SuitePath) -> SuiteResult:
        """Build SuiteResult with recorded durations."""
        suite_start = self._suite_start_times.get(suite_path, 0)
        suite_duration = time.perf_counter() - suite_start if suite_start else 0
        setup_duration = self._suite_setup_durations.get(suite_path, 0)
        teardown_duration = self._suite_teardown_durations.get(suite_path, 0)
        return SuiteResult(
            name=suite_path,
            duration=suite_duration,
            setup_duration=setup_duration,
            teardown_duration=teardown_duration,
        )
