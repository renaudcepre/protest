import asyncio

from protest.core.session import ProTestSession

session = ProTestSession(concurrency=3)


@session.test()
def test_passing_with_logs():
    print("This log will be captured but NOT shown (test passes)")
    print("Multiple lines work too")
    assert True


@session.test()
def test_failing_with_logs():
    print("Step 1: Preparing data...")
    print("Step 2: Processing...")
    print("Step 3: About to fail!")
    assert False, "Intentional failure to demo log capture"


@session.test()
async def test_async_with_logs():
    print("Async test starting...")
    await asyncio.sleep(0.01)
    print("Async test done!")
    assert True


@session.test()
async def test_parallel_isolation_a():
    print("[TEST A] Starting")
    await asyncio.sleep(0.05)
    print("[TEST A] Middle")
    await asyncio.sleep(0.05)
    print("[TEST A] Done")
    assert True


@session.test()
async def test_parallel_isolation_b():
    print("[TEST B] Starting")
    await asyncio.sleep(0.03)
    print("[TEST B] Middle")
    await asyncio.sleep(0.03)
    print("[TEST B] Done")
    assert True


@session.test()
async def test_parallel_fails_with_interleaved_logs():
    print("[FAIL TEST] Step 1")
    await asyncio.sleep(0.02)
    print("[FAIL TEST] Step 2")
    await asyncio.sleep(0.02)
    print("[FAIL TEST] About to crash...")
    raise ValueError("Boom! Check that logs above are NOT mixed with other tests")
