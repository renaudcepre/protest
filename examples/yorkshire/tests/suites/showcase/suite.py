"""Feature showcase - ForEach, mocker, caplog, raises, warns, Retry.

This module demonstrates advanced ProTest features in one place.
"""

import asyncio
import warnings
from typing import Annotated

from examples.yorkshire.app.domain import Coat, Job, Size, Yorkshire
from examples.yorkshire.app.services import GroomingService, VetService
from examples.yorkshire.tests.fixtures import grooming_quote, yorkshire
from protest import (
    FixtureFactory,
    ForEach,
    From,
    Mocker,
    ProTestSuite,
    Retry,
    Skip,
    Use,
    caplog,
    fixture,
    mocker,
    raises,
    warns,
)
from protest.entities import LogCapture

showcase_suite = ProTestSuite(
    "Showcase",
    tags=["showcase"],
    description="Feature demonstrations: ForEach, mocker, caplog, raises, warns, Retry",
)


# =============================================================================
# PARAMETERIZATION (ForEach / From)
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


@showcase_suite.test()
def test_grooming_price_matrix(
    size: Annotated[Size, From(SIZES)],
    coat: Annotated[Coat, From(COATS)],
    quote: Annotated[dict[str, float], Use(grooming_quote)],
) -> None:
    """Cartesian product: Size x Coat = 6 test variations."""
    dog = Yorkshire(name="Matrix", size=size, job=Job.UNEMPLOYED, age=24, coat=coat)
    price = quote["base"]
    if coat == Coat.LONG:
        price += quote["long_coat_extra"]
    assert price > 0
    assert dog.needs_grooming == (coat == Coat.LONG)


@showcase_suite.test()
async def test_job_variations(
    job: Annotated[Job, From(JOBS)],
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    """Single ForEach: 5 job variations."""
    worker = await factory(name="Worker", job=job, age=24)
    assert worker.can_work


# =============================================================================
# MOCKER (patch, spy)
# =============================================================================


@showcase_suite.test()
def test_vet_checkup_with_mock(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Mock a method return value."""
    vet = VetService()
    dog = Yorkshire(name="Patient", size=Size.MINI, job=Job.UNEMPLOYED, age=24)

    mock_checkup = mock.patch.object(vet, "checkup")
    mock_checkup.return_value = {"healthy": True, "weight": 2.8}

    result = vet.checkup(dog)

    assert result["healthy"] is True
    mock_checkup.assert_called_once_with(dog)


@showcase_suite.test()
async def test_grooming_appointment_with_mock(
    mock: Annotated[Mocker, Use(mocker)],
) -> None:
    """Mock an async method."""
    grooming = GroomingService()
    dog = Yorkshire(name="Fluffy", size=Size.STANDARD, job=Job.INFLUENCER, age=36)

    mock_schedule = mock.patch.object(grooming, "schedule_appointment")
    mock_schedule.return_value = "APT-FLU-20251225"

    result = await grooming.schedule_appointment(dog, "2025-12-25")

    assert result == "APT-FLU-20251225"
    mock_schedule.assert_called_once_with(dog, "2025-12-25")


@showcase_suite.test()
def test_spy_real_method(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Spy calls real method but tracks invocations."""
    vet = VetService()
    dog = Yorkshire(name="Spied", size=Size.TEACUP, job=Job.THERAPIST, age=18)

    spy = mock.spy(vet.checkup)

    result = vet.checkup(dog)

    assert result["healthy"] is True
    spy.assert_called_once_with(dog)
    assert spy.spy_return == result


# =============================================================================
# CAPLOG (log capture)
# =============================================================================


@showcase_suite.test()
async def test_kennel_logs_additions(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
    logs: Annotated[LogCapture, Use(caplog)],
) -> None:
    """Capture log output during test."""
    await factory(name="Logger")
    assert "Logger" in logs.text


# =============================================================================
# RAISES (exception assertions)
# =============================================================================


@showcase_suite.test()
def test_yorkshire_refuses_bath() -> None:
    """Basic raises usage."""

    def give_bath(dog: Yorkshire) -> None:
        if dog.coat == Coat.LONG:
            raise ValueError(f"{dog.name} has escaped through the bathroom window")

    fluffy = Yorkshire(
        name="Fluffy", size=Size.MINI, job=Job.INFLUENCER, age=24, coat=Coat.LONG
    )
    with raises(ValueError):
        give_bath(fluffy)


@showcase_suite.test()
def test_raises_with_match_pattern() -> None:
    """Raises with regex match."""

    def feed_treats(dog: Yorkshire, count: int) -> None:
        if dog.size == Size.TEACUP and count > 3:  # noqa: PLR2004
            raise ValueError(f"Too many treats! {dog.name} now spherical")

    tiny = Yorkshire(name="Gizmo", size=Size.TEACUP, job=Job.THERAPIST, age=36)
    with raises(ValueError, match=r"spherical"):
        feed_treats(tiny, count=47)


@showcase_suite.test()
def test_raises_captures_exception_info() -> None:
    """Access exception details via exc_info."""
    case_files: dict[str, str] = {"case_001": "The Missing Squeaky Toy"}

    with raises(KeyError) as exc_info:
        _ = case_files["case_404"]

    assert "case_404" in str(exc_info.value)
    assert exc_info.type is KeyError


@showcase_suite.test()
def test_raises_with_match_groups() -> None:
    """Extract groups from match pattern."""

    def parse_recipe(instructions: str) -> None:
        raise TypeError(f"Expected kibble recipe, got '{instructions}'")

    with raises(TypeError) as exc_info:
        parse_recipe("human food")

    match_result = exc_info.match(r"Expected (\w+) recipe, got '(.+)'")
    assert match_result.group(1) == "kibble"
    assert match_result.group(2) == "human food"


@showcase_suite.test()
async def test_raises_async() -> None:
    """Raises works with async code."""

    async def post_selfie() -> None:
        await asyncio.sleep(0.01)
        raise RuntimeError("No WiFi! Cannot post today's 47th selfie")

    with raises(RuntimeError, match="WiFi"):
        await post_selfie()


# =============================================================================
# WARNS (warning assertions)
# =============================================================================


def old_grooming_algorithm(dog: Yorkshire) -> int:
    """Deprecated grooming price calculator."""
    warnings.warn(
        "old_grooming_algorithm is deprecated, use calculate_grooming_price instead",
        DeprecationWarning,
        stacklevel=2,
    )
    base = 30
    if dog.coat == Coat.LONG:
        base += 15
    return base


@showcase_suite.test()
def test_deprecated_grooming_function() -> None:
    """Basic warns usage: catch deprecation warnings."""
    dog = Yorkshire(name="Scruffy", size=Size.MINI, job=Job.UNEMPLOYED, age=24)

    with warns(DeprecationWarning):
        old_grooming_algorithm(dog)


@showcase_suite.test()
def test_warns_with_match_pattern() -> None:
    """Warns with regex match."""
    dog = Yorkshire(name="Bruno", size=Size.STANDARD, job=Job.BODYGUARD, age=48)

    with warns(DeprecationWarning, match=r"deprecated.*calculate_grooming_price"):
        old_grooming_algorithm(dog)


@showcase_suite.test()
def test_warns_captures_multiple() -> None:
    """Capture and inspect multiple warnings."""

    def risky_operation(dog: Yorkshire) -> str:
        warnings.warn(f"{dog.name} is getting nervous", UserWarning, stacklevel=2)
        warnings.warn(
            f"Low treat reserves for {dog.name}", ResourceWarning, stacklevel=2
        )
        return "survived"

    fluffy = Yorkshire(name="Fluffy", size=Size.TEACUP, job=Job.THERAPIST, age=18)

    with warns() as record:
        result = risky_operation(fluffy)

    assert result == "survived"
    expected_warning_count = 2
    assert len(record) == expected_warning_count
    assert record[0].category is UserWarning
    assert "nervous" in str(record[0].message)
    assert record[1].category is ResourceWarning


# =============================================================================
# RETRY (flaky test handling)
# =============================================================================

recall_attempts = 0


@showcase_suite.test(retry=3)
def test_recall_command_with_retry() -> None:
    """Simple retry: retries up to 3 times on any exception."""
    global recall_attempts  # noqa: PLW0603
    recall_attempts += 1
    if recall_attempts < 3:  # noqa: PLR2004
        raise TimeoutError("Yorkshire pretending to be deaf, investigating squirrel")


wifi_attempts = 0


@showcase_suite.test(retry=Retry(times=2, on=ConnectionError, delay=0.1))
async def test_retry_with_specific_exception(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    """Retry only on ConnectionError, with delay between attempts."""
    global wifi_attempts  # noqa: PLW0603
    wifi_attempts += 1
    fifi = await factory(name="Fifi", job=Job.INFLUENCER)
    if wifi_attempts < 2:  # noqa: PLR2004
        raise ConnectionError(f"{fifi.name} lost WiFi mid-selfie upload!")


# =============================================================================
# FAILING TESTS (error reporting demo)
# =============================================================================


@showcase_suite.test()
async def test_yorkshire_math_skills(
    factory: Annotated[FixtureFactory[Yorkshire], Use(yorkshire)],
) -> None:
    """Intentionally failing test for error reporting demo."""
    fifi = await factory(name="Fifi", job=Job.INFLUENCER)
    treats_expected = 10
    treats_actual = 7
    assert treats_actual == treats_expected, (
        f"{fifi.name} counted {treats_actual} treats but expected {treats_expected}"
    )


# =============================================================================
# CONDITIONAL SKIP (skip with callable condition)
# =============================================================================


@fixture()
def feature_flags() -> dict[str, bool]:
    """Feature flags from environment/config."""
    return {
        "new_grooming_algorithm": True,  # Would be from env/config in real code
        "premium_treats": False,
    }


showcase_suite.bind(feature_flags)


@showcase_suite.test(
    skip=lambda feature_flags: not feature_flags["new_grooming_algorithm"],
    skip_reason="Feature flag 'new_grooming_algorithm' not enabled",
)
def test_runtime_conditional_skip_with_fixture(
    feature_flags: Annotated[dict[str, bool], Use(feature_flags)],
) -> None:
    """Runtime conditional skip: condition callable receives fixture values.

    Note: The parameter name must match what the skip callable expects.
    """
    assert feature_flags["new_grooming_algorithm"]


@showcase_suite.test(
    skip=Skip(
        condition=lambda feature_flags: not feature_flags["premium_treats"],
        reason="Premium treats feature disabled",
    ),
)
def test_skip_object_form(
    feature_flags: Annotated[dict[str, bool], Use(feature_flags)],
) -> None:
    """Skip object with condition: explicit condition + reason.

    This test will be SKIPPED because premium_treats is False.
    """
    assert feature_flags["premium_treats"]
