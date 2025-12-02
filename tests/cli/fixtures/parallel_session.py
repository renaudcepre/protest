import asyncio

from protest import ProTestSession

session = ProTestSession()


@session.test()
async def test_parallel_a() -> None:
    await asyncio.sleep(0.1)


@session.test()
async def test_parallel_b() -> None:
    await asyncio.sleep(0.1)


@session.test()
async def test_parallel_c() -> None:
    await asyncio.sleep(0.1)
