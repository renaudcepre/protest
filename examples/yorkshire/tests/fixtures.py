"""Shared fixtures for Yorkshire examples.

Fixtures defined here can be bound to different scopes:
- SESSION: session.bind(fn)
- SUITE: suite.bind(fn)
- TEST: no binding needed (default)

For SUITE-scoped fixtures examples, see suites/workers/suite.py
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Generator
from typing import Annotated

from examples.yorkshire.app.domain import Job, Size, Yorkshire
from examples.yorkshire.app.kennel import Kennel
from protest import Use, factory, fixture


@fixture()
def configure_kennel_logging() -> Generator[None, None, None]:
    """Enable debug logging for Yorkshire module."""
    logging.getLogger("examples.yorkshire").setLevel(logging.DEBUG)
    yield


@fixture(tags=["database", "slow-setup"])
async def kennel() -> AsyncGenerator[Kennel, None]:
        kennel_instance = Kennel()
    await asyncio.sleep(0.1)
    yield kennel_instance
    await kennel_instance.clear()


@factory()
async def yorkshire(
    kennel_fixture: Annotated[Kennel, Use(kennel)],
    name: str = "Unnamed",
    size: Size = Size.STANDARD,
    job: Job = Job.UNEMPLOYED,
    age: int = 24,
) -> Yorkshire:
    """Factory for creating Yorkshire terriers.

    Each yorkshire is added to the kennel on creation and removed on teardown.
    """
    dog = Yorkshire(name=name, size=size, job=job, age=age)
    await kennel_fixture.add(dog)
    yield dog
    await kennel_fixture.remove(dog.name)


@fixture(tags=["temp"])
def grooming_quote() -> dict[str, float]:
    """Grooming price quote for cartesian product tests."""
    return {"base": 30.0, "long_coat_extra": 15.0}
