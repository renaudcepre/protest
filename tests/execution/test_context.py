"""Tests for TestExecutionContext - parallel execution isolation."""

from typing import Annotated

import pytest

from protest.di.container import FixtureContainer
from protest.di.markers import Use
from protest.entities import FixtureScope
from protest.execution.context import TestExecutionContext


@pytest.fixture
def resolver() -> FixtureContainer:
    return FixtureContainer()


class TestFunctionScopeIsolation:
    """FUNCTION-scoped fixtures should be isolated per TestExecutionContext."""

    @pytest.mark.asyncio
    async def test_function_fixture_isolated_between_contexts(
        self, resolver: FixtureContainer
    ) -> None:
        """Each context gets its own instance of FUNCTION-scoped fixtures."""
        call_count = 0

        def counter_fixture() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        resolver.register(counter_fixture, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx1:
            value1 = await ctx1.resolve(counter_fixture)

        async with TestExecutionContext(resolver) as ctx2:
            value2 = await ctx2.resolve(counter_fixture)

        assert value1 == 1
        assert value2 == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_function_fixture_cached_within_same_context(
        self, resolver: FixtureContainer
    ) -> None:
        """Same context returns cached value for repeated resolves."""
        call_count = 0

        def counter_fixture() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        resolver.register(counter_fixture, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx:
            value1 = await ctx.resolve(counter_fixture)
            value2 = await ctx.resolve(counter_fixture)

        assert value1 == 1
        assert value2 == 1
        assert call_count == 1


class TestSessionScopeDelegation:
    """SESSION-scoped fixtures should delegate to parent resolver."""

    @pytest.mark.asyncio
    async def test_session_fixture_shared_across_contexts(
        self, resolver: FixtureContainer
    ) -> None:
        """SESSION fixtures are resolved by parent and shared."""
        call_count = 0

        def session_fixture() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        resolver.register(session_fixture, scope=FixtureScope.SESSION)

        async with resolver:
            async with TestExecutionContext(resolver) as ctx1:
                value1 = await ctx1.resolve(session_fixture)

            async with TestExecutionContext(resolver) as ctx2:
                value2 = await ctx2.resolve(session_fixture)

        assert value1 == 1
        assert value2 == 1
        assert call_count == 1


class TestTeardown:
    """Teardown should happen correctly when context exits."""

    @pytest.mark.asyncio
    async def test_function_generator_teardown_on_context_exit(
        self, resolver: FixtureContainer
    ) -> None:
        """Generator fixtures teardown when context exits."""
        teardown_called = False

        def generator_fixture():
            yield "value"
            nonlocal teardown_called
            teardown_called = True

        resolver.register(generator_fixture, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx:
            value = await ctx.resolve(generator_fixture)
            assert value == "value"
            assert not teardown_called

        assert teardown_called

    @pytest.mark.asyncio
    async def test_async_generator_teardown(self, resolver: FixtureContainer) -> None:
        """Async generator fixtures teardown correctly."""
        teardown_called = False

        async def async_generator_fixture():
            yield "async_value"
            nonlocal teardown_called
            teardown_called = True

        resolver.register(async_generator_fixture, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx:
            value = await ctx.resolve(async_generator_fixture)
            assert value == "async_value"
            assert not teardown_called

        assert teardown_called

    @pytest.mark.asyncio
    async def test_multiple_fixtures_teardown_in_order(
        self, resolver: FixtureContainer
    ) -> None:
        """Multiple fixtures teardown in reverse order."""
        teardown_order: list[str] = []

        def fixture_a():
            yield "a"
            teardown_order.append("a")

        def fixture_b():
            yield "b"
            teardown_order.append("b")

        resolver.register(fixture_a, scope=FixtureScope.TEST)
        resolver.register(fixture_b, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx:
            await ctx.resolve(fixture_a)
            await ctx.resolve(fixture_b)

        assert teardown_order == ["b", "a"]


class TestDependencyResolution:
    """Dependencies should be resolved correctly through context."""

    @pytest.mark.asyncio
    async def test_function_fixture_with_function_dependency(
        self, resolver: FixtureContainer
    ) -> None:
        """FUNCTION fixture can depend on another FUNCTION fixture."""

        def base_fixture() -> str:
            return "base"

        def dependent_fixture(base: str) -> str:
            return f"dependent_{base}"

        resolver.register(base_fixture, scope=FixtureScope.TEST)

        def dependent_with_annotation(
            base: Annotated[str, Use(base_fixture)],
        ) -> str:
            return f"dependent_{base}"

        resolver.register(dependent_with_annotation, scope=FixtureScope.TEST)

        async with TestExecutionContext(resolver) as ctx:
            value = await ctx.resolve(dependent_with_annotation)

        assert value == "dependent_base"

    @pytest.mark.asyncio
    async def test_function_fixture_with_session_dependency(
        self, resolver: FixtureContainer
    ) -> None:
        """FUNCTION fixture can depend on SESSION fixture."""

        def session_fixture() -> str:
            return "session_value"

        resolver.register(session_fixture, scope=FixtureScope.SESSION)

        def function_fixture(
            session: Annotated[str, Use(session_fixture)],
        ) -> str:
            return f"function_{session}"

        resolver.register(function_fixture, scope=FixtureScope.TEST)

        async with resolver, TestExecutionContext(resolver) as ctx:
            value = await ctx.resolve(function_fixture)

        assert value == "function_session_value"


class TestSuiteScopeDelegation:
    """SUITE-scoped fixtures should delegate to parent resolver."""

    @pytest.mark.asyncio
    async def test_suite_fixture_shared_within_suite(self, resolver: FixtureContainer) -> None:
        """SUITE fixtures are resolved by parent and shared within suite."""
        call_count = 0

        def suite_fixture() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        resolver.register(suite_fixture, scope=FixtureScope.SUITE)

        async with resolver:
            async with TestExecutionContext(resolver, suite_path="MySuite") as ctx1:
                value1 = await ctx1.resolve(suite_fixture)

            async with TestExecutionContext(resolver, suite_path="MySuite") as ctx2:
                value2 = await ctx2.resolve(suite_fixture)

        assert value1 == 1
        assert value2 == 1
        assert call_count == 1
