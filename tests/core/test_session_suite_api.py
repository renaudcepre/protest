"""Tests for the simplified fixture system with global @fixture decorator."""

from typing import Annotated

import pytest

from protest import Scope, fixture
from protest.core.session import ProTestSession
from protest.core.suite import ProTestSuite
from protest.di.markers import Use
from protest.execution.context import TestExecutionContext


class TestSessionSuiteAPI:
    """Tests for the new simplified fixture API."""

    def test_session_and_suite_creation(self) -> None:
        """Basic creation and setup."""
        session = ProTestSession()
        suite_a = ProTestSuite("API Tests")
        suite_b = ProTestSuite("Unit Tests")

        session.include_suite(suite_a)
        session.include_suite(suite_b)

        assert suite_a.name == "API Tests"
        assert suite_b.name == "Unit Tests"
        assert len(session.suites) == 2

    def test_test_registration(self) -> None:
        """Basic test registration should work."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.include_suite(suite_a)

        @session.test()
        def session_test() -> None:
            assert True

        @suite_a.test()
        def suite_test() -> None:
            assert True

        assert len(session.tests) == 1
        assert len(suite_a.tests) == 1
        assert getattr(session.tests[0], "__name__", None) == "session_test"
        assert getattr(suite_a.tests[0], "__name__", None) == "suite_test"


class TestGlobalFixtureDecorator:
    """Tests for the @fixture decorator."""

    @pytest.mark.asyncio
    async def test_session_scoped_fixture_cached_globally(self) -> None:
        """SESSION-scoped fixtures are cached once globally."""
        call_count = 0

        @fixture(scope=Scope.SESSION)
        def database_connection() -> str:
            nonlocal call_count
            call_count += 1
            return f"connection_{call_count}"

        session = ProTestSession()

        async with session:
            result1 = await session.resolver.resolve(database_connection)
            result2 = await session.resolver.resolve(database_connection)

        assert result1 == "connection_1"
        assert result2 == "connection_1"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_suite_scoped_fixture_cached_per_suite(self) -> None:
        """SUITE-scoped fixtures are cached separately per suite."""
        call_count = 0

        @fixture(scope=Scope.SUITE)
        def suite_resource() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        session = ProTestSession()

        async with session:
            result_a1 = await session.resolver.resolve(
                suite_resource, suite_name="suite_a"
            )
            result_a2 = await session.resolver.resolve(
                suite_resource, suite_name="suite_a"
            )
            result_b1 = await session.resolver.resolve(
                suite_resource, suite_name="suite_b"
            )

        assert result_a1 == "resource_1"
        assert result_a2 == "resource_1"
        assert result_b1 == "resource_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_undecorated_function_defaults_to_function_scope(self) -> None:
        """Functions without @fixture decorator are treated as FUNCTION scope."""
        call_count = 0

        def simple_fixture() -> str:
            nonlocal call_count
            call_count += 1
            return f"value_{call_count}"

        session = ProTestSession()

        async with session:
            async with TestExecutionContext(session.resolver) as ctx1:
                result1 = await ctx1.resolve(simple_fixture)
            async with TestExecutionContext(session.resolver) as ctx2:
                result2 = await ctx2.resolve(simple_fixture)

        assert result1 == "value_1"
        assert result2 == "value_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_fixture_with_dependencies(self) -> None:
        """Fixtures can depend on other fixtures via Use()."""

        @fixture(scope=Scope.SESSION)
        def database() -> str:
            return "db_connection"

        @fixture(scope=Scope.SESSION)
        def repository(db: Annotated[str, Use(database)]) -> str:
            return f"Repository({db})"

        session = ProTestSession()

        async with session:
            result = await session.resolver.resolve(repository)

        assert result == "Repository(db_connection)"

    @pytest.mark.asyncio
    async def test_mixed_scope_dependencies(self) -> None:
        """SESSION fixtures can be used by SUITE and FUNCTION scoped fixtures."""

        @fixture(scope=Scope.SESSION)
        def global_config() -> str:
            return "global"

        @fixture(scope=Scope.SUITE)
        def suite_service(cfg: Annotated[str, Use(global_config)]) -> str:
            return f"suite_{cfg}"

        def test_helper(svc: Annotated[str, Use(suite_service)]) -> str:
            return f"test_{svc}"

        session = ProTestSession()

        async with session:
            async with TestExecutionContext(
                session.resolver, suite_name="my_suite"
            ) as ctx:
                result = await ctx.resolve(test_helper)

        assert result == "test_suite_global"


class TestAutouse:
    """Tests for autouse fixtures."""

    @pytest.mark.asyncio
    async def test_autouse_fixtures_resolved_at_session_start(self) -> None:
        """Autouse fixtures are resolved when session starts."""
        setup_done = False

        @fixture(scope=Scope.SESSION)
        def setup_database() -> str:
            nonlocal setup_done
            setup_done = True
            return "initialized"

        session = ProTestSession(autouse=[setup_database])

        assert setup_done is False

        async with session:
            await session.resolve_autouse()
            assert setup_done is True

    @pytest.mark.asyncio
    async def test_autouse_with_dependencies(self) -> None:
        """Autouse fixtures can have dependencies."""
        log: list[str] = []

        @fixture(scope=Scope.SESSION)
        def database() -> str:
            log.append("database")
            return "db"

        @fixture(scope=Scope.SESSION)
        def init_tables(db: Annotated[str, Use(database)]) -> str:
            log.append(f"tables_on_{db}")
            return "tables"

        session = ProTestSession(autouse=[init_tables])

        async with session:
            await session.resolve_autouse()

        assert log == ["database", "tables_on_db"]


class TestSuiteTeardown:
    """Tests for suite-scoped fixture teardown."""

    @pytest.mark.asyncio
    async def test_suite_fixtures_torn_down_after_suite(self) -> None:
        """SUITE-scoped fixtures are torn down when suite ends."""
        teardown_log: list[str] = []

        @fixture(scope=Scope.SUITE)
        def suite_resource() -> str:
            yield "resource"
            teardown_log.append("torn_down")

        session = ProTestSession()

        async with session:
            await session.resolver.resolve(suite_resource, suite_name="test_suite")
            assert teardown_log == []

            await session.resolver.teardown_suite("test_suite")
            assert teardown_log == ["torn_down"]

    @pytest.mark.asyncio
    async def test_suite_cache_cleared_after_teardown(self) -> None:
        """Suite cache is cleared after teardown."""
        call_count = 0

        @fixture(scope=Scope.SUITE)
        def counted_resource() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        session = ProTestSession()

        async with session:
            result1 = await session.resolver.resolve(
                counted_resource, suite_name="suite"
            )
            assert result1 == "resource_1"

            await session.resolver.teardown_suite("suite")

            result2 = await session.resolver.resolve(
                counted_resource, suite_name="suite"
            )
            assert result2 == "resource_2"

        assert call_count == 2
