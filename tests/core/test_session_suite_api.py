"""Tests for the Scope at Binding fixture system."""

from collections.abc import Generator
from typing import Annotated

import pytest

from protest import ProTestSession, ProTestSuite, Use
from protest.core.runner import TestRunner
from protest.di.decorators import factory, fixture
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

    def test_suite_description(self) -> None:
        """Suite can have an optional description."""
        suite_with_desc = ProTestSuite(
            "API", description="Integration tests for REST API"
        )
        suite_without_desc = ProTestSuite("Unit")

        assert suite_with_desc.description == "Integration tests for REST API"
        assert suite_without_desc.description is None


class TestScopeAtBinding:
    """Tests for the Scope at Binding system."""

    @pytest.mark.asyncio
    async def test_session_scoped_fixture_cached_globally(self) -> None:
        """SESSION-scoped fixtures are cached once globally."""
        call_count = 0

        session = ProTestSession()

        @fixture()
        def database_connection() -> str:
            nonlocal call_count
            call_count += 1
            return f"connection_{call_count}"

        session.fixture(database_connection)  # SESSION scope

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

        @fixture()
        def suite_resource_a() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        suite_a.fixture(suite_resource_a)  # SUITE scope

        @fixture()
        def suite_resource_b() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        suite_b.fixture(suite_resource_b)  # SUITE scope

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

        @fixture()
        def database() -> str:
            return "db_connection"

        session.fixture(database)  # SESSION scope

        @fixture()
        def repository(db: Annotated[str, Use(database)]) -> str:
            return f"Repository({db})"

        session.fixture(repository)  # SESSION scope

        async with session:
            result = await session.resolver.resolve(repository)

        assert result == "Repository(db_connection)"

    @pytest.mark.asyncio
    async def test_mixed_scope_dependencies(self) -> None:
        """SESSION fixtures can be used by SUITE and TEST scoped fixtures."""
        # Given: session with nested scope fixtures (session -> suite -> test)
        session = ProTestSession()
        my_suite = ProTestSuite("my_suite")
        session.add_suite(my_suite)

        @fixture()
        def global_config() -> str:
            return "global"

        session.fixture(global_config)  # SESSION scope

        @fixture()
        def suite_service(cfg: Annotated[str, Use(global_config)]) -> str:
            return f"suite_{cfg}"

        my_suite.fixture(suite_service)  # SUITE scope

        @fixture()
        def test_helper(svc: Annotated[str, Use(suite_service)]) -> str:
            return f"test_{svc}"

        # test_helper is not bound → TEST scope by default

        # When: resolving test-scoped fixture that depends on suite and session
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
    async def test_session_autouse_resolved_at_session_start(self) -> None:
        """Session autouse fixtures are resolved when session starts."""
        setup_done = False
        session = ProTestSession()

        @fixture()
        def setup_database() -> str:
            nonlocal setup_done
            setup_done = True
            return "initialized"

        session.fixture(setup_database, autouse=True)  # SESSION + autouse

        assert setup_done is False

        async with session:
            await session.resolve_autouse()
            assert setup_done is True

    @pytest.mark.asyncio
    async def test_session_autouse_with_dependencies(self) -> None:
        """Session autouse fixtures can have dependencies on session fixtures."""
        log: list[str] = []
        session = ProTestSession()

        @fixture()
        def database() -> str:
            log.append("database")
            return "db"

        session.fixture(database)  # SESSION scope

        @fixture()
        def init_tables(db: Annotated[str, Use(database)]) -> str:
            log.append(f"tables_on_{db}")
            return "tables"

        session.fixture(init_tables, autouse=True)  # SESSION + autouse

        async with session:
            await session.resolve_autouse()

        assert log == ["database", "tables_on_db"]

    @pytest.mark.asyncio
    async def test_suite_autouse_resolved_when_suite_starts(self) -> None:
        """Suite autouse fixtures are resolved when suite starts."""
        log: list[str] = []
        session = ProTestSession()
        suite = ProTestSuite("TestSuite")
        session.add_suite(suite)

        @fixture()
        def suite_setup() -> str:
            log.append("suite_setup")
            return "setup"

        suite.fixture(suite_setup, autouse=True)  # SUITE + autouse

        async with session:
            assert log == []
            await session.resolver.resolve_suite_autouse("TestSuite")
            assert log == ["suite_setup"]

    @pytest.mark.asyncio
    async def test_suite_autouse_can_use_session_fixture(self) -> None:
        """Suite autouse fixtures can depend on session fixtures."""
        log: list[str] = []
        session = ProTestSession()
        suite = ProTestSuite("TestSuite")
        session.add_suite(suite)

        @fixture()
        def database() -> str:
            log.append("database")
            return "db"

        session.fixture(database)  # SESSION scope

        @fixture()
        def suite_init(db: Annotated[str, Use(database)]) -> str:
            log.append(f"suite_init_{db}")
            return "init"

        suite.fixture(suite_init, autouse=True)  # SUITE + autouse

        async with session:
            await session.resolve_autouse()
            await session.resolver.resolve_suite_autouse("TestSuite")

        assert log == ["database", "suite_init_db"]

    @pytest.mark.asyncio
    async def test_suite_autouse_teardown_with_suite(self) -> None:
        """Suite autouse fixtures are torn down with the suite."""
        teardown_log: list[str] = []
        session = ProTestSession()
        suite = ProTestSuite("TestSuite")
        session.add_suite(suite)

        @fixture()
        def suite_resource() -> Generator[str, None, None]:
            yield "resource"
            teardown_log.append("torn_down")

        suite.fixture(suite_resource, autouse=True)  # SUITE + autouse

        async with session:
            await session.resolver.resolve_suite_autouse("TestSuite")
            assert teardown_log == []
            await session.resolver.teardown_suite("TestSuite")
            assert teardown_log == ["torn_down"]

    @pytest.mark.asyncio
    async def test_nested_suite_autouse_cached_per_owner(self) -> None:
        """Suite autouse fixtures are cached per owner suite (Scope at Binding).

        With Scope at Binding, SUITE-scoped autouse fixtures are:
        - Resolved when their owner suite (or descendant) starts
        - Cached by owner suite path, not by current test path
        - Accessible by child suites via ancestry check
        """
        call_counts: dict[str, int] = {"parent": 0, "child": 0}
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @fixture()
        def parent_setup() -> str:
            call_counts["parent"] += 1
            return "parent"

        parent.fixture(parent_setup, autouse=True)  # SUITE + autouse

        @fixture()
        def child_setup() -> str:
            call_counts["child"] += 1
            return "child"

        child.fixture(child_setup, autouse=True)  # SUITE + autouse

        async with session:
            # Resolve autouse for parent suite - only parent_setup runs
            await session.resolver.resolve_suite_autouse("Parent")
            # Resolve autouse for child suite - child_setup runs,
            # parent_setup is already cached (owner "Parent")
            await session.resolver.resolve_suite_autouse("Parent::Child")

        # Each fixture runs once (cached by owner suite)
        assert call_counts["parent"] == 1  # Runs for "Parent", cached
        assert call_counts["child"] == 1  # Runs for "Parent::Child", cached


class TestSuiteTeardown:
    """Tests for suite-scoped fixture teardown."""

    @pytest.mark.asyncio
    async def test_suite_fixtures_torn_down_after_suite(self) -> None:
        """SUITE-scoped fixtures are torn down when suite ends."""
        teardown_log: list[str] = []

        session = ProTestSession()
        test_suite = ProTestSuite("test_suite")
        session.add_suite(test_suite)

        @fixture()
        def suite_resource() -> Generator[str, None, None]:
            yield "resource"
            teardown_log.append("torn_down")

        test_suite.fixture(suite_resource)  # SUITE scope

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

        @fixture()
        def counted_resource() -> str:
            nonlocal call_count
            call_count += 1
            return f"resource_{call_count}"

        suite.fixture(counted_resource)  # SUITE scope

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

        @fixture()
        def parent_resource() -> str:
            return "parent_data"

        parent.fixture(parent_resource)  # SUITE scope

        @fixture()
        def child_resource(
            parent: Annotated[str, Use(parent_resource)],
        ) -> str:
            return f"child_using_{parent}"

        child.fixture(child_resource)  # SUITE scope

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

        @fixture()
        def session_resource() -> str:
            return "session_data"

        session.fixture(session_resource)  # SESSION scope

        @fixture()
        def child_resource(
            sess: Annotated[str, Use(session_resource)],
        ) -> str:
            return f"child_using_{sess}"

        child.fixture(child_resource)  # SUITE scope

        async with session:
            result = await session.resolver.resolve(
                child_resource, current_path="Parent::Child"
            )

        assert result == "child_using_session_data"


class TestSuiteFactory:
    @pytest.mark.asyncio
    async def test_suite_factory_basic(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("MySuite")
        session.add_suite(suite)

        @factory()
        def user_factory(name: str) -> Generator[str, None, None]:
            yield f"user_{name}"

        suite.fixture(user_factory)  # SUITE scope

        async with session:
            factory_inst = await session.resolver.resolve(
                user_factory, current_path="MySuite"
            )
            user = await factory_inst(name="alice")

        assert user == "user_alice"

    @pytest.mark.asyncio
    async def test_suite_factory_with_cache_false(self) -> None:
        call_count = 0
        session = ProTestSession()
        suite = ProTestSuite("MySuite")
        session.add_suite(suite)

        @factory(cache=False)
        def uncached_factory(tag: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"instance_{call_count}_{tag}"

        suite.fixture(uncached_factory)  # SUITE scope

        async with session:
            factory_inst = await session.resolver.resolve(
                uncached_factory, current_path="MySuite"
            )
            result1 = await factory_inst(tag="a")
            result2 = await factory_inst(tag="b")

        expected_call_count = 2
        assert call_count == expected_call_count
        assert result1 != result2

    @pytest.mark.asyncio
    async def test_suite_factory_with_managed_false(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("MySuite")
        session.add_suite(suite)

        class UserFactory:
            def create(self, name: str) -> str:
                return f"user_{name}"

        @factory(managed=False)
        def user_factory() -> UserFactory:
            return UserFactory()

        suite.fixture(user_factory)  # SUITE scope

        async with session:
            factory_inst = await session.resolver.resolve(
                user_factory, current_path="MySuite"
            )
            user = factory_inst.create(name="bob")

        assert user == "user_bob"


class TestSuiteAddAfterAttach:
    def test_add_suite_after_session_attach(self) -> None:
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        session.add_suite(parent)

        child = ProTestSuite("Child")
        parent.add_suite(child)

        assert child._parent_suite is parent
        assert child._session is session

    def test_add_deeply_nested_after_attach(self) -> None:
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        session.add_suite(parent)

        child = ProTestSuite("Child")
        grandchild = ProTestSuite("GrandChild")
        child.add_suite(grandchild)
        parent.add_suite(child)

        assert child._session is session
        assert grandchild._session is session
        assert grandchild.full_path == "Parent::Child::GrandChild"


class TestFixtureBinding:
    """Tests for session.fixture() and suite.fixture() API."""

    @pytest.mark.asyncio
    async def test_session_fixture_binds_to_session_scope(self) -> None:
        """session.fixture() binds a fixture to SESSION scope."""

        @fixture()
        def config() -> str:
            return "session_config"

        session = ProTestSession()
        session.fixture(config)  # SESSION scope

        async with session:
            result = await session.resolver.resolve(config)

        assert result == "session_config"

    @pytest.mark.asyncio
    async def test_session_fixture_with_autouse(self) -> None:
        """session.fixture(fn, autouse=True) auto-resolves at session start."""

        setup_done = False

        @fixture()
        def auto_setup() -> str:
            nonlocal setup_done
            setup_done = True
            return "initialized"

        session = ProTestSession()
        session.fixture(auto_setup, autouse=True)  # SESSION + autouse

        assert setup_done is False

        async with session:
            await session.resolve_autouse()
            assert setup_done is True

    @pytest.mark.asyncio
    async def test_suite_fixture_binds_to_suite_scope(self) -> None:
        """suite.fixture() binds a fixture to SUITE scope."""

        @fixture()
        def suite_resource() -> str:
            return "suite_data"

        session = ProTestSession()
        suite = ProTestSuite("TestSuite")
        suite.fixture(suite_resource)  # SUITE scope
        session.add_suite(suite)

        async with session:
            result = await session.resolver.resolve(
                suite_resource, current_path="TestSuite"
            )

        assert result == "suite_data"

    def test_fixture_rejects_undecorated_function(self) -> None:
        """fixture() raises on plain functions without @fixture()."""

        def plain_func() -> str:
            return "plain"

        session = ProTestSession()

        with pytest.raises(ValueError, match="not decorated"):
            session.fixture(plain_func)


class TestNestedSuiteFixtureLifetime:
    """Tests for fixture lifetime in nested suite scenarios.

    These tests verify that parent suite fixtures remain alive while
    child suites are executing, and are only torn down after all
    children complete.
    """

    def test_parent_fixture_created_once_across_parent_and_child_tests(self) -> None:
        """Parent suite fixture should be created ONCE, reused by child suites.

        The SuiteTracker now counts tests hierarchically, ensuring parent
        suites only complete after all child suite tests are done.
        """

        call_count = 0

        session = ProTestSession(concurrency=1)
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @fixture()
        def parent_resource() -> Generator[str, None, None]:
            nonlocal call_count
            call_count += 1
            yield f"resource_{call_count}"

        parent.fixture(parent_resource)  # SUITE scope

        # Test in parent suite that uses the fixture
        @parent.test()
        def test_in_parent(res: Annotated[str, Use(parent_resource)]) -> None:
            # Just use the fixture, don't assert on value
            assert res.startswith("resource_")

        # Test in child suite that also uses parent's fixture
        @child.test()
        def test_in_child(res: Annotated[str, Use(parent_resource)]) -> None:
            # Just use the fixture, don't assert on value
            assert res.startswith("resource_")

        runner = TestRunner(session)
        result = runner.run()

        # Tests themselves should pass (they just check fixture exists)
        assert result.success is True, "Tests failed unexpectedly"

        # Parent fixture should only be created ONCE
        assert call_count == 1, (
            f"Parent fixture was created {call_count} times, expected 1. "
            "This indicates the parent suite is being torn down prematurely "
            "before child suites complete."
        )

    def test_parent_fixture_teardown_order_is_child_first(self) -> None:
        """Teardown should happen in reverse order: child fixtures before parent."""

        teardown_order: list[str] = []

        session = ProTestSession(concurrency=1)
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @fixture()
        def parent_resource() -> Generator[str, None, None]:
            yield "parent"
            teardown_order.append("parent")

        parent.fixture(parent_resource)  # SUITE scope

        @fixture()
        def child_resource(
            p: Annotated[str, Use(parent_resource)],
        ) -> Generator[str, None, None]:
            yield f"child_of_{p}"
            teardown_order.append("child")

        child.fixture(child_resource)  # SUITE scope

        @parent.test()
        def test_in_parent(res: Annotated[str, Use(parent_resource)]) -> None:
            assert res == "parent"

        @child.test()
        def test_in_child(res: Annotated[str, Use(child_resource)]) -> None:
            assert res == "child_of_parent"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

        # Teardown order should be LIFO: child first, then parent
        assert teardown_order == ["child", "parent"], (
            f"Teardown order was {teardown_order}, expected ['child', 'parent']. "
            "Child fixtures must be torn down before parent fixtures."
        )
