"""Integration tests for factory error handling in the test runner."""

from typing import Annotated

from protest import FixtureFactory, ProTestSession, Use
from protest.core.runner import TestRunner
from protest.plugin import PluginBase
from tests.conftest import CollectedEvents


class TestFactoryErrorDistinction:
    """Test that factory errors are reported as 'errors' not 'failed'."""

    def test_factory_error_counted_as_error_not_failed(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.factory()
        def user(username: str) -> dict[str, str]:
            raise RuntimeError("DB unavailable")

        @session.test()
        async def test_using_factory(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(username="alice")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert collected.test_fails[0].is_fixture_error is True
        expected_session_result_count = 1
        assert len(collected.session_results) == expected_session_result_count
        assert collected.session_results[0].passed == 0
        assert collected.session_results[0].failed == 0
        assert collected.session_results[0].errors == 1

    def test_regular_test_failure_counted_as_failed(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def test_that_fails() -> None:
            raise AssertionError("Expected failure")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_session_result_count = 1
        assert len(collected.session_results) == expected_session_result_count
        assert collected.session_results[0].passed == 0
        assert collected.session_results[0].failed == 1
        assert collected.session_results[0].errors == 0

    def test_setup_error_during_fixture_resolution(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        def broken_fixture() -> str:
            raise RuntimeError("Setup failed")

        @session.test()
        def test_with_broken_fixture(
            value: Annotated[str, Use(broken_fixture)],
        ) -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert collected.test_fails[0].is_fixture_error is True
        expected_session_result_count = 1
        assert len(collected.session_results) == expected_session_result_count
        assert collected.session_results[0].errors == 1
        assert collected.session_results[0].failed == 0

    def test_mixed_results_counted_correctly(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.factory()
        def user(username: str, fail: bool = False) -> dict[str, str]:
            if fail:
                raise RuntimeError("Factory failed")
            return {"name": username}

        @session.test()
        def test_passing() -> None:
            assert True

        @session.test()
        def test_failing() -> None:
            raise AssertionError("Intentional failure")

        @session.test()
        async def test_factory_error(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(username="alice", fail=True)

        runner = TestRunner(session)
        run_result = runner.run()

        assert run_result.success is False
        expected_session_result_count = 1
        assert len(collected.session_results) == expected_session_result_count
        session_result = collected.session_results[0]
        assert session_result.passed == 1
        assert session_result.failed == 1
        assert session_result.errors == 1


class TestFactoryErrorPreservesOriginal:
    """Test that the original exception is properly preserved."""

    def test_original_exception_available_in_result(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.factory()
        def user(username: str) -> dict[str, str]:
            raise ValueError("Custom message with details")

        @session.test()
        async def test_it(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(username="alice")

        runner = TestRunner(session)
        runner.run()

        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert isinstance(collected.test_fails[0].error, ValueError)
        assert "Custom message with details" in str(collected.test_fails[0].error)


class TestAsyncFactoryErrors:
    """Test factory errors with async factories."""

    def test_async_factory_error_handled(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.factory()
        async def user(username: str) -> dict[str, str]:
            raise ConnectionError("API timeout")

        @session.test()
        async def test_async_factory(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(username="alice")

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False
        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert collected.test_fails[0].is_fixture_error is True
        assert collected.session_results[0].errors == 1


class TestFactoryWithTeardown:
    """Test that factory teardown works correctly."""

    def test_factory_teardown_called_on_session_end(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        teardown_called = []

        @session.factory()
        def user(username: str) -> dict[str, str]:
            yield {"name": username}
            teardown_called.append(username)

        @session.test()
        async def test_create_users(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            await user_factory(username="alice")
            await user_factory(username="bob")

        runner = TestRunner(session)
        runner.run()

        expected_teardown_count = 2
        assert len(teardown_called) == expected_teardown_count
        assert "alice" in teardown_called
        assert "bob" in teardown_called


class TestFactoryCaching:
    """Test that factory caching works correctly."""

    def test_factory_caches_by_kwargs(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        call_count = 0

        @session.factory()
        def user(username: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"name": username, "call": call_count}

        @session.test()
        async def test_caching(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            user1 = await user_factory(username="alice")
            user2 = await user_factory(username="alice")
            user3 = await user_factory(username="bob")

            assert user1 is user2
            assert user1 is not user3
            expected_call_count = 2
            assert call_count == expected_call_count

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_factory_no_cache_when_disabled(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, _collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        call_count = 0

        @session.factory(cache=False)
        def user(username: str) -> dict[str, str]:
            nonlocal call_count
            call_count += 1
            return {"name": username, "call": call_count}

        @session.test()
        async def test_no_caching(
            user_factory: Annotated[FixtureFactory[dict[str, str]], Use(user)],
        ) -> None:
            user1 = await user_factory(username="alice")
            user2 = await user_factory(username="alice")

            assert user1 is not user2
            expected_call_count = 2
            assert call_count == expected_call_count

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
