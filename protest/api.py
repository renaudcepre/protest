"""Public API for running ProTest sessions.

This module provides the main entry points for running tests programmatically,
independent of any CLI or adapter implementation.

Example:
    from protest import ProTestSession
    from protest.api import run_session

    session = ProTestSession()

    @session.test()
    def test_example():
        assert True

    success = run_session(session)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.session import ProTestSession
    from protest.entities import TestItem


def run_session(  # noqa: PLR0913
    session: ProTestSession,
    concurrency: int | None = None,
    exitfirst: bool = False,
    last_failed: bool = False,
    cache_clear: bool = False,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    capture: bool = True,
    suite_filter: str | None = None,
    keyword_patterns: list[str] | None = None,
    log_file: bool = True,
    force_live: bool = False,
    force_no_live: bool = False,
    force_no_color: bool = False,
) -> bool:
    """Run a test session and return success status.

    This is the main entry point for running tests programmatically.

    Args:
        session: The ProTestSession to run.
        concurrency: Number of concurrent workers (None = use session default).
        exitfirst: Stop after first failure.
        last_failed: Only run tests that failed in the last run.
        cache_clear: Clear the cache before running.
        include_tags: Only run tests with these tags (OR logic).
        exclude_tags: Exclude tests with these tags.
        capture: Capture stdout/stderr during tests (default: True).
        suite_filter: Only run tests in this suite (::SuiteName syntax).
        keyword_patterns: Only run tests matching these patterns (-k flag).
        log_file: Write output to .protest/last_run.log (default: True).
        force_live: Force live display mode (--live flag).
        force_no_live: Force sequential display mode (--no-live flag).
        force_no_color: Disable colors (--no-color flag).

    Returns:
        True if all tests passed, False otherwise.
    """
    from protest.core.runner import TestRunner  # noqa: PLC0415
    from protest.reporting.factory import get_reporter  # noqa: PLC0415

    if force_live or force_no_live or force_no_color:
        reporter = get_reporter(force_live, force_no_live, force_no_color)
        session.use(reporter)

    if concurrency is not None:
        session.concurrency = concurrency
    session.exitfirst = exitfirst
    session.capture = capture
    session.configure_suite_filter(suite_filter)
    session.configure_keyword_filter(keyword_patterns)
    session.configure_tags(include_tags=include_tags, exclude_tags=exclude_tags)
    session.configure_cache(last_failed=last_failed, cache_clear=cache_clear)
    session.configure_log_file(enabled=log_file)

    runner = TestRunner(session)
    return runner.run()


def collect_tests(
    session: ProTestSession,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    suite_filter: str | None = None,
    keyword_patterns: list[str] | None = None,
) -> list[TestItem]:
    """Collect tests from a session without running them.

    Args:
        session: The ProTestSession to collect from.
        include_tags: Only include tests with these tags.
        exclude_tags: Exclude tests with these tags.
        suite_filter: Only include tests in this suite.
        keyword_patterns: Only include tests matching these patterns.

    Returns:
        List of collected TestItem objects.
    """
    import asyncio  # noqa: PLC0415

    from protest.core.collector import Collector  # noqa: PLC0415
    from protest.events.types import Event  # noqa: PLC0415

    session.configure_suite_filter(suite_filter)
    session.configure_keyword_filter(keyword_patterns)
    session.configure_tags(include_tags=include_tags, exclude_tags=exclude_tags)

    collector = Collector()
    items = collector.collect(session)
    return asyncio.run(session.events.emit_and_collect(Event.COLLECTION_FINISH, items))


def list_tags(session: ProTestSession) -> set[str]:
    """List all declared tags in a session.

    Args:
        session: The ProTestSession to inspect.

    Returns:
        Set of all tag names declared on fixtures, suites, and tests.
    """
    from protest.core.suite import ProTestSuite  # noqa: PLC0415, TC001

    all_tags: set[str] = set()

    for reg in session.fixtures:
        all_tags.update(reg.tags)

    for test_reg in session.tests:
        all_tags.update(test_reg.tags)

    def collect_from_suites(suites: list[ProTestSuite]) -> None:
        for suite in suites:
            all_tags.update(suite.tags)
            for reg in suite.fixtures:
                all_tags.update(reg.tags)
            for test_reg in suite.tests:
                all_tags.update(test_reg.tags)
            collect_from_suites(suite.suites)

    collect_from_suites(session.suites)

    return all_tags
