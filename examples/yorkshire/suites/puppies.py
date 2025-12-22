"""Puppies suite - tests for young yorkshires."""

from typing import Annotated

from examples.yorkshire.domain import Coat, Job, Size, Yorkshire
from examples.yorkshire.fixtures import yorkshire
from protest import FixtureFactory, ProTestSuite, Use

puppies_suite = ProTestSuite("Puppies", tags=["puppy"])


@puppies_suite.test()
async def test_puppy_cannot_work(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    puppy = await factory(name="Bebe", age=6)
    assert puppy.is_puppy
    assert not puppy.can_work


@puppies_suite.test()
async def test_puppy_growth(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    puppy = await factory(name="Tiny", age=11)
    assert puppy.is_puppy

    adult = await factory(name="BigTiny", age=12)
    assert not adult.is_puppy


@puppies_suite.test()
def test_puppy_age_validation_sync() -> None:
    puppy = Yorkshire(name="SyncPup", size=Size.MINI, job=Job.UNEMPLOYED, age=6)
    assert puppy.is_puppy
    assert not puppy.can_work


@puppies_suite.test()
def test_puppy_needs_no_grooming_sync() -> None:
    puppy = Yorkshire(
        name="ShortCoat", size=Size.TEACUP, job=Job.UNEMPLOYED, age=8, coat=Coat.SHORT
    )
    assert not puppy.needs_grooming
