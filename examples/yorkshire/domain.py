import asyncio
from dataclasses import dataclass
from enum import Enum


class Size(Enum):
    TEACUP = "teacup"
    MINI = "mini"
    STANDARD = "standard"


class Coat(Enum):
    LONG = "long"
    SHORT = "short"
    SILKY = "silky"


class Job(Enum):
    INFLUENCER = "influencer"
    BODYGUARD = "bodyguard"
    DETECTIVE = "detective"
    CHEF = "chef"
    ASTRONAUT = "astronaut"
    THERAPIST = "therapist"
    UNEMPLOYED = "unemployed"


@dataclass
class Yorkshire:
    name: str
    size: Size
    job: Job
    age: int
    coat: Coat = Coat.SILKY

    @property
    def is_puppy(self) -> bool:
        return self.age < 12

    @property
    def is_senior(self) -> bool:
        return self.age > 96

    @property
    def can_work(self) -> bool:
        return not self.is_puppy and self.job != Job.UNEMPLOYED

    @property
    def needs_grooming(self) -> bool:
        return self.coat == Coat.LONG or self.age > 72

    async def nap(self) -> float:
        duration = self.age * 0.002
        await asyncio.sleep(duration)
        return duration
