"""Timeout demo - demonstrates test timeout feature.

Run with:
    protest run examples.basic.timeout_demo:session

To see timeout failures, try:
    protest run examples.basic.timeout_demo:session_with_failures
"""

import asyncio
import time

from protest import ProTestSession, ProTestSuite

session = ProTestSession()
api_suite = ProTestSuite("API")
session.add_suite(api_suite)


@session.test(timeout=2.0)
async def test_fast_async() -> None:
    """Async test that completes within timeout."""
    await asyncio.sleep(0.1)


@session.test(timeout=2.0)
def test_fast_sync() -> None:
    """Sync test that completes within timeout."""
    time.sleep(0.1)


@api_suite.test(timeout=1.0)
async def test_api_call() -> None:
    """Suite test with timeout."""
    await asyncio.sleep(0.1)


@session.test(xfail="Known to be slow", timeout=0.1)
async def test_expected_timeout() -> None:
    """Expected failure due to timeout - counts as xfail."""
    await asyncio.sleep(1.0)


@session.test(skip="Not ready", timeout=0.001)
async def test_skipped_with_timeout() -> None:
    """Skipped test - timeout never applies."""
    await asyncio.sleep(100)


session_with_failures = ProTestSession()


@session_with_failures.test(timeout=0.2)
async def test_slow_async() -> None:
    """Async test that exceeds timeout - will fail."""
    await asyncio.sleep(1.0)


@session_with_failures.test(timeout=0.2)
def test_slow_sync() -> None:
    """Sync test that exceeds timeout - will fail."""
    time.sleep(1.0)


if __name__ == "__main__":
    from protest import run_session

    run_session(session)
