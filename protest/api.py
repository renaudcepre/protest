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

Note:
    This module uses lazy imports (PLC0415) to optimize startup time.
    Users importing `from protest.api import run_session` shouldn't pay
    the cost of loading the entire framework until they actually call it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.session import ProTestSession
    from protest.entities import RunResult, TestItem
    from protest.plugin import PluginContext


def run_session(  # noqa: PLR0913 - public API with many optional params
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
    force_no_color: bool = False,
    *,
    ctx: PluginContext | None = None,
) -> RunResult:
    """Run a test session and return result with success and interrupted status.

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
        force_no_color: Disable colors (--no-color flag).
        ctx: Plugin context (if provided, overrides individual params above).

    Returns:
        RunResult with success status and interrupted flag.
    """
    from protest.core.runner import (  # noqa: PLC0415 - lazy import for startup perf
        TestRunner,
    )

    # Apply session-level settings from ctx or params
    if ctx is not None:
        if ctx.get("concurrency") is not None:
            session.concurrency = ctx.get("concurrency")
        session.exitfirst = ctx.get("exitfirst", False)
        session.capture = not ctx.get("no_capture", False)
    else:
        if concurrency is not None:
            session.concurrency = concurrency
        session.exitfirst = exitfirst
        session.capture = capture

    # Register default plugins if none registered
    if not session.plugin_classes:
        session.register_default_plugins()

    # Build context from parameters if not provided
    if ctx is None:
        from protest.plugin import (  # noqa: PLC0415 - lazy import for startup perf
            PluginContext,
        )

        ctx = PluginContext(
            args={
                "last_failed": last_failed,
                "cache_clear": cache_clear,
                "tags": list(include_tags) if include_tags else [],
                "exclude_tags": list(exclude_tags) if exclude_tags else [],
                "target_suite": suite_filter,
                "keywords": keyword_patterns or [],
                "no_log_file": not log_file,
                "no_color": force_no_color,
            }
        )

    session.activate_plugins(ctx)

    runner = TestRunner(session)
    return runner.run()


def collect_tests(  # noqa: PLR0913 - public API with many optional params
    session: ProTestSession,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    suite_filter: str | None = None,
    keyword_patterns: list[str] | None = None,
    *,
    ctx: PluginContext | None = None,
) -> list[TestItem]:
    """Collect tests from a session without running them.

    Args:
        session: The ProTestSession to collect from.
        include_tags: Only include tests with these tags.
        exclude_tags: Exclude tests with these tags.
        suite_filter: Only include tests in this suite.
        keyword_patterns: Only include tests matching these patterns.
        ctx: Plugin context (if provided, overrides individual params above).

    Returns:
        List of collected TestItem objects.
    """
    # Lazy imports for startup performance - only load when function is called
    import asyncio  # noqa: PLC0415

    from protest.core.collector import Collector  # noqa: PLC0415
    from protest.events.types import Event  # noqa: PLC0415
    from protest.filters.keyword import KeywordFilterPlugin  # noqa: PLC0415
    from protest.filters.suite import SuiteFilterPlugin  # noqa: PLC0415
    from protest.plugin import PluginBase, PluginContext  # noqa: PLC0415
    from protest.tags.plugin import TagFilterPlugin  # noqa: PLC0415

    # Build context from parameters if not provided
    if ctx is None:
        ctx = PluginContext(
            args={
                "tags": list(include_tags) if include_tags else [],
                "exclude_tags": list(exclude_tags) if exclude_tags else [],
                "target_suite": suite_filter,
                "keywords": keyword_patterns or [],
            }
        )

    # Activate filter plugins
    filter_plugins: list[type[PluginBase]] = [
        TagFilterPlugin,
        SuiteFilterPlugin,
        KeywordFilterPlugin,
    ]
    for plugin_class in filter_plugins:
        instance = plugin_class.activate(ctx)
        if instance is not None:
            session.register_plugin(instance)

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
    from protest.core.suite import (  # noqa: PLC0415, TC001 - lazy import for startup perf
        ProTestSuite,
    )

    all_tags: set[str] = set()

    for fixture_reg in session.fixtures:
        all_tags.update(fixture_reg.tags)

    for test_reg in session.tests:
        all_tags.update(test_reg.tags)

    def collect_from_suites(suites: list[ProTestSuite]) -> None:
        for suite in suites:
            all_tags.update(suite.tags)
            for fixture_reg in suite.fixtures:
                all_tags.update(fixture_reg.tags)
            for test_reg in suite.tests:
                all_tags.update(test_reg.tags)
            collect_from_suites(suite.suites)

    collect_from_suites(session.suites)

    return all_tags
