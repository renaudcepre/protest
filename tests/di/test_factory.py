"""Tests for FixtureFactory class."""

from contextlib import AsyncExitStack
from dataclasses import dataclass

import pytest

from protest.di.factory import FixtureFactory
from protest.entities import Fixture
from protest.exceptions import FixtureError


@dataclass
class User:
    username: str
    role: str = "guest"


class TestFixtureFactoryBasic:
    @pytest.mark.asyncio
    async def test_creates_instance_with_kwargs(self) -> None:
        def user_fixture(username: str, role: str = "guest") -> User:
            return User(username=username, role=role)

        fixture = Fixture(func=user_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            user = await factory(username="alice", role="admin")

            assert user.username == "alice"
            assert user.role == "admin"

    @pytest.mark.asyncio
    async def test_caches_by_kwargs_when_enabled(self) -> None:
        call_count = 0

        def user_fixture(username: str) -> User:
            nonlocal call_count
            call_count += 1
            return User(username=username)

        fixture = Fixture(func=user_fixture, is_factory=True, cache=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            user1 = await factory(username="alice")
            user2 = await factory(username="alice")
            user3 = await factory(username="bob")

            assert user1 is user2
            assert user1 is not user3
            expected_call_count = 2
            assert call_count == expected_call_count

    @pytest.mark.asyncio
    async def test_no_cache_when_disabled(self) -> None:
        call_count = 0

        def user_fixture(username: str) -> User:
            nonlocal call_count
            call_count += 1
            return User(username=username)

        fixture = Fixture(func=user_fixture, is_factory=True, cache=False)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=False,
            )

            user1 = await factory(username="alice")
            user2 = await factory(username="alice")

            assert user1 is not user2
            expected_call_count = 2
            assert call_count == expected_call_count


class TestFixtureFactoryWithGenerator:
    @pytest.mark.asyncio
    async def test_generator_teardown_called(self) -> None:
        teardown_called = []

        def user_fixture(username: str) -> User:
            user = User(username=username)
            yield user
            teardown_called.append(username)

        fixture = Fixture(func=user_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            await factory(username="alice")
            await factory(username="bob")

            assert len(teardown_called) == 0

        expected_teardown_count = 2
        assert len(teardown_called) == expected_teardown_count
        assert "alice" in teardown_called
        assert "bob" in teardown_called

    @pytest.mark.asyncio
    async def test_async_generator_teardown_called(self) -> None:
        teardown_called = []

        async def user_fixture(username: str) -> User:
            user = User(username=username)
            yield user
            teardown_called.append(username)

        fixture = Fixture(func=user_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            await factory(username="alice")

        expected_teardown_count = 1
        assert len(teardown_called) == expected_teardown_count


class TestFixtureFactoryErrors:
    @pytest.mark.asyncio
    async def test_error_becomes_fixture_error(self) -> None:
        def failing_fixture(username: str) -> User:
            raise ValueError("DB connection failed")

        fixture = Fixture(func=failing_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user_factory",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            with pytest.raises(FixtureError) as exc_info:
                await factory(username="alice")

            assert exc_info.value.fixture_name == "user_factory"
            assert isinstance(exc_info.value.original, ValueError)
            assert "DB connection failed" in str(exc_info.value.original)

    @pytest.mark.asyncio
    async def test_unhashable_kwargs_raises_type_error(self) -> None:
        def fixture_with_list(items: list[str]) -> str:
            return ",".join(items)

        fixture = Fixture(func=fixture_with_list, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[str] = FixtureFactory(
                fixture=fixture,
                fixture_name="test",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            with pytest.raises(TypeError) as exc_info:
                await factory(items=["a", "b"])

            assert "unhashable kwargs" in str(exc_info.value)


class TestFixtureFactoryWithDependencies:
    @pytest.mark.asyncio
    async def test_merges_resolved_dependencies_with_user_kwargs(self) -> None:
        def user_fixture(db_connection: str, username: str) -> dict[str, str]:
            return {"db": db_connection, "user": username}

        fixture = Fixture(func=user_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[dict[str, str]] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={"db_connection": "postgres://localhost"},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            result = await factory(username="alice")

            assert result["db"] == "postgres://localhost"
            assert result["user"] == "alice"


class TestFixtureFactoryAsync:
    @pytest.mark.asyncio
    async def test_async_fixture_function(self) -> None:
        async def async_user_fixture(username: str) -> User:
            return User(username=username)

        fixture = Fixture(func=async_user_fixture, is_factory=True)
        exit_stack = AsyncExitStack()

        async with exit_stack:
            factory: FixtureFactory[User] = FixtureFactory(
                fixture=fixture,
                fixture_name="user",
                resolved_dependencies={},
                exit_stack=exit_stack,
                cache_enabled=True,
            )

            user = await factory(username="alice")

            assert user.username == "alice"
