"""Unemployed yorkshires suite - dogs without jobs."""

from typing import Annotated

from examples.yorkshire.domain import Job, Yorkshire
from examples.yorkshire.fixtures import kennel, yorkshire
from examples.yorkshire.kennel import Kennel
from protest import FixtureFactory, ProTestSuite, Use

unemployed_suite = ProTestSuite("Unemployed")


@unemployed_suite.test()
async def test_unemployed_dog_cannot_work(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    """Unemployed dogs cannot work, even if adults."""
    lazy = await factory(name="Lazy", job=Job.UNEMPLOYED, age=24)
    assert not lazy.can_work


@unemployed_suite.test()
async def test_firing_a_dog(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    kennel_fixture: Annotated[Kennel, Use(kennel)],
) -> None:
    """Dogs can be fired and become unemployed."""
    chef = await factory(name="Gordon", job=Job.CHEF, age=36)
    assert chef.can_work

    await kennel_fixture.fire("Gordon")
    updated = await kennel_fixture.get("Gordon")

    assert updated is not None
    assert updated.job == Job.UNEMPLOYED
