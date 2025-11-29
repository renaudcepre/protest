import sys

from examples.demo_async import session
from protest.core.runner import TestRunner


def main():
    print("Running Async Demo...")
    runner = TestRunner(session)
    success = runner.run()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
