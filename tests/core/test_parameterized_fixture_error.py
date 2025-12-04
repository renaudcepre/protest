"""Test that From() in fixtures raises ParameterizedFixtureError."""

from typing import Annotated

import pytest

from protest import ForEach, From, ProTestSession, ProTestSuite, factory, fixture
from protest.exceptions import ParameterizedFixtureError

ROLES = ForEach(["admin", "guest"])


class TestSessionFixture:
    def test_fixture_with_from_raises_error(self) -> None:
        session = ProTestSession()

        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @session.fixture()
            def bad_fixture(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_fixture" in str(exc_info.value)
        assert "role" in str(exc_info.value)
        assert "From() is only allowed in tests" in str(exc_info.value)

    def test_factory_with_from_raises_error(self) -> None:
        session = ProTestSession()

        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @session.factory()
            def bad_factory(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_factory" in str(exc_info.value)


class TestSuiteFixture:
    def test_fixture_with_from_raises_error(self) -> None:
        suite = ProTestSuite("test")

        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @suite.fixture()
            def bad_fixture(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_fixture" in str(exc_info.value)

    def test_factory_with_from_raises_error(self) -> None:
        suite = ProTestSuite("test")

        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @suite.factory()
            def bad_factory(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_factory" in str(exc_info.value)


class TestStandaloneDecorators:
    def test_fixture_with_from_raises_error(self) -> None:
        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @fixture()
            def bad_fixture(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_fixture" in str(exc_info.value)

    def test_factory_with_from_raises_error(self) -> None:
        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @factory()
            def bad_factory(role: Annotated[str, From(ROLES)]) -> dict[str, str]:
                return {"role": role}

        assert "bad_factory" in str(exc_info.value)


class TestMultipleFromParams:
    def test_error_lists_all_params(self) -> None:
        session = ProTestSession()
        methods = ForEach(["GET", "POST"])

        with pytest.raises(ParameterizedFixtureError) as exc_info:

            @session.fixture()
            def bad_fixture(
                role: Annotated[str, From(ROLES)],
                method: Annotated[str, From(methods)],
            ) -> dict[str, str]:
                return {"role": role, "method": method}

        error_message = str(exc_info.value)
        assert "role" in error_message
        assert "method" in error_message


class TestValidFixtures:
    def test_fixture_without_from_works(self) -> None:
        session = ProTestSession()

        @session.fixture()
        def good_fixture() -> str:
            return "ok"

        assert len(session.fixtures) == 1

    def test_factory_without_from_works(self) -> None:
        session = ProTestSession()

        @session.factory()
        def good_factory(name: str) -> dict[str, str]:
            return {"name": name}

        assert len(session.fixtures) == 1
