"""ProTest Demo - Skip functionality."""

from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use

session = ProTestSession()
api_suite = ProTestSuite("API Tests")
session.add_suite(api_suite)


@session.fixture()
def database() -> str:
    return "db_connection"


@session.test()
def test_that_runs() -> None:
    assert True


@session.test(skip=True)
def test_skipped_with_default_reason() -> None:
    raise AssertionError("This should never run")


@session.test(skip="WIP: authentication refactor in progress")
def test_skipped_with_custom_reason() -> None:
    raise AssertionError("This should never run")


@session.test(skip="TODO: waiting for external API")
def test_external_integration(db: Annotated[str, Use(database)]) -> None:
    raise AssertionError("This should never run")


@api_suite.test()
def test_api_that_runs() -> None:
    assert True


@api_suite.test(skip="Known flaky on CI")
def test_flaky_api_call() -> None:
    raise AssertionError("This should never run")
