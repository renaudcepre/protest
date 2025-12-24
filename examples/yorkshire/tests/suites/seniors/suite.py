"""Seniors suite - tests for elderly yorkshires."""

import asyncio
from typing import Annotated

from examples.yorkshire.app.domain import Coat, Job, Size, Yorkshire
from examples.yorkshire.tests.fixtures import yorkshire
from protest import FixtureFactory, ProTestSuite, Retry, Use

seniors_suite = ProTestSuite("Seniors", tags=["senior"])


@seniors_suite.test()
async def test_senior_still_works(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    old_boy = await factory(name="Papy", age=120, job=Job.DETECTIVE)
    assert old_boy.is_senior
    assert old_boy.can_work


@seniors_suite.test(tags=["slow"])
async def test_senior_nap_time(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    senior = await factory(name="Sleepy", age=100)
    nap_duration = await senior.nap()
    assert nap_duration > 0.15  # noqa


@seniors_suite.test(timeout=1.0)
async def test_senior_slow_walk() -> None:
    await asyncio.sleep(0.1)


@seniors_suite.test(timeout=0.1, xfail="Seniors take their time")
async def test_senior_marathon() -> None:
    await asyncio.sleep(0.5)


@seniors_suite.test()
def test_senior_needs_grooming_sync() -> None:
    senior = Yorkshire(
        name="OldTimer", size=Size.STANDARD, job=Job.THERAPIST, age=100, coat=Coat.SHORT
    )
    assert senior.is_senior
    assert senior.needs_grooming


@seniors_suite.test(skip="Astronaut program suspended until 2026")
async def test_senior_astronaut_mission() -> None:
    """Skipped test - astronaut program on hold."""


# =============================================================================
# RETRY EXAMPLE
# =============================================================================


@seniors_suite.test(
    timeout=0.15,
    retry=Retry(times=2, on=TimeoutError, delay=0.05),
    tags=["retry-example"],
)
async def test_senior_wakes_up_eventually(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    """Senior yorkshire takes too long to wake up, but eventually responds."""
    papy = await factory(name="Papy", age=120, job=Job.THERAPIST)
    assert papy.is_senior
