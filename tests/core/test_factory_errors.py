"""Integration tests for factory error handling in the test runner."""

from collections.abc import Callable
from typing import Annotated

from protest import ProTestSession, Scope, Use, fixture
from protest.core.runner import TestRunner
from protest.events.data import SessionResult, TestResult
from protest.plugin import PluginBase


class TestFactoryErrorDistinction:
    """Test that factory errors are reported as 'errors' not 'failed'."""

    def test_factory_error_counted_as_error_not_failed(self) -> None:
        session = ProTestSession()
        results: list[TestResult] = []
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_test_fail(self, result: TestResult) -> None:
                results.append(result)

            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @fixture(scope=Scope.FUNCTION, factory=True)
        def failing_factory() -> Callable[[], None]:
            def create() -> None:
                raise RuntimeError("DB unavailable")

            return create

        @session.test()
        def test_using_factory(
            make: Annotated[Callable[[], None], Use(failing_factory)],
        ) -> None:
            make()

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        assert len(results) == 1
        assert results[0].is_fixture_error is True
        assert len(session_results) == 1
        assert session_results[0].passed == 0
        assert session_results[0].failed == 0
        assert session_results[0].errors == 1

    def test_regular_test_failure_counted_as_failed(self) -> None:
        session = ProTestSession()
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @session.test()
        def test_that_fails() -> None:
            raise AssertionError("Expected failure")

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        assert len(session_results) == 1
        assert session_results[0].passed == 0
        assert session_results[0].failed == 1
        assert session_results[0].errors == 0

    def test_setup_error_during_fixture_resolution(self) -> None:
        session = ProTestSession()
        results: list[TestResult] = []
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_test_fail(self, result: TestResult) -> None:
                results.append(result)

            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @fixture(scope=Scope.FUNCTION)
        def broken_fixture() -> str:
            raise RuntimeError("Setup failed")

        @session.test()
        def test_with_broken_fixture(
            value: Annotated[str, Use(broken_fixture)],
        ) -> None:
            pass

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        assert len(results) == 1
        assert results[0].is_fixture_error is True
        assert len(session_results) == 1
        assert session_results[0].errors == 1
        assert session_results[0].failed == 0

    def test_mixed_results_counted_correctly(self) -> None:
        session = ProTestSession()
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @fixture(scope=Scope.FUNCTION, factory=True)
        def user_factory() -> Callable[..., dict[str, str]]:
            def create(fail: bool = False) -> dict[str, str]:
                if fail:
                    raise RuntimeError("Factory failed")
                return {"name": "alice"}

            return create

        @session.test()
        def test_passing() -> None:
            assert True

        @session.test()
        def test_failing() -> None:
            raise AssertionError("Intentional failure")

        @session.test()
        def test_factory_error(
            make_user: Annotated[Callable[..., dict[str, str]], Use(user_factory)],
        ) -> None:
            make_user(fail=True)

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        assert len(session_results) == 1
        result = session_results[0]
        assert result.passed == 1
        assert result.failed == 1
        assert result.errors == 1


class TestFactoryErrorPreservesOriginal:
    """Test that the original exception is properly preserved."""

    def test_original_exception_available_in_result(self) -> None:
        session = ProTestSession()
        results: list[TestResult] = []

        class Collector(PluginBase):
            def on_test_fail(self, result: TestResult) -> None:
                results.append(result)

        session.use(Collector())

        @fixture(scope=Scope.FUNCTION, factory=True)
        def factory_with_custom_error() -> Callable[[], None]:
            def create() -> None:
                raise ValueError("Custom message with details")

            return create

        @session.test()
        def test_it(
            factory: Annotated[Callable[[], None], Use(factory_with_custom_error)],
        ) -> None:
            factory()

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        assert isinstance(results[0].error, ValueError)
        assert "Custom message with details" in str(results[0].error)


class TestAsyncFactoryErrors:
    """Test factory errors with async factories."""

    def test_async_factory_error_handled(self) -> None:
        session = ProTestSession()
        results: list[TestResult] = []
        session_results: list[SessionResult] = []

        class Collector(PluginBase):
            def on_test_fail(self, result: TestResult) -> None:
                results.append(result)

            def on_session_end(self, result: SessionResult) -> None:
                session_results.append(result)

        session.use(Collector())

        @fixture(scope=Scope.FUNCTION, factory=True)
        def async_factory() -> Callable[[], None]:
            async def create() -> None:
                raise ConnectionError("API timeout")

            return create  # type: ignore[return-value]

        @session.test()
        async def test_async_factory(
            make: Annotated[Callable[[], None], Use(async_factory)],
        ) -> None:
            await make()  # type: ignore[misc]

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        assert len(results) == 1
        assert results[0].is_fixture_error is True
        assert session_results[0].errors == 1
