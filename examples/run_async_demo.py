from protest.core.runner import TestRunner
from examples.demo_async import session

def main():
    print("Running Async Demo...")
    runner = TestRunner(session)
    success = runner.run()
    if not success:
        # Exit with a non-zero code to indicate failure, useful for CI
        exit(1)

if __name__ == "__main__":
    main()
