"""Custom factory classes for Yorkshire terriers.

These classes demonstrate the `managed=False` pattern where you define
your own factory class with custom methods instead of using ProTest's
built-in FixtureFactory wrapper.
"""

from examples.yorkshire.app.domain import Coat, Job, Size, Yorkshire
from examples.yorkshire.app.kennel import Kennel


class YorkshireFactory:
    """Custom factory for creating Yorkshire terriers with convenience methods.

    Unlike the default FixtureFactory (which wraps a function and calls it
    with kwargs), this class provides explicit methods for common creation
    patterns.

    Usage with @factory(managed=False):
        @factory(managed=False)
        def dog_factory(kennel: Annotated[Kennel, Use(kennel)]) -> YorkshireFactory:
            return YorkshireFactory(kennel)

        @suite.test()
        def test_dogs(factory: Annotated[YorkshireFactory, Use(dog_factory)]):
            puppy = factory.create_puppy("Tiny")
            adults = factory.create_pack(count=3)
    """

    def __init__(self, kennel: Kennel) -> None:
        self.kennel = kennel
        self.created: list[Yorkshire] = []

    def create(
        self,
        name: str,
        size: Size = Size.STANDARD,
        job: Job = Job.UNEMPLOYED,
        age: int = 24,
        coat: Coat = Coat.SILKY,
    ) -> Yorkshire:
        """Create a single Yorkshire terrier."""
        dog = Yorkshire(name=name, size=size, job=job, age=age, coat=coat)
        self.created.append(dog)
        return dog

    def create_puppy(self, name: str, size: Size = Size.TEACUP) -> Yorkshire:
        """Create a young puppy (age 3 months)."""
        return self.create(name=name, size=size, age=3)

    def create_senior(self, name: str, job: Job = Job.UNEMPLOYED) -> Yorkshire:
        """Create a senior dog (age 10 years)."""
        return self.create(name=name, age=120, job=job)

    def create_worker(self, name: str, job: Job) -> Yorkshire:
        """Create a working-age dog with a specific job."""
        if job == Job.UNEMPLOYED:
            raise ValueError("Workers must have a job!")
        return self.create(name=name, age=36, job=job)

    def create_pack(self, count: int, prefix: str = "Dog") -> list[Yorkshire]:
        """Create multiple dogs with numbered names."""
        return [self.create(name=f"{prefix}_{i}") for i in range(count)]

    async def cleanup(self) -> int:
        """Remove all created dogs from kennel. Returns count removed."""
        count = 0
        for dog in self.created:
            await self.kennel.remove(dog.name)
            count += 1
        self.created.clear()
        return count
