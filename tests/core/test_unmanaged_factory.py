"""Integration tests for non-managed factory fixtures (factory=True, managed=False)."""

from typing import Annotated

from protest import ProTestSession, Use
from protest.core.runner import TestRunner
from protest.di.decorators import factory, fixture
from protest.plugin import PluginBase
from tests.conftest import CollectedEvents


class UserFactory:
    """A custom factory class that manages user creation."""

    def __init__(self, db: str) -> None:
        self.db = db
        self.created: list[dict[str, str]] = []

    def create(self, name: str, role: str = "guest") -> dict[str, str]:
        user = {"name": name, "role": role, "db": self.db}
        self.created.append(user)
        return user

    def create_many(self, count: int) -> list[dict[str, str]]:
        return [self.create(f"user_{idx}") for idx in range(count)]


class FailingUserFactory:
    """A factory that fails on certain inputs."""

    def create(self, name: str) -> dict[str, str]:
        if name == "crash":
            raise ValueError("Database unavailable")
        return {"name": name}


class TestUnmanagedFactoryBasic:
    """Test that managed=False returns the factory class directly."""

    def test_factory_class_methods_available(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory(managed=False)
        def user_factory() -> UserFactory:
            return UserFactory(db="test_db")

        session.fixture(user_factory)

        @session.test()
        def test_use_factory(
            factory: Annotated[UserFactory, Use(user_factory)],
        ) -> None:
            user = factory.create(name="alice", role="admin")
            assert user["name"] == "alice"
            assert user["role"] == "admin"

            users = factory.create_many(count=3)
            expected_count = 3
            assert len(users) == expected_count

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True


class TestUnmanagedFactoryErrorHandling:
    """Test that errors in non-managed factories are reported as ERROR not FAIL."""

    def test_factory_error_counted_as_error(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory(managed=False)
        def user_factory() -> FailingUserFactory:
            return FailingUserFactory()

        session.fixture(user_factory)

        @session.test()
        def test_trigger_factory_error(
            factory: Annotated[FailingUserFactory, Use(user_factory)],
        ) -> None:
            factory.create(name="crash")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert collected.test_fails[0].is_fixture_error is True
        expected_session_count = 1
        assert len(collected.session_results) == expected_session_count
        assert collected.session_results[0].errors == 1
        assert collected.session_results[0].failed == 0

    def test_regular_test_failure_still_counted_as_failed(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @factory(managed=False)
        def user_factory() -> UserFactory:
            return UserFactory(db="test_db")

        session.fixture(user_factory)

        @session.test()
        def test_assertion_failure(
            factory: Annotated[UserFactory, Use(user_factory)],
        ) -> None:
            user = factory.create(name="alice")
            assert user["name"] == "bob"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_session_count = 1
        assert len(collected.session_results) == expected_session_count
        assert collected.session_results[0].failed == 1
        assert collected.session_results[0].errors == 0


class TestUnmanagedFactoryWithDependencies:
    """Test that non-managed factories can have dependencies."""

    def test_factory_receives_dependencies(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        @fixture()
        def database() -> str:
            return "postgres://localhost"

        @factory(managed=False)
        def user_factory(
            db: Annotated[str, Use(database)],
        ) -> UserFactory:
            return UserFactory(db=db)

        session.fixture(database)
        session.fixture(user_factory)

        @session.test()
        def test_factory_has_db(
            factory: Annotated[UserFactory, Use(user_factory)],
        ) -> None:
            assert factory.db == "postgres://localhost"
            user = factory.create(name="alice")
            assert user["db"] == "postgres://localhost"

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True


class TestUnmanagedFactoryWithTeardown:
    """Test that non-managed factories with yield get proper teardown."""

    def test_factory_teardown_called(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.register_plugin(plugin)

        teardown_called = []

        @factory(managed=False)
        def user_factory() -> UserFactory:
            factory = UserFactory(db="test_db")
            yield factory
            teardown_called.append(factory.created.copy())

        session.fixture(user_factory)

        @session.test()
        def test_create_users(
            factory: Annotated[UserFactory, Use(user_factory)],
        ) -> None:
            factory.create(name="alice")
            factory.create(name="bob")

        runner = TestRunner(session)
        runner.run()

        expected_teardown_count = 1
        assert len(teardown_called) == expected_teardown_count
        expected_user_count = 2
        assert len(teardown_called[0]) == expected_user_count
