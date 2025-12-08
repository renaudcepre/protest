import os
from typing import Annotated

import pytest

from protest import Mocker, ProTestSession, Use, mocker
from protest.core.runner import TestRunner
from protest.plugin import PluginBase
from tests.conftest import CollectedEvents


class DummyService:
    def get_value(self) -> str:
        return "real_value"

    def compute(self, value: int) -> int:
        return value * 2


def external_function() -> str:
    return "external_result"


class TestMockerFixture:
    def test_patch_function(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def test_patch(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func.return_value = "mocked_result"

            result = external_function()
            assert result == "mocked_result"
            mock_func.assert_called_once()

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        expected_pass_count = 1
        assert len(collected.test_passes) == expected_pass_count

    def test_patch_object(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_object_patch(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            service = DummyService()
            mock_method = mock_manager.patch.object(service, "get_value")
            mock_method.return_value = "mocked_value"

            result = service.get_value()
            assert result == "mocked_value"
            mock_method.assert_called_once()

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_patch_dict(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_dict_patch(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_manager.patch.dict(os.environ, {"TEST_VAR": "test_value"})

            assert os.environ.get("TEST_VAR") == "test_value"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert "TEST_VAR" not in os.environ

    def test_patch_dict_clear(self) -> None:
        session = ProTestSession()
        original_env_key = "PATH"

        @session.test()
        def test_dict_clear(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_manager.patch.dict(os.environ, {"ONLY_KEY": "only_value"}, clear=True)

            assert os.environ.get("ONLY_KEY") == "only_value"
            assert original_env_key not in os.environ

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert original_env_key in os.environ

    def test_stopall_lifo(self) -> None:
        session = ProTestSession()
        teardown_order: list[str] = []

        @session.test()
        def test_lifo(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            def tracking_stopall() -> None:
                for patcher in reversed(mock_manager._patchers):
                    teardown_order.append(str(patcher))
                    patcher.stop()
                mock_manager._patchers.clear()
                mock_manager._mocks.clear()

            mock_manager.stopall = tracking_stopall

            mock_manager.patch("tests.fixtures.test_mocker.external_function")
            service = DummyService()
            mock_manager.patch.object(service, "get_value")

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        expected_teardown_count = 2
        assert len(teardown_order) == expected_teardown_count

    def test_stop_single(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_single_stop(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock1 = mock_manager.patch("tests.fixtures.test_mocker.external_function")
            mock1.return_value = "mock1"

            assert external_function() == "mock1"

            mock_manager.stop(mock1)

            assert external_function() == "external_result"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_resetall(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_reset(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func.return_value = "mocked"

            external_function()
            external_function()

            assert mock_func.call_count == 2

            mock_manager.resetall()

            assert mock_func.call_count == 0

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_spy_tracks_calls_classic_style(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_spy(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            service = DummyService()
            spy = mock_manager.spy(service, "compute")

            result = service.compute(5)

            assert result == 10
            spy.assert_called_once_with(5)

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_spy_tracks_calls_bound_method_style(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_spy_bound(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            service = DummyService()
            spy = mock_manager.spy(service.compute)

            result = service.compute(5)

            assert result == 10
            spy.assert_called_once_with(5)

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_spy_return(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_spy_return_value(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            service = DummyService()
            spy = mock_manager.spy(service, "compute")

            service.compute(3)

            assert spy.spy_return == 6

            service.compute(7)

            assert spy.spy_return == 14

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_stub(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_stub_callable(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            callback = mock_manager.stub("my_callback")
            callback.return_value = "callback_result"

            result = callback("arg1", key="value")

            assert result == "callback_result"
            callback.assert_called_once_with("arg1", key="value")

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_async_stub(self) -> None:
        session = ProTestSession()

        @session.test()
        async def test_async_stub_awaitable(
            mock_manager: Annotated[Mocker, Use(mocker)],
        ) -> None:
            async_callback = mock_manager.async_stub("async_callback")
            async_callback.return_value = "async_result"

            result = await async_callback("async_arg")

            assert result == "async_result"
            async_callback.assert_awaited_once_with("async_arg")

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_create_autospec(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_autospec(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_service = mock_manager.create_autospec(DummyService, instance=True)
            mock_service.compute.return_value = 100

            result = mock_service.compute(5)

            assert result == 100
            mock_service.compute.assert_called_once_with(5)

        runner = TestRunner(session)
        success = runner.run()

        assert success is True

    def test_isolation_between_tests(self) -> None:
        session = ProTestSession()
        call_counts: list[int] = []

        @session.test()
        def test_first(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func()
            call_counts.append(mock_func.call_count)

        @session.test()
        def test_second(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func()
            call_counts.append(mock_func.call_count)

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        assert call_counts == [1, 1]

    def test_parallel_isolation(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        plugin, collected = event_collector
        session = ProTestSession(concurrency=3)
        session.use(plugin)

        @session.test()
        def test_a(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func.return_value = "a"
            assert external_function() == "a"

        @session.test()
        def test_b(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func.return_value = "b"
            assert external_function() == "b"

        @session.test()
        def test_c(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_func = mock_manager.patch(
                "tests.fixtures.test_mocker.external_function"
            )
            mock_func.return_value = "c"
            assert external_function() == "c"

        runner = TestRunner(session)
        success = runner.run()

        assert success is True
        expected_pass_count = 3
        assert len(collected.test_passes) == expected_pass_count

    def test_teardown_on_test_failure(self) -> None:
        session = ProTestSession()
        cleanup_verified = []

        class LocalService:
            def method(self) -> str:
                return "original"

        service = LocalService()

        @session.test()
        def test_failing(mock_manager: Annotated[Mocker, Use(mocker)]) -> None:
            mock_method = mock_manager.patch.object(service, "method")
            mock_method.return_value = "mocked"
            assert service.method() == "mocked"
            raise AssertionError("Intentional failure")

        runner = TestRunner(session)
        success = runner.run()

        assert success is False
        cleanup_verified.append(service.method() == "original")
        assert cleanup_verified[0] is True

    def test_spy_invalid_argument_raises_typeerror(self) -> None:
        mock_manager = Mocker()

        with pytest.raises(TypeError, match="spy\\(\\) requires either"):
            mock_manager.spy("not_a_bound_method")

        with pytest.raises(TypeError, match="spy\\(\\) requires either"):
            mock_manager.spy(lambda: None)

        with pytest.raises(TypeError, match="spy\\(\\) requires either"):
            mock_manager.spy(42)
