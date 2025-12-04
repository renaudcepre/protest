"""Tests for the tree-based scoping fixture system."""

from collections.abc import Generator
from typing import Annotated

import pytest

from protest import ProTestSession, ProTestSuite, Use
from protest.di.decorators import fixture
from protest.exceptions import PlainFunctionError
from protest.execution.context import TestExecutionContext


class TestSessionSuiteAPI:
    """Tests for session and suite API."""

    def test_session_and_suite_creation(self) -> None:
        """Basic creation and setup."""
        session = ProTestSession()
        suite_a = ProTestSuite("API Tests")
        suite_b = ProTestSuite("Unit Tests")

        session.add_suite(suite_a)
        session.add_suite(suite_b)

        assert suite_a.name == "API Tests"
        assert suite_b.name == "Unit Tests"
        assert len(session.suites) == 2

    def test_test_registration(self) -> None:
        """Basic test registration should work."""
        session = ProTestSession()
        suite_a = ProTestSuite("Suite A")
        session.add_suite(suite_a)

        @session.test()
        def session_test() -> None:
            assert True

        @suite_a.test()
        def suite_test() -> None:
            assert True

        assert len(session.tests) == 1
        assert len(suite_a.tests) == 1
        assert session.tests[0].func.__name__ == "session_test"
        assert suite_a.tests[0].func.__name__ == "suite_test"

    def test_nested_suite_full_path(self) -> None:
        """Nested suites have correct full_path."""
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        grandchild = ProTestSuite("GrandChild")

        parent.add_suite(child)
        child.add_suite(grandchild)

        assert parent.full_path == "Parent"
        assert child.full_path == "Parent::Child"
        assert grandchild.full_path == "Parent::Child::GrandChild"


class TestTreeBasedScoping:
    """Tests for the tree-based scoping system."""

    @pytest.mark.asyncio
    async def test_session_scoped_fixture_cached_globally(self) -> None:
        """SESSION-scoped fixtures are cached once globally."""
        call_count = 0

        session = ProTestSession()

        @session.fixture()
        def database_connection() -> str:
            nonlocal call_count
            call_count += 1
            return f"connection_{call_count}"

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

        session = ProTestSession()
        suite_a = ProTestSuite("suite_a")
        suite_b = ProTestSuite("suite_b")
        session.add_suite(suite_a)
        session.add_suite(suite_b)

        @suite_a.fixture()
        def suite_resource_a() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        @suite_b.fixture()
        def suite_resource_b() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        async with session:
            result_a1 = await session.resolver.resolve(
                suite_resource_a, current_path="suite_a"
            )
            result_a2 = await session.resolver.resolve(
                suite_resource_a, current_path="suite_a"
            )
            result_b1 = await session.resolver.resolve(
                suite_resource_b, current_path="suite_b"
            )

        assert result_a1 == "resource_1"
        assert result_a2 == "resource_1"
        assert result_b1 == "resource_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_undecorated_function_raises_error(self) -> None:
        """Plain functions without @fixture()/@factory() raise PlainFunctionError."""

        def simple_fixture() -> str:
            return "value"

        session = ProTestSession()

        async with session, TestExecutionContext(session.resolver) as ctx:
            with pytest.raises(PlainFunctionError) as exc_info:
                await ctx.resolve(simple_fixture)

        assert "simple_fixture" in str(exc_info.value)
        assert "@fixture()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fixture_with_dependencies(self) -> None:
        """Fixtures can depend on other fixtures via Use()."""
        session = ProTestSession()

        @session.fixture()
        def database() -> str:
            return "db_connection"

        @session.fixture()
        def repository(db: Annotated[str, Use(database)]) -> str:
            return f"Repository({db})"

        async with session:
            result = await session.resolver.resolve(repository)

        assert result == "Repository(db_connection)"

    @pytest.mark.asyncio
    async def test_mixed_scope_dependencies(self) -> None:
        """SESSION fixtures can be used by SUITE and FUNCTION scoped fixtures."""
        # Given: session with nested scope fixtures (session -> suite -> function)
        session = ProTestSession()
        my_suite = ProTestSuite("my_suite")
        session.add_suite(my_suite)

        @session.fixture()
        def global_config() -> str:
            return "global"

        @my_suite.fixture()
        def suite_service(cfg: Annotated[str, Use(global_config)]) -> str:
            return f"suite_{cfg}"

        @fixture()
        def test_helper(svc: Annotated[str, Use(suite_service)]) -> str:
            return f"test_{svc}"

        # When: resolving function-scoped fixture that depends on suite and session
        async with (
            session,
            TestExecutionContext(session.resolver, suite_path="my_suite") as ctx,
        ):
            result = await ctx.resolve(test_helper)

        # Then: dependencies resolved correctly through scope hierarchy
        assert result == "test_suite_global"


class TestAutouse:
    """Tests for autouse fixtures."""

    @pytest.mark.asyncio
    async def test_autouse_fixtures_resolved_at_session_start(self) -> None:
        """Autouse fixtures are resolved when session starts."""
        setup_done = False

        @fixture()
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

        @fixture()
        def database() -> str:
            log.append("database")
            return "db"

        @fixture()
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

        session = ProTestSession()
        test_suite = ProTestSuite("test_suite")
        session.add_suite(test_suite)

        @test_suite.fixture()
        def suite_resource() -> Generator[str, None, None]:
            yield "resource"
            teardown_log.append("torn_down")

        async with session:
            await session.resolver.resolve(suite_resource, current_path="test_suite")
            assert teardown_log == []

            await session.resolver.teardown_suite("test_suite")
            assert teardown_log == ["torn_down"]

    @pytest.mark.asyncio
    async def test_suite_cache_cleared_after_teardown(self) -> None:
        """Suite cache is cleared after teardown."""
        call_count = 0

        session = ProTestSession()
        suite = ProTestSuite("suite")
        session.add_suite(suite)

        @suite.fixture()
        def counted_resource() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        async with session:
            result1 = await session.resolver.resolve(
                counted_resource, current_path="suite"
            )
            assert result1 == "resource_1"

            await session.resolver.teardown_suite("suite")

            result2 = await session.resolver.resolve(
                counted_resource, current_path="suite"
            )
            assert result2 == "resource_2"

        assert call_count == 2


class TestNestedSuites:
    """Tests for nested suite functionality."""

    @pytest.mark.asyncio
    async def test_nested_suite_can_use_parent_fixture(self) -> None:
        """Child suite can depend on parent suite's fixtures."""
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @parent.fixture()
        def parent_resource() -> str:
            return "parent_data"

        @child.fixture()
        def child_resource(
            parent: Annotated[str, Use(parent_resource)],
        ) -> str:
            return f"child_using_{parent}"

        async with session:
            result = await session.resolver.resolve(
                child_resource, current_path="Parent::Child"
            )

        assert result == "child_using_parent_data"

    @pytest.mark.asyncio
    async def test_child_suite_can_use_session_fixture(self) -> None:
        """Deeply nested suite can use session fixtures."""
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @session.fixture()
        def session_resource() -> str:
            return "session_data"

        @child.fixture()
        def child_resource(
            sess: Annotated[str, Use(session_resource)],
        ) -> str:
            return f"child_using_{sess}"

        async with session:
            result = await session.resolver.resolve(
                child_resource, current_path="Parent::Child"
            )

        assert result == "child_using_session_data"
