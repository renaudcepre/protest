"""Edge case tests for DI module to achieve 100% coverage."""

import asyncio
import functools
from contextlib import AsyncExitStack
from typing import Annotated, Any

import pytest

from protest import ProTestSession, Use
from protest.api import run_session
from protest.di.decorators import fixture
from protest.di.factory import FixtureFactory
from protest.di.hashable import make_hashable
from protest.di.proxy import SafeProxy
from protest.di.resolver import Resolver
from protest.entities import Fixture
from protest.events.bus import EventBus
from protest.exceptions import (
    FixtureNotFoundError,
    ScopeMismatchError,
    UnregisteredDependencyError,
)
from protest.execution.async_bridge import is_async_callable


class TestHashableEdgeCases:
    """Edge cases for make_hashable."""

    def test_dict_with_non_sortable_keys(self) -> None:
        """Dict with keys that can't be sorted falls back to list order."""
        # Create a dict with mixed types that can't be sorted
        # (int and str keys cause TypeError in Python 3)
        mixed_dict: dict[Any, str] = {1: "one", "two": "2"}

        # Should not raise, should use list(keys()) instead of sorted()
        result = make_hashable(mixed_dict)

        # Result is a tuple of (key, value) pairs
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestSafeProxyEdgeCases:
    """Edge cases for SafeProxy."""

    @pytest.mark.asyncio
    async def test_proxy_with_async_call(self) -> None:
        """SafeProxy handles target with async __call__."""

        class AsyncCallable:
            async def __call__(self, x: int) -> int:
                return x * 2

        proxy = SafeProxy(AsyncCallable(), "async_factory")
        result = await proxy(5)
        assert result == 10


class TestFixtureFactoryEdgeCases:
    """Edge cases for FixtureFactory."""

    @pytest.mark.asyncio
    async def test_cache_hit_inside_lock(self) -> None:
        """Test double-checked locking - cache hit inside lock."""

        call_count = 0

        def slow_factory(name: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"instance_{name}"

        fixture_obj = Fixture(func=slow_factory)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory = FixtureFactory(
                fixture=fixture_obj,
                fixture_name="slow_factory",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            # Simulate concurrent calls hitting the lock
            # First call creates the instance
            result1 = await factory(name="test")
            assert result1 == "instance_test"
            assert call_count == 1

            # Create multiple concurrent tasks
            tasks = [factory(name="test") for _ in range(3)]
            results = await asyncio.gather(*tasks)

            # All should return same cached value
            assert all(r == "instance_test" for r in results)
            assert call_count == 1  # Only called once


class TestFixtureWrapperEdgeCases:
    """Edge cases for FixtureWrapper."""

    def test_fixture_wrapper_callable(self) -> None:
        """FixtureWrapper is callable and returns function result."""

        @fixture()
        def my_fixture(x: int, y: int = 10) -> int:
            return x + y

        # FixtureWrapper should be callable
        result = my_fixture(5)
        assert result == 15

        result2 = my_fixture(5, y=20)
        assert result2 == 25


class TestResolverEdgeCases:
    """Edge cases for Resolver."""

    def test_resolver_event_bus_property(self) -> None:
        """event_bus property returns the configured event bus."""

        bus = EventBus()
        resolver = Resolver(event_bus=bus)
        assert resolver.event_bus is bus

        resolver_no_bus = Resolver(event_bus=None)
        assert resolver_no_bus.event_bus is None

    def test_get_dependencies_unwrapped(self) -> None:
        """get_dependencies works with wrapped and unwrapped fixtures."""
        resolver = Resolver()

        @fixture()
        def dep_fixture() -> str:
            return "dep"

        @fixture()
        def main_fixture(d: Annotated[str, Use(dep_fixture)]) -> str:
            return d

        resolver.register(dep_fixture.func)
        resolver.register(main_fixture.func)

        # Get dependencies using the wrapper
        deps = resolver.get_dependencies(main_fixture)
        assert "d" in deps

        # Get dependencies using the unwrapped function
        deps2 = resolver.get_dependencies(main_fixture.func)
        assert "d" in deps2

    def test_session_fixture_depends_on_suite_raises(self) -> None:
        """Session fixture depending on suite fixture raises ScopeMismatchError."""
        resolver = Resolver()

        @fixture()
        def suite_resource() -> str:
            return "suite_data"

        @fixture()
        def bad_session_fixture(
            res: Annotated[str, Use(suite_resource)],
        ) -> str:
            return res

        # Register suite fixture first (at suite scope)
        resolver.register(suite_resource.func, scope_path="MySuite")

        # Try to register session fixture that depends on suite fixture
        # This should fail - session fixture can't depend on suite fixture
        with pytest.raises(ScopeMismatchError) as exc_info:
            resolver.register(bad_session_fixture.func, scope_path=None)

        assert "session" in str(exc_info.value)
        assert "MySuite" in str(exc_info.value)


class TestFixtureClearCache:
    """Test Fixture.clear_cache method."""

    def test_fixture_clear_cache(self) -> None:
        """Fixture.clear_cache resets cached_value and is_cached."""
        fixture_obj = Fixture(func=lambda: "value")

        # Simulate caching
        fixture_obj.cached_value = "cached_result"
        fixture_obj.is_cached = True

        assert fixture_obj.cached_value == "cached_result"
        assert fixture_obj.is_cached is True

        # Clear cache
        fixture_obj.clear_cache()

        assert fixture_obj.cached_value is None
        assert fixture_obj.is_cached is False


class TestExceptionsInit:
    """Test exception constructors."""

    def test_unregistered_dependency_error(self) -> None:
        """UnregisteredDependencyError message format."""
        exc = UnregisteredDependencyError("my_fixture", "unknown_dep")
        assert "my_fixture" in str(exc)
        assert "unknown_dep" in str(exc)
        assert "unregistered" in str(exc).lower()

    def test_fixture_not_found_error(self) -> None:
        """FixtureNotFoundError message format."""
        exc = FixtureNotFoundError("missing_fixture")
        assert "missing_fixture" in str(exc)
        assert "not registered" in str(exc).lower()


class TestAsyncBridgeEdgeCases:
    """Edge cases for async_bridge module."""

    def test_is_async_callable_with_partial(self) -> None:
        """is_async_callable unwraps functools.partial."""

        async def async_func(x: int, y: int) -> int:
            return x + y

        def sync_func(x: int, y: int) -> int:
            return x + y

        # Plain functions
        assert is_async_callable(async_func) is True
        assert is_async_callable(sync_func) is False

        # Wrapped in partial
        partial_async = functools.partial(async_func, 1)
        partial_sync = functools.partial(sync_func, 1)

        assert is_async_callable(partial_async) is True
        assert is_async_callable(partial_sync) is False

        # Nested partials
        nested_partial = functools.partial(partial_async, y=2)
        assert is_async_callable(nested_partial) is True


class TestApiForceNoColor:
    """Test api.py force_no_color branch."""

    def test_run_session_with_force_no_color(self) -> None:
        """run_session with force_no_color=True uses ASCII reporter."""

        session = ProTestSession()
        executed: list[str] = []

        @session.test()
        def simple_test() -> None:
            executed.append("ran")

        result = run_session(session, force_no_color=True)

        assert result.success is True
        assert executed == ["ran"]
