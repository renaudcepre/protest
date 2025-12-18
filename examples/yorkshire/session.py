import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Generator
from typing import Annotated
from uuid import uuid4

from examples.yorkshire.domain import Coat, Job, Size, Yorkshire
from examples.yorkshire.kennel import Kennel
from examples.yorkshire.services import GroomingService, VetService
from protest import (
    FixtureFactory,
    ForEach,
    From,
    Mocker,
    ProTestSession,
    ProTestSuite,
    Retry,
    Use,
    caplog,
    factory,
    fixture,
    mocker,
    raises,
)
from protest.entities import LogCapture

session = ProTestSession(concurrency=4)


# =============================================================================
# SESSION AUTOUSE (auto-resolved at session start)
# =============================================================================


@session.autouse()
def configure_kennel_logging() -> Generator[None, None, None]:
    logging.getLogger("examples.yorkshire").setLevel(logging.DEBUG)
    yield


# =============================================================================
# SESSION FIXTURES
# =============================================================================


@session.fixture(tags=["database", "slow-setup"])
async def kennel() -> AsyncGenerator[Kennel, None]:
    kennel_instance = Kennel()
    await asyncio.sleep(1)
    yield kennel_instance
    print("  [kennel] starting LONG teardown (1 seconds)...")  # noqa
    await asyncio.sleep(3)
    print("  [kennel] teardown complete!")  # noqa
    await kennel_instance.clear()


@factory()
async def yorkshire_factory(
    kennel_fixture: Annotated[Kennel, Use(kennel)],
    name: str = "Unnamed",
    size: Size = Size.STANDARD,
    job: Job = Job.UNEMPLOYED,
    age: int = 24,
) -> Yorkshire:
    dog = Yorkshire(name=name, size=size, job=job, age=age)
    await kennel_fixture.add(dog)
    await asyncio.sleep(age / 100)
    print(f"Creating {dog.name}... ")  # noqa: T201
    yield dog
    await asyncio.sleep(age / 100)
    await kennel_fixture.remove(dog.name)


# =============================================================================
# SUITES
# =============================================================================

puppies_suite = ProTestSuite("Puppies", tags=["puppy"])
adults_suite = ProTestSuite("Adults")
workers_suite = ProTestSuite("Workers", tags=["working"], max_concurrency=2)
unemployed_suite = ProTestSuite("Unemployed")
seniors_suite = ProTestSuite("Seniors", tags=["senior"])
legacy_suite = ProTestSuite(
    "Legacy",
    description="Old sync-only code, no parallel execution",
    tags=["legacy"],
    max_concurrency=1,
)

adults_suite.add_suite(workers_suite)
adults_suite.add_suite(unemployed_suite)

session.add_suite(puppies_suite)
session.add_suite(adults_suite)
session.add_suite(seniors_suite)
session.add_suite(legacy_suite)


# =============================================================================
# SUITE AUTOUSE (auto-resolved when suite starts)
# =============================================================================


@workers_suite.autouse()
def setup_work_environment() -> Generator[None, None, None]:
    yield


# =============================================================================
# SUITE FIXTURES
# =============================================================================


@fixture()
async def working_dog(
    dog_factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> Yorkshire:
    return await dog_factory(name="Rex", job=Job.DETECTIVE, age=36)


# =============================================================================
# FUNCTION-SCOPED FIXTURES
# =============================================================================


@fixture()
def appointment_id() -> str:
    return f"apt_{uuid4().hex[:8]}"


@fixture(tags=["temp"])
def grooming_quote() -> dict[str, float]:
    return {"base": 30.0, "long_coat_extra": 15.0}


# =============================================================================
# PARAMETERIZATION
# =============================================================================

JOBS = ForEach(
    [Job.INFLUENCER, Job.BODYGUARD, Job.DETECTIVE, Job.CHEF, Job.THERAPIST],
    ids=lambda job: job.value,
)

SIZES = ForEach(
    [Size.TEACUP, Size.MINI, Size.STANDARD],
    ids=lambda size: size.value,
)

COATS = ForEach(
    [Coat.LONG, Coat.SHORT],
    ids=lambda coat: coat.value,
)


# =============================================================================
# SESSION-LEVEL TESTS
# =============================================================================


@session.test()
async def test_kennel_starts_empty(
    kennel_fixture: Annotated[Kennel, Use(kennel)],
) -> None:
    dogs = await kennel_fixture.list_all()
    expected_count = 0
    assert len(dogs) == expected_count


@session.test()
async def test_multiple_yorkshires(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    fifi = await factory(name="Fifi", job=Job.INFLUENCER)
    rex = await factory(name="Rex", job=Job.BODYGUARD)
    assert fifi.name != rex.name
    assert fifi.job != rex.job


@session.test()
async def test_kennel_logs_additions(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
    logs: Annotated[LogCapture, Use(caplog)],
) -> None:
    await factory(name="Logger")
    assert "Logger" in logs.text


# =============================================================================
# MOCKER TESTS (sync + async)
# =============================================================================


@session.test()
def test_vet_checkup_sync(mock: Annotated[Mocker, Use(mocker)]) -> None:
    vet = VetService()
    dog = Yorkshire(name="Patient", size=Size.MINI, job=Job.UNEMPLOYED, age=24)

    mock_checkup = mock.patch.object(vet, "checkup")
    mock_checkup.return_value = {"healthy": True, "weight": 2.8}

    result = vet.checkup(dog)

    assert result["healthy"] is True
    mock_checkup.assert_called_once_with(dog)


@session.test()
async def test_grooming_appointment_async(mock: Annotated[Mocker, Use(mocker)]) -> None:
    grooming = GroomingService()
    dog = Yorkshire(name="Fluffy", size=Size.STANDARD, job=Job.INFLUENCER, age=36)

    mock_schedule = mock.patch.object(grooming, "schedule_appointment")
    mock_schedule.return_value = "APT-FLU-20251225"

    result = await grooming.schedule_appointment(dog, "2025-12-25")

    assert result == "APT-FLU-20251225"
    mock_schedule.assert_called_once_with(dog, "2025-12-25")


@session.test()
def test_vet_spy_real_method(mock: Annotated[Mocker, Use(mocker)]) -> None:
    vet = VetService()
    dog = Yorkshire(name="Spied", size=Size.TEACUP, job=Job.THERAPIST, age=18)

    spy = mock.spy(vet.checkup)

    result = vet.checkup(dog)

    assert result["healthy"] is True
    spy.assert_called_once_with(dog)
    assert spy.spy_return == result


# =============================================================================
# CARTESIAN PRODUCT (Size * Coat = 6 tests)
# =============================================================================


@session.test()
def test_grooming_price_matrix(
    size: Annotated[Size, From(SIZES)],
    coat: Annotated[Coat, From(COATS)],
    quote: Annotated[dict[str, float], Use(grooming_quote)],
) -> None:
    dog = Yorkshire(name="Matrix", size=size, job=Job.UNEMPLOYED, age=24, coat=coat)
    price = quote["base"]
    if coat == Coat.LONG:
        price += quote["long_coat_extra"]
    assert price > 0
    assert dog.needs_grooming == (coat == Coat.LONG)


# =============================================================================
# PUPPIES SUITE
# =============================================================================


@puppies_suite.test()
async def test_puppy_cannot_work(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    puppy_age = 6
    puppy = await factory(name="Bebe", age=puppy_age)
    assert puppy.is_puppy
    assert not puppy.can_work


@puppies_suite.test()
async def test_puppy_growth(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    almost_adult_age = 11
    puppy = await factory(name="Tiny", age=almost_adult_age)
    assert puppy.is_puppy
    adult_age = 12
    adult = await factory(name="BigTiny", age=adult_age)
    assert not adult.is_puppy


@puppies_suite.test()
def test_puppy_age_validation_sync() -> None:
    puppy_age = 6
    puppy = Yorkshire(name="SyncPup", size=Size.MINI, job=Job.UNEMPLOYED, age=puppy_age)
    assert puppy.is_puppy
    assert not puppy.can_work


@puppies_suite.test()
def test_puppy_needs_no_grooming_sync() -> None:
    puppy = Yorkshire(
        name="ShortCoat", size=Size.TEACUP, job=Job.UNEMPLOYED, age=8, coat=Coat.SHORT
    )
    assert not puppy.needs_grooming


# =============================================================================
# WORKERS SUITE (nested under Adults)
# =============================================================================


@workers_suite.test()
async def test_job_assignment(
    job: Annotated[Job, From(JOBS)],
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    worker_age = 24
    dog = await factory(name="Worker", job=job, age=worker_age)
    assert dog.can_work


@workers_suite.test(tags=["slow"])
async def test_detective_finds_treats(
    working_dog_fixture: Annotated[Yorkshire, Use(working_dog)],
) -> None:
    assert working_dog_fixture.job == Job.DETECTIVE
    investigation_time = 0.1
    await asyncio.sleep(investigation_time)


@workers_suite.test(xfail="Bug: teacup yorkies too small for bodyguard vest")
async def test_teacup_bodyguard(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    adult_age = 24
    tiny_guard = await factory(
        name="Brutus",
        size=Size.TEACUP,
        job=Job.BODYGUARD,
        age=adult_age,
    )
    assert tiny_guard.can_work
    assert tiny_guard.size == Size.STANDARD


@workers_suite.test(skip="Astronaut program suspended until 2026")
async def test_astronaut_mission() -> None:
    pass


# =============================================================================
# UNEMPLOYED SUITE (nested under Adults)
# =============================================================================


@unemployed_suite.test()
async def test_unemployed_dog_cannot_work(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    adult_age = 24
    lazy = await factory(name="Lazy", job=Job.UNEMPLOYED, age=adult_age)
    assert not lazy.can_work


@unemployed_suite.test()
async def test_firing_a_dog(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
    kennel_fixture: Annotated[Kennel, Use(kennel)],
) -> None:
    adult_age = 36
    chef = await factory(name="Gordon", job=Job.CHEF, age=adult_age)
    assert chef.can_work

    await kennel_fixture.fire("Gordon")
    updated = await kennel_fixture.get("Gordon")

    assert updated is not None
    assert updated.job == Job.UNEMPLOYED


# =============================================================================
# SENIORS SUITE
# =============================================================================


@seniors_suite.test()
async def test_senior_still_works(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    senior_age = 120
    old_boy = await factory(name="Papy", age=senior_age, job=Job.DETECTIVE)
    assert old_boy.is_senior
    assert old_boy.can_work


@seniors_suite.test(tags=["slow"])
async def test_senior_nap_time(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    senior = await factory(name="Sleepy", age=100)
    nap_duration = await senior.nap()
    expected_min_duration = 0.15
    assert nap_duration > expected_min_duration


@seniors_suite.test(timeout=1.0)
async def test_senior_slow_walk() -> None:
    walk_duration = 0.1
    await asyncio.sleep(walk_duration)


@seniors_suite.test(timeout=0.1, xfail="Seniors take their time")
async def test_senior_marathon() -> None:
    marathon_duration = 1.0
    await asyncio.sleep(marathon_duration)


@seniors_suite.test()
def test_senior_needs_grooming_sync() -> None:
    senior = Yorkshire(
        name="OldTimer", size=Size.STANDARD, job=Job.THERAPIST, age=100, coat=Coat.SHORT
    )
    assert senior.is_senior
    assert senior.needs_grooming


# =============================================================================
# LEGACY SUITE (sync-only, max_concurrency=1)
# =============================================================================


@legacy_suite.fixture()
def fax_machine() -> Generator[str, None, None]:
    print("  [legacy] warming up fax machine...")  # noqa
    time.sleep(0.05)
    yield "fax_ready"
    print("  [legacy] fax machine cooling down")  # noqa


@legacy_suite.test()
def test_send_treat_order_by_fax(fax: Annotated[str, Use(fax_machine)]) -> None:
    time.sleep(0.1)
    assert fax == "fax_ready"


@legacy_suite.test()
def test_receive_vet_appointment_by_fax(fax: Annotated[str, Use(fax_machine)]) -> None:
    time.sleep(0.1)
    assert fax == "fax_ready"


@legacy_suite.test()
def test_fax_grandma_photos_of_yorkies(fax: Annotated[str, Use(fax_machine)]) -> None:
    time.sleep(0.1)
    assert fax == "fax_ready"


# =============================================================================
# FAILING TESTS (to demonstrate error reporting)
# =============================================================================


@session.test()
async def test_yorkshire_math_skills(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    fifi = await factory(name="Fifi", job=Job.INFLUENCER)
    treats_expected = 10
    treats_actual = 7
    assert treats_actual == treats_expected, (
        f"{fifi.name} counted {treats_actual} treats but expected {treats_expected}"
    )


@workers_suite.test()
async def test_chef_cooking_disaster(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    gordon = await factory(name="Gordon", job=Job.CHEF, age=48)
    assert gordon.job == Job.CHEF
    raise ValueError(f"{gordon.name} burned the kitchen down!")


# =============================================================================
# RAISES EXAMPLES (exception assertion)
# =============================================================================


@session.test()
def test_yorkshire_refuses_bath() -> None:
    def give_bath(dog: Yorkshire) -> None:
        if dog.coat == Coat.LONG:
            raise ValueError(f"{dog.name} has escaped through the bathroom window")

    fluffy = Yorkshire(
        name="Fluffy", size=Size.MINI, job=Job.INFLUENCER, age=24, coat=Coat.LONG
    )
    with raises(ValueError):
        give_bath(fluffy)


@session.test()
def test_teacup_weight_limit_exceeded() -> None:
    def feed_treats(dog: Yorkshire, treat_count: int) -> None:
        if dog.size == Size.TEACUP and treat_count > 3:  # noqa
            raise ValueError(f"Too many treats! {dog.name} now spherical")

    tiny = Yorkshire(name="Gizmo", size=Size.TEACUP, job=Job.THERAPIST, age=36)
    with raises(ValueError, match=r"spherical"):
        feed_treats(tiny, treat_count=47)


@session.test()
def test_detective_case_file_missing() -> None:
    case_files: dict[str, str] = {"case_001": "The Missing Squeaky Toy"}

    with raises(KeyError) as exc_info:
        _ = case_files["case_404"]

    assert "case_404" in str(exc_info.value)
    assert exc_info.type is KeyError


@session.test()
async def test_influencer_wifi_outage() -> None:
    async def post_selfie() -> None:
        await asyncio.sleep(0.01)
        raise RuntimeError("No WiFi! Cannot post today's 47th selfie")

    with raises(RuntimeError, match="WiFi"):
        await post_selfie()


@session.test()
def test_chef_recipe_parsing_error() -> None:
    def parse_recipe(instructions: str) -> None:
        raise TypeError(f"Expected kibble recipe, got '{instructions}'")

    with raises(TypeError) as exc_info:
        parse_recipe("human food")

    match_result = exc_info.match(r"Expected (\w+) recipe, got '(.+)'")
    assert match_result.group(1) == "kibble"
    assert match_result.group(2) == "human food"


@session.test()
def test_bodyguard_never_flinches() -> None:
    def startle_dog(dog: Yorkshire) -> None:
        if dog.job != Job.BODYGUARD:
            raise RuntimeError(f"{dog.name} jumped three feet in the air")

    brutus = Yorkshire(name="Brutus", size=Size.STANDARD, job=Job.BODYGUARD, age=48)
    with raises(RuntimeError):
        startle_dog(brutus)


# =============================================================================
# RETRIES EXAMPLES (stubborn yorkshires need multiple attempts)
# =============================================================================


recall_attempts = 0


@session.test(retry=3)
def test_yorkshire_recall_command() -> None:
    """Yorkshire ignores recall command until treats are offered."""
    global recall_attempts  # noqa
    recall_attempts += 1
    if recall_attempts < 3:  # noqa
        raise TimeoutError("Yorkshire pretending to be deaf, investigating squirrel")


wifi_connection_attempts = 0


@session.test(
    retry=Retry(times=2, on=ConnectionError, delay=0.1),
)
async def test_influencer_unstable_wifi(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    """Influencer yorkshire dealing with flaky cafe WiFi."""
    global wifi_connection_attempts  # noqa
    wifi_connection_attempts += 1
    fifi = await factory(name="Fifi", job=Job.INFLUENCER)
    if wifi_connection_attempts < 2:  # noqa
        raise ConnectionError(f"{fifi.name} lost WiFi mid-selfie upload!")
    await asyncio.sleep(0.01)


nap_attempts = 0


@seniors_suite.test(
    timeout=0.15,
    retry=Retry(times=2, on=AssertionError, delay=0.05),
    tags=["senior"],
)
async def test_senior_wakes_up_eventually(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire_factory)],
) -> None:
    """Senior yorkshire takes too long to wake up, but eventually responds."""
    global nap_attempts  # noqa
    nap_attempts += 1
    papy = await factory(name="Papy", age=120, job=Job.THERAPIST)
    if nap_attempts < 2:  # noqa
        await asyncio.sleep(1.0)
    assert papy.is_senior
