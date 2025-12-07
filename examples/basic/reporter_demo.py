"""Demo: Reporter modes.

Run with different flags to see the difference:

    # Default (Live mode if interactive terminal)
    protest run examples.basic.reporter_demo:session -n 4

    # Force sequential mode (like CI)
    protest run examples.basic.reporter_demo:session -n 4 --no-live

    # Force ASCII mode (no colors)
    protest run examples.basic.reporter_demo:session -n 4 --no-color

    # Simulate CI environment
    CI=true protest run examples.basic.reporter_demo:session -n 4

    # Simulate NO_COLOR environment
    NO_COLOR=1 protest run examples.basic.reporter_demo:session -n 4
"""

import asyncio

from protest import ProTestSession

session = ProTestSession(concurrency=4)


@session.test()
async def test_fast():
    await asyncio.sleep(0.1)


@session.test()
async def test_medium():
    await asyncio.sleep(0.3)


@session.test()
async def test_slow():
    await asyncio.sleep(0.5)


@session.test()
async def test_very_slow():
    await asyncio.sleep(0.8)


@session.test()
async def test_another_fast():
    await asyncio.sleep(0.15)


@session.test()
async def test_fail():
    await asyncio.sleep(0.2)
    assert False, "Expected failure for demo"


@session.test(skip="Skipped for demo")
async def test_skipped():
    pass


@session.test(xfail="Known issue")
async def test_xfail():
    await asyncio.sleep(0.1)
    assert False, "This is expected to fail"
