"""Fixtures for the workers suite hierarchy."""

from collections.abc import Generator
from typing import Annotated

from examples.yorkshire.app.domain import Job, Size, Yorkshire
from examples.yorkshire.app.kennel import Kennel
from examples.yorkshire.app.workers import (
    ChefKitchen,
    DetectiveTools,
    WorkSchedule,
)
from examples.yorkshire.tests.fixtures import kennel
from protest import Use, factory, fixture

# =============================================================================
# WORKERS FIXTURES
# =============================================================================


@fixture()
def setup_work_environment(
    kennel_instance: Annotated[Kennel, Use(kennel)],
) -> Generator[None, None, None]:
    """Autouse fixture: prepares work environment when Workers suite starts."""
    print("  [workers] Setting up work environment (kennel has capacity)")  # noqa: T201
    yield
    print("  [workers] Cleaning up work environment")  # noqa: T201


@fixture()
def work_schedule(
    kennel_instance: Annotated[Kennel, Use(kennel)],
) -> Generator[WorkSchedule, None, None]:
    """Work schedule shared across all workers tests."""
    schedule = WorkSchedule(kennel=kennel_instance, shift_start=8, shift_end=18)
    print(f"  [workers] Created schedule: {schedule.shift_hours}h shift")  # noqa: T201
    yield schedule
    print("  [workers] Schedule ended")  # noqa: T201


@factory()
def scheduled_worker(
    schedule: Annotated[WorkSchedule, Use(work_schedule)],
    name: str = "Anonymous",
    job: Job = Job.THERAPIST,
) -> Generator[Yorkshire, None, None]:
    """Factory for workers with schedule awareness."""
    age = 24 + schedule.shift_hours
    worker = Yorkshire(name=name, size=Size.STANDARD, job=job, age=age)
    print(f"  [factory] Created {name} for {schedule.shift_hours}h shift")  # noqa: T201
    yield worker
    print(f"  [factory] {name} clocked out")  # noqa: T201


# =============================================================================
# DETECTIVES FIXTURES
# =============================================================================


@fixture()
def detective_tools(
    schedule: Annotated[WorkSchedule, Use(work_schedule)],
) -> Generator[DetectiveTools, None, None]:
    """Detective equipment, depends on parent suite's work_schedule."""
    tools = DetectiveTools()
    print(f"  [detectives] Tools ready (shift: {schedule.shift_hours}h)")  # noqa: T201
    yield tools
    print("  [detectives] Tools stored")  # noqa: T201


@fixture()
def case_file(
    tools: Annotated[DetectiveTools, Use(detective_tools)],
) -> Generator[dict[str, str], None, None]:
    """Fresh case file for each test."""
    case = {"status": "open", "notes": ""}
    tools.case_notes.append("New case opened")  # type: ignore[union-attr]
    yield case
    case["status"] = "closed"


# =============================================================================
# CHEFS FIXTURES
# =============================================================================


@fixture()
def chef_kitchen(
    schedule: Annotated[WorkSchedule, Use(work_schedule)],
) -> Generator[ChefKitchen, None, None]:
    """Kitchen setup, depends on parent suite's work_schedule."""
    kitchen = ChefKitchen(stove_on=True, ingredients=["treats", "bacon"])
    print(f"  [chefs] Kitchen open (shift: {schedule.shift_hours}h)")  # noqa: T201
    yield kitchen
    kitchen.stove_on = False
    print("  [chefs] Kitchen closed")  # noqa: T201


@fixture()
def recipe(
    kitchen: Annotated[ChefKitchen, Use(chef_kitchen)],
) -> dict[str, list[str]]:
    """Fresh recipe for each test."""
    return {
        "steps": [],
        "ingredients_used": kitchen.ingredients.copy() if kitchen.ingredients else [],
    }
