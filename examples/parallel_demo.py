"""Demo of parallel test execution - shows 10x speedup with -n 10."""

import asyncio
import time

from protest import ProTestSession, ProTestSuite


session = ProTestSession(default_reporter=True, default_cache=False)

slow_suite = ProTestSuite("SlowTests")


@slow_suite.test()
async def test_async_slow_1():
    """Async test that takes 500ms."""
    await asyncio.sleep(0.5)
    assert True


@slow_suite.test()
async def test_async_slow_2():
    await asyncio.sleep(0.5)
    assert True


@slow_suite.test()
async def test_async_slow_3():
    await asyncio.sleep(0.5)
    assert True


@slow_suite.test()
async def test_async_slow_4():
    await asyncio.sleep(0.5)
    assert True


@slow_suite.test()
async def test_async_slow_5():
    await asyncio.sleep(0.5)
    assert True


@slow_suite.test()
def test_sync_slow_1():
    """Sync test that takes 500ms."""
    time.sleep(0.5)
    assert True


@slow_suite.test()
def test_sync_slow_2():
    time.sleep(0.5)
    assert True


@slow_suite.test()
def test_sync_slow_3():
    time.sleep(0.5)
    assert True


@slow_suite.test()
def test_sync_slow_4():
    time.sleep(0.5)
    assert True


@slow_suite.test()
def test_sync_slow_5():
    time.sleep(0.5)
    assert True


session.add_suite(slow_suite)


if __name__ == "__main__":
    print("10 tests x 500ms each = 5s sequential")
    print()
    print("Try:")
    print("  protest run parallel_demo:session --app-dir examples        # ~5s")
    print("  protest run parallel_demo:session --app-dir examples -n 10  # ~0.5s")