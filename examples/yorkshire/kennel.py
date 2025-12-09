import logging
from dataclasses import replace

from examples.yorkshire.domain import Job, Yorkshire

logger = logging.getLogger(__name__)


class Kennel:
    def __init__(self) -> None:
        self._dogs: dict[str, Yorkshire] = {}

    async def add(self, dog: Yorkshire) -> None:
        logger.info("Adding %s to kennel", dog.name)
        self._dogs[dog.name] = dog

    async def get(self, name: str) -> Yorkshire | None:
        return self._dogs.get(name)

    async def remove(self, name: str) -> None:
        logger.info("Removing %s from kennel", name)
        self._dogs.pop(name, None)

    async def list_all(self) -> list[Yorkshire]:
        return list(self._dogs.values())

    async def list_by_job(self, job: Job) -> list[Yorkshire]:
        return [dog for dog in self._dogs.values() if dog.job == job]

    async def list_puppies(self) -> list[Yorkshire]:
        return [dog for dog in self._dogs.values() if dog.is_puppy]

    async def fire(self, name: str) -> None:
        logger.info("Firing %s", name)
        if dog := self._dogs.get(name):
            self._dogs[name] = replace(dog, job=Job.UNEMPLOYED)

    async def clear(self) -> None:
        logger.info("Clearing kennel")
        self._dogs.clear()
