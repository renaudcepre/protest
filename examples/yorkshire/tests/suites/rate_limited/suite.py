"""Rate-limited suite demonstrating fixture max_concurrency.

This suite shows how to use `max_concurrency` on fixtures to limit how many tests
can use a shared resource simultaneously. This is useful for:
- Rate-limited APIs that only allow N concurrent requests
- Connection pools with limited capacity
- License-restricted resources

Key concept: `max_concurrency` limits concurrent ACCESS to the fixture,
not the number of instances. A SESSION-scoped fixture with max_concurrency=2
will have 1 instance, but only 2 tests can use it at the same time.
"""

import asyncio
from typing import Annotated

from examples.yorkshire.app.domain import Job, Size, Yorkshire
from examples.yorkshire.app.services import GroomingService
from examples.yorkshire.tests.fixtures import yorkshire
from protest import FixtureFactory, ProTestSuite, Use, fixture

# =============================================================================
# RATE-LIMITED GROOMING API FIXTURE
# =============================================================================


@fixture(max_concurrency=2, tags=["rate-limited"])
async def grooming_api() -> GroomingService:
    """Rate-limited grooming API that only allows 2 concurrent requests.

    This simulates a real-world API with rate limiting. Only 2 tests can
    access the API at the same time, regardless of how many workers are running.

    With 10 parallel workers and 6 tests, you'd normally see all 6 tests
    running at once. But with max_concurrency=2, only 2 tests can use
    this fixture simultaneously.
    """
    await asyncio.sleep(0.01)  # Simulate connection setup
    yield GroomingService()
    # No teardown needed for this simple service


# =============================================================================
# RATE-LIMITED SUITE
# =============================================================================

rate_limited_suite = ProTestSuite(
    "RateLimited",
    tags=["api", "rate-limited"],
    description="Tests demonstrating fixture max_concurrency for rate-limited APIs",
)

rate_limited_suite.bind(grooming_api)


# =============================================================================
# TESTS - These will run with max 2 concurrent API accesses
# =============================================================================


@rate_limited_suite.test()
async def test_groom_teacup(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test grooming a teacup yorkshire via rate-limited API."""
    tiny = await dog_factory(name="Tiny", size=Size.TEACUP, age=12)
    price = await api.groom(tiny)
    # teacup base (25.0) * silky coat multiplier (1.3) = 32.5
    expected_price = 32.5
    assert price == expected_price


@rate_limited_suite.test()
async def test_groom_mini(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test grooming a mini yorkshire via rate-limited API."""
    mini = await dog_factory(name="Mini", size=Size.MINI, age=24)
    price = await api.groom(mini)
    # mini base (35.0) * silky coat multiplier (1.3) = 45.5
    expected_price = 45.5
    assert price == expected_price


@rate_limited_suite.test()
async def test_groom_standard(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test grooming a standard yorkshire via rate-limited API."""
    standard = await dog_factory(name="Max", age=36)  # standard is default
    price = await api.groom(standard)
    # standard base (45.0) * silky coat multiplier (1.3) = 58.5
    expected_price = 58.5
    assert price == expected_price


@rate_limited_suite.test()
async def test_schedule_appointment(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test scheduling grooming appointment via rate-limited API."""
    buddy = await dog_factory(name="Buddy", age=18)
    appointment_id = await api.schedule_appointment(buddy, "2024-03-15")
    assert appointment_id == "APT-BUD-20240315"


@rate_limited_suite.test()
async def test_groom_senior(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test grooming a senior yorkshire (needs gentle handling)."""
    senior = await dog_factory(name="Grandpa", age=120, job=Job.UNEMPLOYED)
    price = await api.groom(senior)
    expected_min_price = 25.0  # At least teacup base price
    assert price >= expected_min_price


@rate_limited_suite.test()
async def test_groom_puppy(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    api: Annotated[GroomingService, Use(grooming_api)],
) -> None:
    """Test grooming a young puppy (first grooming experience)."""
    puppy = await dog_factory(name="Baby", age=4)
    price = await api.groom(puppy)
    expected_min_price = 25.0  # At least teacup base price
    assert price >= expected_min_price
