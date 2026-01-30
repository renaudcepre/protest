"""Example: Capturing subprocess output in tests.

ProTest captures Python print() and logging automatically, but subprocess
output (which writes directly to OS file descriptors) requires explicit
capture using subprocess.PIPE or capture_output=True.

This example shows the recommended patterns.
"""

import subprocess

from protest import ProTestSession, ProTestSuite

session = ProTestSession()
suite = ProTestSuite("SubprocessCapture")
session.add_suite(suite)


# --- Pattern 1: capture_output=True (simplest) ---


@suite.test()
def test_with_capture_output() -> None:
    """Use capture_output=True and print the result."""
    result = subprocess.run(
        ["echo", "Hello from subprocess"],
        capture_output=True,
        text=True,
    )

    # Print captured output - now it's in the test's captured output
    if result.stdout:
        print(result.stdout, end="")

    assert result.returncode == 0
    assert "Hello" in result.stdout


# --- Pattern 2: check_output for simple cases ---


@suite.test()
def test_with_check_output() -> None:
    """Use check_output for commands that should succeed."""
    output = subprocess.check_output(
        ["echo", "Another subprocess"],
        text=True,
    )

    print(output, end="")

    assert "Another" in output


# --- Pattern 3: Helper function for repeated use ---


def run_and_capture(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    """Run a subprocess and print its output for capture."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result


@suite.test()
def test_with_helper() -> None:
    """Use a helper function for cleaner code."""
    result = run_and_capture(["echo", "Using helper"])

    assert result.returncode == 0


# --- What NOT to do ---

# DON'T do this - output goes directly to terminal, not captured:
#
# @suite.test()
# def test_bad_example() -> None:
#     subprocess.run(["echo", "Lost output"])  # Output NOT captured!
#
# DON'T do this either - stdout=sys.stdout bypasses capture:
#
# @suite.test()
# def test_also_bad() -> None:
#     subprocess.run(["echo", "Also lost"], stdout=sys.stdout)
