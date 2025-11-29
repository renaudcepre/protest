import argparse
import importlib
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="protest", description="ProTest runner")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run tests")
    run_parser.add_argument(
        "target",
        help="Module and session in format 'module:session' (e.g., 'demo:session')",
    )
    run_parser.add_argument(
        "--app-dir",
        default=".",
        help="Look for module in this directory (default: current directory)",
    )
    run_parser.add_argument(
        "-n",
        "--concurrency",
        type=int,
        default=1,
        help="Number of concurrent tests (default: 1, sequential)",
    )

    args = parser.parse_args()

    if args.command == "run":
        sys.path.insert(0, args.app_dir)
        run_tests(args.target, args.concurrency)
    else:
        parser.print_help()


def run_tests(target: str, concurrency: int = 1) -> None:
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

    from protest.core.runner import TestRunner
    from protest.core.session import ProTestSession
    from protest.reporting.console import ConsoleReporter

    if not isinstance(session, ProTestSession):
        print(f"Error: '{session_name}' is not a ProTestSession")
        sys.exit(1)

    session.concurrency = concurrency
    session.use(ConsoleReporter())

    runner = TestRunner(session)
    runner.run()


if __name__ == "__main__":
    main()
