"""Example: Capturing subprocess output in tests.

ProTest captures Python print() and logging automatically, but subprocess
output (which writes directly to OS file descriptors) requires explicit
capture.

The recommended approach is to use the Shell helper, which provides
async-safe subprocess execution with automatic output capture.
"""

from protest import ProTestSession, ProTestSuite, Shell

session = ProTestSession()
suite = ProTestSuite("SubprocessCapture")
session.add_suite(suite)


# --- Recommended: Shell helper (async, thread-safe) ---


@suite.test()
async def test_with_shell() -> None:
    """Use Shell.run() for async-safe subprocess capture."""
    result = await Shell.run("echo 'Hello from subprocess'")

    assert result.success
    assert "Hello" in result.stdout


@suite.test()
async def test_shell_with_args_list() -> None:
    """Shell accepts command as string or list."""
    result = await Shell.run(["echo", "Using list args"])

    assert result.exit_code == 0
    assert "Using list" in result.stdout


@suite.test()
async def test_shell_run_ok() -> None:
    """Shell.run_ok() asserts success automatically."""
    result = await Shell.run_ok("echo 'Must succeed'")

    # No need to check exit_code - run_ok() already did
    assert "Must succeed" in result.stdout


@suite.test()
async def test_shell_with_timeout() -> None:
    """Shell supports timeout for long-running commands."""
    result = await Shell.run("sleep 0.1 && echo done", timeout=5.0, shell=True)

    assert result.success
    assert "done" in result.stdout


@suite.test()
async def test_shell_failure() -> None:
    """Shell captures failures cleanly (shell=True for builtins like exit)."""
    result = await Shell.run("exit 1", shell=True)

    assert not result.success
    assert result.exit_code == 1


@suite.test()
async def test_shell_stderr() -> None:
    """Shell captures both stdout and stderr."""
    result = await Shell.run("echo 'out' && echo 'err' >&2", shell=True)

    assert "out" in result.stdout
    assert "err" in result.stderr
    assert "out" in result.output  # Combined stdout + stderr


@suite.test()
async def test_failing_to_show_capture() -> None:
    """This test fails intentionally to demonstrate captured output."""
    result = await Shell.run("echo 'This output will be shown in the failure report'")

    assert False, "Intentional failure to show captured subprocess output"


# --- Alternative: sync subprocess with manual capture ---
# Use this if you need sync subprocess or specific subprocess options


import subprocess


@suite.test()
def test_sync_subprocess() -> None:
    """Sync subprocess with capture_output=True."""
    result = subprocess.run(
        ["echo", "Sync subprocess"],
        capture_output=True,
        text=True,
    )

    # Print captured output so ProTest can capture it
    if result.stdout:
        print(result.stdout, end="")

    assert result.returncode == 0
    assert "Sync" in result.stdout


# --- What NOT to do ---

# DON'T do this - output goes directly to terminal, not captured:
#
# @suite.test()
# def test_bad_example() -> None:
#     subprocess.run(["echo", "Lost output"])  # Output NOT captured!
