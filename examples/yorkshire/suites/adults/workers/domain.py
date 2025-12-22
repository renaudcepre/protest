"""Domain objects for the workers suite."""

from dataclasses import dataclass

from examples.yorkshire.kennel import Kennel


@dataclass
class WorkSchedule:
    """Work schedule for the kennel."""

    kennel: Kennel
    shift_start: int = 9
    shift_end: int = 17

    @property
    def shift_hours(self) -> int:
        return self.shift_end - self.shift_start


@dataclass
class DetectiveTools:
    """Equipment for detective yorkshires."""

    magnifying_glass: bool = True
    trench_coat: bool = True
    case_notes: list[str] | None = None

    def __post_init__(self) -> None:
        self.case_notes = self.case_notes or []


@dataclass
class ChefKitchen:
    """Kitchen setup for chef yorkshires."""

    stove_on: bool = False
    ingredients: list[str] | None = None

    def __post_init__(self) -> None:
        self.ingredients = self.ingredients or []
