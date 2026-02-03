"""Custom factory suite demonstrating @factory(managed=False).

This suite shows how to use a custom factory class instead of ProTest's
built-in FixtureFactory. This is useful when you want:
- Multiple creation methods (create_puppy, create_senior, create_pack)
- Custom validation logic in factory methods
- State tracking across multiple creations
- Batch operations (create_many, cleanup)

Compare with the standard @factory() approach in fixtures.py which uses
FixtureFactory and is called like: `await dog_factory(name="Rex", age=24)`
"""

from typing import Annotated

from examples.yorkshire.app.domain import Job, Size
from examples.yorkshire.app.factories import YorkshireFactory
from examples.yorkshire.app.kennel import Kennel
from examples.yorkshire.tests.fixtures import kennel
from protest import ProTestSuite, Use, factory

# =============================================================================
# CUSTOM FACTORY FIXTURE (managed=False)
# =============================================================================


@factory(managed=False)
async def dog_factory(
    kennel_instance: Annotated[Kennel, Use(kennel)],
) -> YorkshireFactory:
    """Factory fixture returning a custom YorkshireFactory class.

    With managed=False, ProTest returns the factory class directly instead
    of wrapping it in FixtureFactory. This gives you full control over the
    factory's API.

    The fixture can still use yield for teardown:
    """
    factory_instance = YorkshireFactory(kennel_instance)
    yield factory_instance
    # Cleanup all created dogs when the fixture is torn down
    await factory_instance.cleanup()


# =============================================================================
# CUSTOM FACTORY SUITE
# =============================================================================

custom_factory_suite = ProTestSuite(
    "CustomFactory",
    tags=["factory", "managed-false"],
    description="Demonstrates @factory(managed=False) with custom factory class",
)

custom_factory_suite.bind(dog_factory)


# =============================================================================
# TESTS USING CUSTOM FACTORY METHODS
# =============================================================================


@custom_factory_suite.test()
async def test_create_single_dog(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test basic creation with custom factory."""
    rex = factory.create(name="Rex", size=Size.STANDARD, job=Job.DETECTIVE, age=36)

    assert rex.name == "Rex"
    assert rex.size == Size.STANDARD
    assert rex.job == Job.DETECTIVE
    assert rex.can_work is True


@custom_factory_suite.test()
async def test_create_puppy_shortcut(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test create_puppy() convenience method."""
    tiny = factory.create_puppy("Tiny", size=Size.TEACUP)

    assert tiny.name == "Tiny"
    expected_puppy_age = 3
    assert tiny.age == expected_puppy_age
    assert tiny.is_puppy is True
    assert tiny.can_work is False


@custom_factory_suite.test()
async def test_create_senior_shortcut(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test create_senior() convenience method."""
    grandpa = factory.create_senior("Grandpa")

    assert grandpa.name == "Grandpa"
    expected_senior_age = 120
    assert grandpa.age == expected_senior_age
    assert grandpa.is_senior is True


@custom_factory_suite.test()
async def test_create_worker_with_validation(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test create_worker() which validates job != UNEMPLOYED."""
    chef = factory.create_worker("Gordon", job=Job.CHEF)

    assert chef.job == Job.CHEF
    assert chef.can_work is True


@custom_factory_suite.test()
async def test_create_pack_batch_creation(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test create_pack() for batch creation."""
    pack = factory.create_pack(count=5, prefix="Pup")

    expected_count = 5
    assert len(pack) == expected_count
    assert pack[0].name == "Pup_0"
    assert pack[4].name == "Pup_4"
    # Factory tracks all created dogs
    assert len(factory.created) == expected_count


@custom_factory_suite.test()
async def test_factory_tracks_created_dogs(
    factory: Annotated[YorkshireFactory, Use(dog_factory)],
) -> None:
    """Test that factory.created tracks all dogs."""
    factory.create("Alice")
    factory.create("Bob")
    factory.create_puppy("Charlie")

    expected_count = 3
    assert len(factory.created) == expected_count
    names = [dog.name for dog in factory.created]
    assert names == ["Alice", "Bob", "Charlie"]
