from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.suite import ProTestSuite
    from protest.entities import TestItem

HELP_EPILOG = """
Examples:
  protest run demo:session              Run all tests
  protest run demo:session -n 4         Run with 4 concurrent workers
  protest run demo:session --lf         Re-run only failed tests
  protest run demo:session --collect-only   List tests without running
  protest run demo:session --tag slow   Run tests with 'slow' tag
  protest tags list demo:session        List all available tags
"""


def _handle_tags_command() -> None:
    """Handle 'protest tags' subcommand."""
    parser = argparse.ArgumentParser(
        prog="protest tags",
        description="Tag inspection commands",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    list_parser = subparsers.add_parser("list", help="List all available tags")
    list_parser.add_argument(
        "target",
        help="Module and session: 'module:session' (e.g., 'demo:session')",
    )
    list_parser.add_argument(
        "--app-dir",
        default=".",
        help="Look for module in this directory (default: .)",
    )
    list_parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Show effective tags per test (including inherited from fixtures)",
    )

    args = parser.parse_args(sys.argv[2:])

    if args.subcommand == "list":
        sys.path.insert(0, args.app_dir)
        _list_tags(args.target, recursive=args.recursive)


def _list_tags(target: str, recursive: bool = False) -> None:
    """List all tags in a session."""
    if ":" not in target:
        print(f"Error: Invalid format '{target}'. Use 'module:session'")
        sys.exit(1)

    module_path, session_name = target.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        print(f"Error: Cannot import module '{module_path}': {exc}")
        sys.exit(1)

    session = getattr(module, session_name, None)
    if session is None:
        print(f"Error: No '{session_name}' found in module '{module_path}'")
        sys.exit(1)

    from protest.core.collector import Collector
    from protest.core.session import ProTestSession

    if not isinstance(session, ProTestSession):
        print(f"Error: '{session_name}' is not a ProTestSession")
        sys.exit(1)

    collector = Collector()
    items = collector.collect(session)

    if recursive:
        _print_tags_recursive(items)
    else:
        _print_tags_summary(items, session, collector)


def _print_tags_summary(
    items: list[TestItem], session: object, collector: object
) -> None:
    """Print summary of all declared tags."""
    from protest.core.collector import Collector
    from protest.core.session import ProTestSession

    assert isinstance(session, ProTestSession)
    assert isinstance(collector, Collector)

    all_tags: set[str] = set()

    for reg in session.fixtures:
        all_tags.update(reg.tags)

    def collect_suite_tags(suites: list[ProTestSuite]) -> None:
        for suite in suites:
            all_tags.update(suite.tags)
            for reg in suite.fixtures:
                all_tags.update(reg.tags)
            collect_suite_tags(suite.suites)

    collect_suite_tags(session.suites)

    for test_reg in session.tests:
        all_tags.update(test_reg.tags)

    def collect_suite_test_tags(suites: list[ProTestSuite]) -> None:
        for suite in suites:
            for test_reg in suite.tests:
                all_tags.update(test_reg.tags)
            collect_suite_test_tags(suite.suites)

    collect_suite_test_tags(session.suites)

    for tag in sorted(all_tags):
        print(tag)


def _print_tags_recursive(items: list[TestItem]) -> None:
    """Print effective tags per test."""
    if not items:
        print("No tests found.")
        return

    print(f"Effective tags for {len(items)} test(s):\n")
    for item in items:
        tags_str = ", ".join(sorted(item.tags)) if item.tags else "(none)"
        print(f"  {item.node_id}")
        print(f"    tags: {tags_str}\n")


def main() -> None:
    if len(sys.argv) < 2:
        _print_help()
        return

    command = sys.argv[1]

    if command == "tags":
        _handle_tags_command()
        return

    if command == "run":
        _handle_run_command()
        return

    print(f"Error: Unknown command '{command}'. Use 'run' or 'tags'.")
    sys.exit(1)


def _print_help() -> None:
    """Print main help."""
    print("ProTest - Async-first Python test framework\n")
    print("Commands:")
    print("  run    Run tests")
    print("  tags   Tag inspection commands")
    print(HELP_EPILOG)


def _handle_run_command() -> None:
    """Handle 'protest run' subcommand."""
    parser = argparse.ArgumentParser(
        prog="protest run",
        description="Run tests",
    )
    parser.add_argument(
        "target",
        help="Module and session: 'module:session' (e.g., 'demo:session')",
    )
    parser.add_argument(
        "--app-dir",
        default=".",
        help="Look for module in this directory (default: .)",
    )
    parser.add_argument(
        "-n",
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent tests (default: 1)",
    )
    parser.add_argument(
        "--lf",
        "--last-failed",
        dest="last_failed",
        action="store_true",
        help="Re-run only failed tests from last run",
    )
    parser.add_argument(
        "--cache-clear",
        dest="cache_clear",
        action="store_true",
        help="Clear cache before run",
    )
    parser.add_argument(
        "--collect-only",
        dest="collect_only",
        action="store_true",
        help="Only collect and list tests, don't run them",
    )
    parser.add_argument(
        "-t",
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Run only tests with this tag (can be used multiple times, OR logic)",
    )
    parser.add_argument(
        "--no-tag",
        dest="exclude_tags",
        action="append",
        default=[],
        help="Exclude tests with this tag (can be used multiple times)",
    )
    parser.add_argument(
        "-x",
        "--exitfirst",
        action="store_true",
        help="Exit after first failed test",
    )

    args = parser.parse_args(sys.argv[2:])

    sys.path.insert(0, args.app_dir)
    run_tests(
        args.target,
        args.concurrency,
        last_failed=args.last_failed,
        cache_clear=args.cache_clear,
        collect_only=args.collect_only,
        include_tags=set(args.tags),
        exclude_tags=set(args.exclude_tags),
        exitfirst=args.exitfirst,
    )


def run_tests(  # noqa: PLR0913
    target: str,
    concurrency: int = 1,
    last_failed: bool = False,
    cache_clear: bool = False,
    collect_only: bool = False,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    exitfirst: bool = False,
) -> None:
    if ":" not in target:
        print(f"Error: Invalid format '{target}'. Use 'module:session'")
        sys.exit(1)

    module_path, session_name = target.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        print(f"Error: Cannot import module '{module_path}': {exc}")
        sys.exit(1)

    session = getattr(module, session_name, None)
    if session is None:
        print(f"Error: No '{session_name}' found in module '{module_path}'")
        sys.exit(1)

    from protest.core.collector import Collector
    from protest.core.runner import TestRunner
    from protest.core.session import ProTestSession

    if not isinstance(session, ProTestSession):
        print(f"Error: '{session_name}' is not a ProTestSession")
        sys.exit(1)

    session.concurrency = concurrency
    session.exitfirst = exitfirst
    session.configure_cache(last_failed=last_failed, cache_clear=cache_clear)

    session.configure_tags(include_tags=include_tags, exclude_tags=exclude_tags)

    if collect_only:
        from protest.events.types import Event

        collector = Collector()
        items = collector.collect(session)
        items = asyncio.run(
            session.events.emit_and_collect(Event.COLLECTION_FINISH, items)
        )
        print(f"Collected {len(items)} test(s):\n")
        for item in items:
            print(f"  {item.node_id}")
        sys.exit(0)

    runner = TestRunner(session)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
