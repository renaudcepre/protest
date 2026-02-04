"""Test that 3x Ctrl+C exits cleanly even with blocked worker threads.

This is a regression test for the deadlock issue where:
1. Workers get blocked in C code (e.g., gRPC on closed client)
2. User sends 3x Ctrl+C
3. Process hangs in threading._shutdown() waiting for blocked workers

The fix uses a watchdog thread that calls os._exit() on 3rd Ctrl+C.
"""

import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

BLOCKING_TEST_MODULE = Path(__file__).parent / "test_blocking.py"


class TestBlockedThreadsExit:
    """E2E test: process exits within timeout after 3x SIGINT."""

    @pytest.mark.skipif(
        not BLOCKING_TEST_MODULE.exists(),
        reason="test_blocking.py not found in repo root",
    )
    def test_triple_sigint_exits_cleanly(self) -> None:
        """Given blocked workers, when 3x SIGINT sent, then process exits quickly.

        Without watchdog fix: process hangs in threading._shutdown()
        With watchdog fix: os._exit(130) terminates immediately
        """
        protest_bin = Path(sys.executable).parent / "protest"
        proc = subprocess.Popen(
            [
                str(protest_bin),
                "run",
                "test_blocking:session",
                "-n",
                "3",
                "--no-capture",
            ],
            cwd=BLOCKING_TEST_MODULE.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # Wait for workers to block
        time.sleep(2)

        # Send 3x SIGINT
        for _ in range(3):
            if proc.poll() is not None:
                break
            proc.send_signal(signal.SIGINT)
            time.sleep(0.3)

        # Should exit within 2s (not stuck in threading._shutdown)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Process stuck after 3x SIGINT - watchdog not working")

        assert proc.returncode in (130, -2, 1, 0)
