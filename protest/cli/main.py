from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.entities import TestItem

HELP_EPILOG = """
Examples:
  protest run demo:session              Run all tests
  protest run demo:session::API         Run tests in API suite only
  protest run demo:session -k login     Run tests matching 'login'
  protest run demo:session -n 4         Run with 4 concurrent workers
  protest run demo:session --lf         Re-run only failed tests
  protest run demo:session --collect-only   List tests without running
  protest run demo:session --tag slow   Run tests with 'slow' tag
  protest run demo:session -s           Disable capture (show print output)
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
        _list_tags(args.target, app_dir=args.app_dir, recursive=args.recursive)


def _list_tags(target: str, app_dir: str, recursive: bool = False) -> None:
    """List all tags in a session."""
    from protest.api import collect_tests, list_tags
    from protest.loader import LoadError, load_session

    try:
        session = load_session(target, app_dir)
    except LoadError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if recursive:
        items = collect_tests(session)
        _print_tags_recursive(items)
    else:
        tags = list_tags(session)
        _print_tags_summary(tags)


def _print_tags_summary(tags: set[str]) -> None:
    """Print summary of all declared tags."""
    for tag in sorted(tags):
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
    parser.add_argument(
        "-s",
        "--no-capture",
        dest="no_capture",
        action="store_true",
        help="Disable stdout/stderr capture (show print output)",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        dest="keywords",
        action="append",
        default=[],
        help="Run only tests matching pattern (substring, can be used multiple times, OR logic)",
    )

    args = parser.parse_args(sys.argv[2:])

    run_tests(
        args.target,
        app_dir=args.app_dir,
        concurrency=args.concurrency,
        last_failed=args.last_failed,
        cache_clear=args.cache_clear,
        collect_only=args.collect_only,
        include_tags=set(args.tags) if args.tags else None,
        exclude_tags=set(args.exclude_tags) if args.exclude_tags else None,
        exitfirst=args.exitfirst,
        capture=not args.no_capture,
        keywords=args.keywords if args.keywords else None,
    )


def run_tests(  # noqa: PLR0913
    target: str,
    app_dir: str = ".",
    concurrency: int = 1,
    last_failed: bool = False,
    cache_clear: bool = False,
    collect_only: bool = False,
    include_tags: set[str] | None = None,
    exclude_tags: set[str] | None = None,
    exitfirst: bool = False,
    capture: bool = True,
    keywords: list[str] | None = None,
) -> None:
    from protest.api import collect_tests, run_session
    from protest.loader import LoadError, load_session, parse_target

    session_target, suite_filter = parse_target(target)

    try:
        session = load_session(session_target, app_dir)
    except LoadError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if collect_only:
        items = collect_tests(
            session,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            suite_filter=suite_filter,
            keyword_patterns=keywords,
        )
        print(f"Collected {len(items)} test(s):\n")
        for item in items:
            print(f"  {item.node_id}")
        sys.exit(0)

    success = run_session(
        session,
        concurrency=concurrency,
        exitfirst=exitfirst,
        last_failed=last_failed,
        cache_clear=cache_clear,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
        capture=capture,
        suite_filter=suite_filter,
        keyword_patterns=keywords,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
