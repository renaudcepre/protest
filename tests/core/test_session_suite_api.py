"""TDD Tests for Session/Suite API with "allowlist" architecture.

These tests define the desired behavior before implementation.
Architecture: Single global resolver + explicit fixture visibility lists.
"""

from typing import Annotated

import pytest

from protest.core.scope import Scope
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.di.markers import Use
from protest.di.resolver import UnregisteredDependencyError


class TestSessionSuiteAPI:
    """Define the desired API and behavior through failing tests."""

    def test_session_and_suite_creation(self) -> None:
        """Basic creation and setup."""
        # Should be able to create session and suites
        session = ProTestSession()
        suite_a = ProTestSuite("API Tests")
        suite_b = ProTestSuite("Unit Tests")

        # Should be able to include suites
        session.include_suite(suite_a)
        session.include_suite(suite_b)

        assert suite_a.name == "API Tests"
        assert suite_b.name == "Unit Tests"
        assert len(session.suites) == 2

    @pytest.mark.asyncio
    async def test_session_fixture_visible_everywhere(self) -> None:
        """Session fixtures should be visible to all suites."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        @session.fixture(scope=Scope.SESSION)
        def database_url() -> str:
            return "postgresql://localhost/test"

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_service(db_url: Annotated[str, Use(database_url)]) -> str:
            return f"ServiceA with {db_url}"

        @suite_b.fixture(scope=Scope.FUNCTION)
        def suite_b_service(db_url: Annotated[str, Use(database_url)]) -> str:
            return f"ServiceB with {db_url}"

        result_a = await suite_a.resolve_fixture(suite_a_service)
        result_b = await suite_b.resolve_fixture(suite_b_service)

        assert result_a == "ServiceA with postgresql://localhost/test"
        assert result_b == "ServiceB with postgresql://localhost/test"

    def test_suite_fixture_isolation(self) -> None:
        """Suite fixtures should NOT be visible to other suites."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_data() -> str:
            return "private_data_A"

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_processed(data: Annotated[str, Use(suite_a_data)]) -> str:
            return f"processed_{data}"

        with pytest.raises(UnregisteredDependencyError):

            @suite_b.fixture(scope=Scope.FUNCTION)
            def suite_b_illegal(data: Annotated[str, Use(suite_a_data)]) -> str:
                return f"illegal_{data}"

    def test_suite_cannot_define_session_scope(self) -> None:
        """Suites should not be allowed to define SESSION-scoped fixtures."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.include_suite(suite_a)

        with pytest.raises(Exception) as exc_info:

            @suite_a.fixture(scope=Scope.SESSION)
            def illegal_session_fixture() -> str:
                return "this should fail"

        assert "session" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_unified_cache_across_suites(self) -> None:
        """SESSION fixtures should be cached once and reused across suites."""
        call_count = 0

        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        @session.fixture(scope=Scope.SESSION)
        def expensive_resource() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_service(res: Annotated[str, Use(expensive_resource)]) -> str:
            return f"A_{res}"

        @suite_b.fixture(scope=Scope.FUNCTION)
        def suite_b_service(res: Annotated[str, Use(expensive_resource)]) -> str:
            return f"B_{res}"

        result_a = await suite_a.resolve_fixture(suite_a_service)
        result_b = await suite_b.resolve_fixture(suite_b_service)

        assert result_a == "A_resource_1"
        assert result_b == "B_resource_1"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_fixture_resolution_context(self) -> None:
        """Each suite should have its own resolution context."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        @session.fixture(scope=Scope.SESSION)
        def global_config() -> dict[str, str]:
            return {"env": "test"}

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.SUITE)
        def suite_a_config(
            config: Annotated[dict[str, str], Use(global_config)],
        ) -> dict[str, str]:
            return {**config, "suite": "A"}

        @suite_b.fixture(scope=Scope.SUITE)
        def suite_b_config(
            config: Annotated[dict[str, str], Use(global_config)],
        ) -> dict[str, str]:
            return {**config, "suite": "B"}

        result_a = await suite_a.resolve_fixture(suite_a_config)
        result_b = await suite_b.resolve_fixture(suite_b_config)

        assert result_a == {"env": "test", "suite": "A"}
        assert result_b == {"env": "test", "suite": "B"}

        with pytest.raises(UnregisteredDependencyError):
            await suite_a.resolve_fixture(suite_b_config)

    def test_test_registration(self) -> None:
        """Basic test registration should work."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.include_suite(suite_a)

        @session.test
        def session_test() -> None:
            assert True

        @suite_a.test
        def suite_test() -> None:
            assert True

        assert len(session.tests) == 1
        assert len(suite_a.tests) == 1
        assert getattr(session.tests[0], "__name__", None) == "session_test"
        assert getattr(suite_a.tests[0], "__name__", None) == "suite_test"

    @pytest.mark.asyncio
    async def test_complex_dependency_chain(self) -> None:
        """Complex dependencies across session and suite levels."""
        session = ProTestSession()
        suite_a = ProTestSuite("API Suite")

        @session.fixture(scope=Scope.SESSION)
        def database_pool() -> str:
            return "pool_connection"

        @session.fixture(scope=Scope.SESSION)
        def cache_client() -> str:
            return "redis_client"

        session.include_suite(suite_a)

        @suite_a.fixture(scope=Scope.SUITE)
        def user_repository(db: Annotated[str, Use(database_pool)]) -> str:
            return f"UserRepo({db})"

        @suite_a.fixture(scope=Scope.SUITE)
        def user_service(
            repo: Annotated[str, Use(user_repository)],
            cache: Annotated[str, Use(cache_client)],
        ) -> str:
            return f"UserService({repo}, {cache})"

        @suite_a.fixture(scope=Scope.FUNCTION)
        def test_user(service: Annotated[str, Use(user_service)]) -> str:
            return f"TestUser via {service}"

        result = await suite_a.resolve_fixture(test_user)
        expected = "TestUser via UserService(UserRepo(pool_connection), redis_client)"
        assert result == expected
