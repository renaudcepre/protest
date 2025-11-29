"""TDD Tests for Session/Suite API with "allowlist" architecture.

These tests define the desired behavior before implementation.
Architecture: Single global resolver + explicit fixture visibility lists.

These tests are skipped until ProTestSession and ProTestSuite are implemented.
"""

pytest = __import__("pytest")
pytest.skip("ProTestSession/ProTestSuite not yet implemented", allow_module_level=True)

from typing import Annotated  # noqa: E402

from protest.core.scope import Scope  # noqa: E402
from protest.core.session import ProTestSession  # noqa: E402
from protest.core.suite import ProTestSuite  # noqa: E402
from protest.di.markers import Use  # noqa: E402
from protest.di.resolver import UnregisteredDependencyError  # noqa: E402


class TestSessionSuiteAPI:
    """Define the desired API and behavior through failing tests."""

    def test_session_and_suite_creation(self):
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

    def test_session_fixture_visible_everywhere(self):
        """Session fixtures should be visible to all suites."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        # Session defines a global fixture
        @session.fixture(scope=Scope.SESSION)
        def database_url() -> str:
            return "postgresql://localhost/test"

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        # Both suites should be able to use session fixture
        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_service(db_url: Annotated[str, Use(database_url)]) -> str:
            return f"ServiceA with {db_url}"

        @suite_b.fixture(scope=Scope.FUNCTION)
        def suite_b_service(db_url: Annotated[str, Use(database_url)]) -> str:
            return f"ServiceB with {db_url}"

        # Should be able to resolve fixtures from both suites
        result_a = suite_a.resolve_fixture(suite_a_service)
        result_b = suite_b.resolve_fixture(suite_b_service)

        assert result_a == "ServiceA with postgresql://localhost/test"
        assert result_b == "ServiceB with postgresql://localhost/test"

    def test_suite_fixture_isolation(self):
        """Suite fixtures should NOT be visible to other suites."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        # Suite A defines its own fixture
        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_data() -> str:
            return "private_data_A"

        # Suite A can use its own fixture
        @suite_a.fixture(scope=Scope.FUNCTION)
        def suite_a_processed(data: Annotated[str, Use(suite_a_data)]) -> str:
            return f"processed_{data}"

        # Suite B tries to use Suite A's fixture - should fail
        with pytest.raises(Exception) as exc_info:

            @suite_b.fixture(scope=Scope.FUNCTION)
            def suite_b_illegal(data: Annotated[str, Use(suite_a_data)]) -> str:
                return f"illegal_{data}"

        assert (
            "not visible" in str(exc_info.value).lower()
            or "not allowed" in str(exc_info.value).lower()
        )

    def test_suite_cannot_define_session_scope(self):
        """Suites should not be allowed to define SESSION-scoped fixtures."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.include_suite(suite_a)

        # Should fail when suite tries to define SESSION fixture
        with pytest.raises(Exception) as exc_info:

            @suite_a.fixture(scope=Scope.SESSION)
            def illegal_session_fixture() -> str:
                return "this should fail"

        assert "session" in str(exc_info.value).lower()

    def test_unified_cache_across_suites(self):
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

        # Both suites use the same cached SESSION fixture
        result_a = suite_a.resolve_fixture(suite_a_service)
        result_b = suite_b.resolve_fixture(suite_b_service)

        assert result_a == "A_resource_1"
        assert result_b == "B_resource_1"
        assert call_count == 1  # Called only once, cached for both

    def test_fixture_resolution_context(self):
        """Each suite should have its own resolution context."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        suite_b = ProTestSuite("Suite B")

        @session.fixture(scope=Scope.SESSION)
        def global_config() -> dict:
            return {"env": "test"}

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        @suite_a.fixture(scope=Scope.SUITE)
        def suite_a_config(config: Annotated[dict, Use(global_config)]) -> dict:
            return {**config, "suite": "A"}

        @suite_b.fixture(scope=Scope.SUITE)
        def suite_b_config(config: Annotated[dict, Use(global_config)]) -> dict:
            return {**config, "suite": "B"}

        # Each suite should resolve its own fixtures independently
        result_a = suite_a.resolve_fixture(suite_a_config)
        result_b = suite_b.resolve_fixture(suite_b_config)

        assert result_a == {"env": "test", "suite": "A"}
        assert result_b == {"env": "test", "suite": "B"}

        # Suite A cannot access Suite B's config
        with pytest.raises(UnregisteredDependencyError):
            suite_a.resolve_fixture(suite_b_config)

    def test_test_registration(self):
        """Basic test registration should work."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.include_suite(suite_a)

        @session.test
        def session_test():
            assert True

        @suite_a.test
        def suite_test():
            assert True

        assert len(session.tests) == 1
        assert len(suite_a.tests) == 1
        assert session.tests[0].__name__ == "session_test"
        assert suite_a.tests[0].__name__ == "suite_test"

    def test_complex_dependency_chain(self):
        """Complex dependencies across session and suite levels."""
        session = ProTestSession()
        suite_a = ProTestSuite("API Suite")

        # Session-level foundation
        @session.fixture(scope=Scope.SESSION)
        def database_pool() -> str:
            return "pool_connection"

        @session.fixture(scope=Scope.SESSION)
        def cache_client() -> str:
            return "redis_client"

        session.include_suite(suite_a)

        # Suite-level services that depend on session fixtures
        @suite_a.fixture(scope=Scope.SUITE)
        def user_repository(db: Annotated[str, Use(database_pool)]) -> str:
            return f"UserRepo({db})"

        @suite_a.fixture(scope=Scope.SUITE)
        def user_service(
            repo: Annotated[str, Use(user_repository)],
            cache: Annotated[str, Use(cache_client)],
        ) -> str:
            return f"UserService({repo}, {cache})"

        # Function-level test fixture
        @suite_a.fixture(scope=Scope.FUNCTION)
        def test_user(service: Annotated[str, Use(user_service)]) -> str:
            return f"TestUser via {service}"

        result = suite_a.resolve_fixture(test_user)
        expected = "TestUser via UserService(UserRepo(pool_connection), redis_client)"
        assert result == expected
