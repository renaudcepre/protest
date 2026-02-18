from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protest.core.session import ProTestSession
    from protest.entities import TestItem
    from protest.plugin import PluginContext

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

    if command == "live":
        _handle_live_command()
        return

    print(f"Error: Unknown command '{command}'. Use 'run', 'tags', or 'live'.")
    sys.exit(1)


def _handle_live_command() -> None:
    """Handle 'protest live' subcommand - starts persistent live server."""
    parser = argparse.ArgumentParser(
        prog="protest live",
        description="Start live reporter server (keeps running for multiple test runs)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765)",
    )
    args = parser.parse_args(sys.argv[2:])

    from protest.reporting.web import run_live_server

    run_live_server(port=args.port)


def _print_help() -> None:
    """Print main help."""
    print("ProTest - Async-first Python test framework\n")
    print("Commands:")
    print("  run    Run tests")
    print("  live   Start live reporter server")
    print("  tags   Tag inspection commands")
    print(HELP_EPILOG)


def _create_base_parser() -> argparse.ArgumentParser:
    """Parser with just target and app-dir for initial loading."""
    parser = argparse.ArgumentParser(
        prog="protest run",
        description="Run tests",
        add_help=False,  # We'll add help to the full parser
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="Module and session: 'module:session' (e.g., 'demo:session')",
    )
    parser.add_argument(
        "--app-dir",
        default=".",
        help="Look for module in this directory (default: .)",
    )
    return parser


def _create_run_parser() -> argparse.ArgumentParser:
    """Base parser with core run options. Plugin options added dynamically."""
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
        "--collect-only",
        dest="collect_only",
        action="store_true",
        help="Only collect and list tests, don't run them",
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
        "-v",
        "--verbose",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity (-v for lifecycle, -vv for fixtures)",
    )
    return parser


def _handle_run_command() -> None:
    """Handle 'protest run' subcommand with two-phase parsing."""
    from protest.loader import LoadError, load_session, parse_target

    argv = sys.argv[2:]

    # Phase 1: Parse base args to get target
    base_parser = _create_base_parser()
    base_args, remaining = base_parser.parse_known_args(argv)

    # If --help in remaining and no target, show help without loading session
    if ("--help" in remaining or "-h" in remaining) and not base_args.target:
        _create_run_parser().parse_args(["--help"])
        return

    if not base_args.target:
        _create_run_parser().print_help()
        sys.exit(1)

    # Phase 2: Load session and register default plugins
    session_target, suite_filter = parse_target(base_args.target)
    try:
        session = load_session(session_target, base_args.app_dir)
    except LoadError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    session.register_default_plugins()

    # Phase 3: Build full parser with plugin options
    full_parser = _create_run_parser()
    for plugin_class in session.plugin_classes:
        plugin_class.add_cli_options(full_parser)

    # Phase 4: Full parse
    args = full_parser.parse_args(argv)

    # Phase 5: Build context
    from protest.plugin import PluginContext

    ctx = PluginContext(args={**vars(args), "target_suite": suite_filter})

    # Phase 6: Run tests (api.run_session handles plugin activation)
    run_tests(session, ctx, collect_only=args.collect_only)


def run_tests(
    session: ProTestSession,
    ctx: PluginContext,
    collect_only: bool = False,
) -> None:
    from protest.api import collect_tests, run_session

    if collect_only:
        items = collect_tests(session, ctx=ctx)
        print(f"Collected {len(items)} test(s):\n")
        for item in items:
            print(f"  {item.node_id}")
        sys.exit(0)

    result = run_session(session, ctx=ctx)
    exit_code_interrupted = 130
    if result.interrupted:
        sys.exit(exit_code_interrupted)
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
