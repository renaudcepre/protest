"""Workers suite with nested suites demonstrating scope hierarchy."""

from typing import Annotated

from examples.yorkshire.domain import Job, Yorkshire
from examples.yorkshire.fixtures import yorkshire
from examples.yorkshire.suites.adults.workers.domain import (
    ChefKitchen,
    DetectiveTools,
    WorkSchedule,
)
from examples.yorkshire.suites.adults.workers.fixtures import (
    case_file,
    chef_kitchen,
    detective_tools,
    recipe,
    scheduled_worker,
    setup_work_environment,
    work_schedule,
)
from protest import FixtureFactory, ProTestSuite, Use


# =============================================================================
# WORKERS SUITE (parent)
# =============================================================================

workers_suite = ProTestSuite(
    "Workers",
    tags=["working"],
    max_concurrency=2,
    description="Tests for employed yorkshires with nested job-specific suites",
)

workers_suite.fixture(setup_work_environment, autouse=True)
workers_suite.fixture(work_schedule)
workers_suite.fixture(scheduled_worker)


# =============================================================================
# DETECTIVES SUITE (child of Workers)
# =============================================================================

detectives_suite = ProTestSuite(
    "Detectives",
    tags=["investigation"],
    description="Tests for detective yorkshires",
)
workers_suite.add_suite(detectives_suite)
detectives_suite.fixture(detective_tools)


@detectives_suite.test()
async def test_detective_has_tools(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    tools: Annotated[DetectiveTools, Use(detective_tools)],
) -> None:
    """Detective can use their tools."""
    rex = await dog_factory(name="Rex", job=Job.DETECTIVE, age=36)
    assert rex.can_work
    assert tools.magnifying_glass
    assert tools.trench_coat


@detectives_suite.test()
async def test_detective_opens_case(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    case: Annotated[dict[str, str], Use(case_file)],
) -> None:
    """Detective works on a case (uses test-scoped case_file)."""
    sherlock = await dog_factory(name="Sherlock", job=Job.DETECTIVE, age=48)
    assert sherlock.can_work
    assert case["status"] == "open"
    case["notes"] = "Found suspicious treat crumbs"


@detectives_suite.test()
def test_detective_tools_persist_across_tests(
    tools: Annotated[DetectiveTools, Use(detective_tools)],
) -> None:
    """Suite fixture persists - previous test's notes are visible."""
    assert tools.case_notes is not None
    assert len(tools.case_notes) >= 1


# =============================================================================
# CHEFS SUITE (child of Workers)
# =============================================================================

chefs_suite = ProTestSuite(
    "Chefs",
    tags=["culinary"],
    description="Tests for chef yorkshires",
)
workers_suite.add_suite(chefs_suite)
chefs_suite.fixture(chef_kitchen)


@chefs_suite.test()
async def test_chef_has_kitchen(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    kitchen: Annotated[ChefKitchen, Use(chef_kitchen)],
) -> None:
    """Chef can use the kitchen."""
    gordon = await dog_factory(name="Gordon", job=Job.CHEF, age=48)
    assert gordon.can_work
    assert kitchen.stove_on
    assert "treats" in (kitchen.ingredients or [])


@chefs_suite.test()
async def test_chef_cooks_recipe(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    current_recipe: Annotated[dict[str, list[str]], Use(recipe)],
) -> None:
    """Chef follows a recipe (uses test-scoped recipe fixture)."""
    julia = await dog_factory(name="Julia", job=Job.CHEF, age=60)
    assert julia.can_work
    current_recipe["steps"].append("Mix ingredients")
    current_recipe["steps"].append("Bake at 180C")
    assert len(current_recipe["steps"]) == 2


# =============================================================================
# WORKERS SUITE DIRECT TESTS
# =============================================================================


@workers_suite.test()
async def test_worker_has_schedule(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    schedule: Annotated[WorkSchedule, Use(work_schedule)],
) -> None:
    """Any worker can check the schedule."""
    worker = await dog_factory(name="Worker", job=Job.THERAPIST, age=30)
    assert worker.can_work
    assert schedule.shift_hours == 10  # 18 - 8


@workers_suite.test()
async def test_scheduled_worker_factory(
    worker_factory: Annotated[FixtureFactory[Yorkshire], Use(scheduled_worker)],
) -> None:
    """Suite-scoped factory creates workers with schedule context."""
    therapist = await worker_factory(name="Dr. Bark", job=Job.THERAPIST)
    bodyguard = await worker_factory(name="Bruno", job=Job.BODYGUARD)

    # Both workers have age based on 10h shift (24 + 10 = 34)
    assert therapist.age == 34
    assert bodyguard.age == 34
    assert therapist.can_work
    assert bodyguard.can_work
