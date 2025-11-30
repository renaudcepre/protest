"""Tests for factory fixture wrapping mechanism."""

import pytest

from protest.core.scope import Scope
from protest.di.decorators import fixture, is_factory_fixture
from protest.di.resolver import _wrap_factory
from protest.exceptions import FixtureError


class TestIsFactoryFixture:
    def test_regular_fixture_is_not_factory(self) -> None:
        @fixture(scope=Scope.FUNCTION)
        def regular() -> str:
            return "value"

        assert is_factory_fixture(regular) is False

    def test_factory_fixture_is_factory(self) -> None:
        @fixture(scope=Scope.FUNCTION, factory=True)
        def factory_fixture() -> str:
            return "value"

        assert is_factory_fixture(factory_fixture) is True

    def test_undecorated_function_is_not_factory(self) -> None:
        def plain_func() -> str:
            return "value"

        assert is_factory_fixture(plain_func) is False


class TestWrapFactory:
    def test_wraps_callable_result(self) -> None:
        def my_factory() -> str:
            return "created"

        wrapped = _wrap_factory(my_factory, "test_fixture")
        assert wrapped() == "created"

    def test_non_callable_returned_unchanged(self) -> None:
        result = "not a function"
        wrapped = _wrap_factory(result, "test_fixture")
        assert wrapped is result

    def test_sync_factory_error_becomes_fixture_error(self) -> None:
        def failing_factory() -> None:
            raise ValueError("DB connection failed")

        wrapped = _wrap_factory(failing_factory, "user_factory")

        with pytest.raises(FixtureError) as exc_info:
            wrapped()

        assert exc_info.value.fixture_name == "user_factory"
        assert isinstance(exc_info.value.original, ValueError)
        assert "DB connection failed" in str(exc_info.value.original)

    def test_preserves_function_metadata(self) -> None:
        def documented_factory() -> str:
            """Creates something useful."""
            return "value"

        wrapped = _wrap_factory(documented_factory, "test")
        assert wrapped.__name__ == "documented_factory"
        assert wrapped.__doc__ == "Creates something useful."

    def test_passes_args_and_kwargs(self) -> None:
        def factory_with_args(name: str, role: str = "guest") -> dict[str, str]:
            return {"name": name, "role": role}

        wrapped = _wrap_factory(factory_with_args, "test")
        result = wrapped("alice", role="admin")
        assert result == {"name": "alice", "role": "admin"}


class TestWrapFactoryAsync:
    @pytest.mark.asyncio
    async def test_wraps_async_callable(self) -> None:
        async def async_factory() -> str:
            return "async_created"

        wrapped = _wrap_factory(async_factory, "test_fixture")
        result = await wrapped()
        assert result == "async_created"

    @pytest.mark.asyncio
    async def test_async_factory_error_becomes_fixture_error(self) -> None:
        async def failing_async_factory() -> None:
            raise ConnectionError("API unavailable")

        wrapped = _wrap_factory(failing_async_factory, "api_factory")

        with pytest.raises(FixtureError) as exc_info:
            await wrapped()

        assert exc_info.value.fixture_name == "api_factory"
        assert isinstance(exc_info.value.original, ConnectionError)

    @pytest.mark.asyncio
    async def test_async_preserves_function_metadata(self) -> None:
        async def async_documented() -> str:
            """Async doc."""
            return "value"

        wrapped = _wrap_factory(async_documented, "test")
        assert wrapped.__name__ == "async_documented"
        assert wrapped.__doc__ == "Async doc."
