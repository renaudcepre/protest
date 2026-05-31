"""Tests for free-standing @fixture() and @factory() decorators."""

from typing import Annotated

from protest import FixtureFactory, ProTestSession, Use, factory, fixture
from protest.core.runner import TestRunner
from protest.di.decorators import FixtureWrapper, get_fixture_marker
from protest.plugin import PluginBase
from tests.conftest import CollectedEvents


class TestFixtureDecorator:
    """Tests for @fixture() decorator."""

    def test_fixture_is_function_scoped(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@fixture() creates a function-scoped fixture (fresh per test)."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        call_count = 0

        @fixture()
        def counter() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        @session.test()
        def test_one(value: Annotated[int, Use(counter)]) -> None:
            assert value == 1

        @session.test()
        def test_two(value: Annotated[int, Use(counter)]) -> None:
            assert value == 2  # Fresh instance, counter incremented again

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        expected_call_count = 2
        assert call_count == expected_call_count

    def test_fixture_with_tags(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@fixture(tags=[...]) properly tags the fixture."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @fixture(tags=["database", "slow"])
        def db_connection() -> str:
            return "connected"

        @session.test()
        def test_with_db(conn: Annotated[str, Use(db_connection)]) -> None:
            assert conn == "connected"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        # Tags are propagated to resolver
        tags = session.resolver.get_fixture_tags(db_connection)
        assert "database" in tags
        assert "slow" in tags

    def test_fixture_with_yield_teardown(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@fixture() with yield gets proper teardown."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        teardown_called = []

        @fixture()
        def resource() -> str:
            yield "resource"
            teardown_called.append("cleaned")

        @session.test()
        def test_use_resource(res: Annotated[str, Use(resource)]) -> None:
            assert res == "resource"

        runner = TestRunner(session)
        runner.run()

        expected_teardown_count = 1
        assert len(teardown_called) == expected_teardown_count


class TestFactoryDecorator:
    """Tests for @factory() decorator."""

    def test_factory_is_function_scoped(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory() creates a function-scoped factory."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory()
        def user(name: str) -> dict[str, str]:
            return {"name": name}

        @session.test()
        async def test_create_user(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice = await user_factory(name="alice")
            assert alice["name"] == "alice"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_factory_with_cache(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory(cache=True) caches by kwargs."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        call_count = 0

        @factory(cache=True)
        def user(name: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"name": name, "call": call_count}

        @session.test()
        async def test_caching(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice1 = await user_factory(name="alice")
            alice2 = await user_factory(name="alice")
            bob = await user_factory(name="bob")

            assert alice1 is alice2  # Cached
            assert alice1 is not bob

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        expected_call_count = 2  # alice once, bob once
        assert call_count == expected_call_count

    def test_factory_default_no_cache(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory() without arguments defaults to cache=False."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        call_count = 0

        @factory()  # No cache argument - should default to False
        def user(name: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"name": name, "call": call_count}

        @session.test()
        async def test_no_caching_by_default(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice1 = await user_factory(name="alice")
            alice2 = await user_factory(name="alice")

            assert alice1 is not alice2  # Not cached by default

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        expected_call_count = 2  # Both calls create new instance
        assert call_count == expected_call_count

    def test_factory_without_cache(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory(cache=False) creates new instance each time."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        call_count = 0

        @factory(cache=False)
        def user(name: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"name": name, "call": call_count}

        @session.test()
        async def test_no_caching(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice1 = await user_factory(name="alice")
            alice2 = await user_factory(name="alice")

            assert alice1 is not alice2

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        expected_call_count = 2
        assert call_count == expected_call_count

    def test_factory_managed_false(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory(managed=False) returns custom factory class with FixtureErrorWrapper."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        class UserFactory:
            def create(self, name: str) -> dict[str, str]:
                return {"name": name}

        @factory(managed=False)
        def user_factory() -> UserFactory:
            return UserFactory()

        @session.test()
        def test_custom_factory(
            factory_instance: Annotated[UserFactory, Use(user_factory)],
        ) -> None:
            user = factory_instance.create(name="alice")
            assert user["name"] == "alice"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_factory_can_depend_on_function_scoped_fixture(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory() can depend on @fixture() (both function-scoped)."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @fixture()
        def db_connection() -> str:
            return "postgres://localhost"

        @factory()
        def user(
            db: Annotated[str, Use(db_connection)],
            name: str,
        ) -> dict[str, str]:
            return {"name": name, "db": db}

        @session.test()
        async def test_factory_with_dep(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice = await user_factory(name="alice")
            assert alice["name"] == "alice"
            assert alice["db"] == "postgres://localhost"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_factory_with_tags(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """@factory(tags=[...]) properly tags the factory."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory(tags=["slow", "integration"])
        def user(name: str) -> dict[str, str]:
            return {"name": name}

        @session.test()
        async def test_with_factory(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(name="alice")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        tags = session.resolver.get_fixture_tags(user)
        assert "slow" in tags
        assert "integration" in tags


class TestDecoratorWithoutParentheses:
    """@fixture / @factory usable without parentheses when no args (issue #92)."""

    def test_bare_fixture_equivalent_to_called(self) -> None:
        """`@fixture` produces the same wrapper/marker as `@fixture()`."""

        @fixture
        def bare() -> int:
            return 1

        @fixture()
        def called() -> int:
            return 1

        assert isinstance(bare, FixtureWrapper)
        assert isinstance(called, FixtureWrapper)
        bare_marker = get_fixture_marker(bare)
        called_marker = get_fixture_marker(called)
        assert bare_marker is not None
        assert called_marker is not None
        assert bare_marker.is_factory is called_marker.is_factory is False

    def test_bare_factory_equivalent_to_called(self) -> None:
        """`@factory` produces the same wrapper/marker as `@factory()` (defaults)."""

        @factory
        def bare(name: str) -> dict[str, str]:
            return {"name": name}

        @factory()
        def called(name: str) -> dict[str, str]:
            return {"name": name}

        assert isinstance(bare, FixtureWrapper)
        assert isinstance(called, FixtureWrapper)
        bare_marker = get_fixture_marker(bare)
        called_marker = get_fixture_marker(called)
        assert bare_marker is not None
        assert called_marker is not None
        assert bare_marker.is_factory is True
        assert bare_marker.cache is called_marker.cache is False
        assert bare_marker.managed is called_marker.managed is True

    def test_bare_fixture_resolves_in_test(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """End-to-end: a bare `@fixture` resolves like a normal fixture."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @fixture
        def value() -> str:
            return "ok"

        @session.test()
        def test_uses_value(v: Annotated[str, Use(value)]) -> None:
            assert v == "ok"

        result = TestRunner(session).run()
        assert result.success is True

    def test_bare_factory_resolves_in_test(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """End-to-end: a bare `@factory` produces a usable factory."""
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory
        def user(name: str) -> dict[str, str]:
            return {"name": name}

        @session.test()
        async def test_makes_user(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            alice = await user_factory(name="alice")
            assert alice["name"] == "alice"

        result = TestRunner(session).run()
        assert result.success is True
