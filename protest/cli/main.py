import argparse
import asyncio
import importlib
import sys
from typing import cast

HELP_EPILOG = """
Examples:
  protest demo:session              Run all tests
  protest demo:session -n 4         Run with 4 concurrent workers
  protest demo:session --lf         Re-run only failed tests
  protest demo:session --collect-only   List tests without running
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="protest",
        description="ProTest - Async-first Python test framework",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    args = parser.parse_args()

    if args.target:
        sys.path.insert(0, args.app_dir)
        run_tests(
            args.target,
            args.concurrency,
            last_failed=args.last_failed,
            cache_clear=args.cache_clear,
            collect_only=args.collect_only,
        )
    else:
        parser.print_help()


def run_tests(
    target: str,
    concurrency: int = 1,
    last_failed: bool = False,
    cache_clear: bool = False,
    collect_only: bool = False,
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

    from protest.cache.plugin import CachePlugin
    from protest.core.collector import Collector
    from protest.core.runner import TestRunner
    from protest.core.session import ProTestSession

    if not isinstance(session, ProTestSession):
        print(f"Error: '{session_name}' is not a ProTestSession")
        sys.exit(1)

    protest_session = cast("ProTestSession", session)
    protest_session.concurrency = concurrency
    protest_session.use(CachePlugin(last_failed=last_failed, cache_clear=cache_clear))

    if collect_only:
        from protest.events.types import Event

        collector = Collector()
        items = collector.collect(protest_session)
        items = asyncio.run(
            protest_session.events.emit_and_collect(Event.COLLECTION_FINISH, items)
        )
        print(f"Collected {len(items)} test(s):\n")
        for item in items:
            print(f"  {item.node_id}")
        sys.exit(0)

    runner = TestRunner(protest_session)
    success = runner.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
