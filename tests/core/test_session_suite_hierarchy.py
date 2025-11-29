"""TDD tests for Session/Suite hierarchy."""

from typing import Annotated

import pytest

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite, SuiteFixtureScopeError
from protest.di.markers import Use
from protest.di.resolver import UnregisteredDependencyError


class TestSessionSuiteHierarchy:
    """Test the session/suite hierarchy and fixture visibility rules."""

    @pytest.mark.asyncio
    async def test_session_fixture_visible_in_suite(self) -> None:
        """Suite can use session-level fixtures."""
        session = ProTestSession()
        suite = ProTestSuite("test_suite")

        @session.fixture(scope=Scope.SESSION)
        def session_data() -> str:
            return "session_value"

        session.include_suite(suite)

        @suite.fixture(scope=Scope.FUNCTION)
        def suite_data(data: Annotated[str, Use(session_data)]) -> str:
            return f"suite_{data}"

        result = await suite.resolver.resolve(suite_data)
        assert result == "suite_session_value"

    def test_suite_fixture_not_visible_from_other_suite(self) -> None:
        """Suite A cannot access fixtures from Suite B."""
        session = ProTestSession()
        suite_a = ProTestSuite("suite_a")
        suite_b = ProTestSuite("suite_b")

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_data() -> str:
            return "suite_a_value"

        with pytest.raises(UnregisteredDependencyError):

            @suite_b.fixture(scope=Scope.FUNCTION)
            def suite_b_data(data: Annotated[str, Use(suite_a_data)]) -> str:
                return f"suite_b_{data}"

    def test_suite_cannot_define_session_scope_fixture(self) -> None:
        """Suite cannot register fixtures with SESSION scope."""
        session = ProTestSession()
        suite = ProTestSuite("test_suite")
        session.include_suite(suite)

        with pytest.raises(
            SuiteFixtureScopeError, match="cannot define SESSION-scoped fixture"
        ):

            @suite.fixture(scope=Scope.SESSION)
            def invalid_fixture() -> str:
                return "invalid"

    def test_suite_fixture_before_include_fails(self) -> None:
        """Cannot register suite fixtures before including in session."""
        suite = ProTestSuite("test_suite")

        with pytest.raises(RuntimeError, match="must be attached to a session"):

            @suite.fixture(scope=Scope.FUNCTION)
            def early_fixture() -> str:
                return "too_early"

    @pytest.mark.asyncio
    async def test_mixed_scope_hierarchy(self) -> None:
        """Test complex hierarchy with mixed scopes."""
        session = ProTestSession()
        suite = ProTestSuite("test_suite")

        @session.fixture(scope=Scope.SESSION)
        def global_config() -> dict[str, str]:
            return {"env": "test"}

        @session.fixture(scope=Scope.SESSION)
        def session_temp() -> str:
            return "temp_data"

        session.include_suite(suite)

        @suite.fixture(scope=Scope.SUITE)
        def suite_service(
            config: Annotated[dict[str, str], Use(global_config)],
            temp: Annotated[str, Use(session_temp)],
        ) -> str:
            return f"service_{config['env']}_{temp}"

        @suite.fixture(scope=Scope.FUNCTION)
        def test_data(service: Annotated[str, Use(suite_service)]) -> str:
            return f"test_{service}"

        result = await suite.resolver.resolve(test_data)
        assert result == "test_service_test_temp_data"

    @pytest.mark.asyncio
    async def test_cache_isolation_between_suites(self) -> None:
        """Cache is isolated between different suites."""
        session = ProTestSession()
        suite_a = ProTestSuite("suite_a")
        suite_b = ProTestSuite("suite_b")

        call_count = 0

        @session.fixture(scope=Scope.SESSION)
        def shared_session_fixture() -> str:
            nonlocal call_count
            call_count += 1
            return f"shared_{call_count}"

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_fixture(shared: Annotated[str, Use(shared_session_fixture)]) -> str:
            return f"a_{shared}"

        @suite_b.fixture(scope=Scope.FUNCTION)
        def suite_b_fixture(shared: Annotated[str, Use(shared_session_fixture)]) -> str:
            return f"b_{shared}"

        result_a = await suite_a.resolver.resolve(suite_a_fixture)
        result_b = await suite_b.resolver.resolve(suite_b_fixture)

        assert result_a == "a_shared_1"
        assert result_b == "b_shared_1"
        assert call_count == 1
