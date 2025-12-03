"""Tests for SafeProxy class."""

import pytest

from protest.di.proxy import SafeProxy
from protest.exceptions import FixtureError


class FakeUserFactory:
    """A fake factory class for testing."""

    def __init__(self, db: str) -> None:
        self.db = db
        self.created: list[dict[str, str]] = []

    def create(self, name: str, role: str = "guest") -> dict[str, str]:
        if name == "crash":
            raise ValueError("Database connection lost")
        user = {"name": name, "role": role, "db": self.db}
        self.created.append(user)
        return user

    def create_many(self, count: int) -> list[dict[str, str]]:
        return [self.create(f"user_{idx}") for idx in range(count)]


class AsyncFakeFactory:
    """A fake factory with async methods."""

    async def create(self, name: str) -> dict[str, str]:
        if name == "crash":
            raise RuntimeError("Async error")
        return {"name": name}


class CallableFakeFactory:
    """A factory that is directly callable."""

    def __call__(self, name: str) -> dict[str, str]:
        if name == "crash":
            raise ValueError("Call error")
        return {"name": name}


class TestSafeProxyBasic:
    def test_proxy_passes_through_successful_call(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        user = proxy.create(name="alice", role="admin")

        assert user["name"] == "alice"
        assert user["role"] == "admin"
        assert user["db"] == "test_db"

    def test_proxy_wraps_error_in_fixture_error(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        with pytest.raises(FixtureError) as exc_info:
            proxy.create(name="crash")

        assert exc_info.value.fixture_name == "user_factory"
        assert isinstance(exc_info.value.original, ValueError)
        assert "Database connection lost" in str(exc_info.value.original)

    def test_proxy_passes_through_attributes(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        assert proxy.db == "test_db"

    def test_proxy_allows_setting_attributes(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        proxy.db = "new_db"

        assert factory.db == "new_db"


class TestSafeProxyMultipleMethods:
    def test_proxy_wraps_all_methods(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        users = proxy.create_many(count=3)

        expected_count = 3
        assert len(users) == expected_count

    def test_different_methods_error_wrapped(self) -> None:
        factory = FakeUserFactory(db="test_db")
        proxy: SafeProxy[FakeUserFactory] = SafeProxy(factory, "user_factory")

        factory.create_many = lambda count: (_ for _ in ()).throw(RuntimeError("boom"))

        with pytest.raises(FixtureError) as exc_info:
            proxy.create_many(count=1)

        assert exc_info.value.fixture_name == "user_factory"


class TestSafeProxyAsync:
    @pytest.mark.asyncio
    async def test_async_method_success(self) -> None:
        factory = AsyncFakeFactory()
        proxy: SafeProxy[AsyncFakeFactory] = SafeProxy(factory, "async_factory")

        result = await proxy.create(name="alice")

        assert result["name"] == "alice"

    @pytest.mark.asyncio
    async def test_async_method_error_wrapped(self) -> None:
        factory = AsyncFakeFactory()
        proxy: SafeProxy[AsyncFakeFactory] = SafeProxy(factory, "async_factory")

        with pytest.raises(FixtureError) as exc_info:
            await proxy.create(name="crash")

        assert exc_info.value.fixture_name == "async_factory"
        assert isinstance(exc_info.value.original, RuntimeError)


class TestSafeProxyCallable:
    def test_callable_factory_success(self) -> None:
        factory = CallableFakeFactory()
        proxy: SafeProxy[CallableFakeFactory] = SafeProxy(factory, "callable_factory")

        result = proxy(name="alice")

        assert result["name"] == "alice"

    def test_callable_factory_error_wrapped(self) -> None:
        factory = CallableFakeFactory()
        proxy: SafeProxy[CallableFakeFactory] = SafeProxy(factory, "callable_factory")

        with pytest.raises(FixtureError) as exc_info:
            proxy(name="crash")

        assert exc_info.value.fixture_name == "callable_factory"


class TestSafeProxyDoesNotDoubleWrap:
    def test_fixture_error_not_double_wrapped(self) -> None:
        """If method already raises FixtureError, don't wrap again."""

        class FactoryThatRaisesFixtureError:
            def create(self) -> None:
                raise FixtureError("inner", ValueError("original"))

        factory = FactoryThatRaisesFixtureError()
        proxy = SafeProxy(factory, "outer")

        with pytest.raises(FixtureError) as exc_info:
            proxy.create()

        assert exc_info.value.fixture_name == "inner"
