"""Test conditional skip functionality (skip with callable condition)."""

from typing import Annotated

from protest import ForEach, From, ProTestSession, ProTestSuite, Skip, Use, fixture
from protest.core.collector import Collector
from protest.core.runner import TestRunner
from protest.entities import SessionResult, TestResult
from protest.plugin import PluginBase


class TestConditionalSkipDecorator:
    """Test skip with callable condition parameter normalization and collection."""

    def test_skip_with_true_bool_creates_skip(self) -> None:
        session = ProTestSession()

        @session.test(skip=True, skip_reason="Always skip")
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip is not None
        assert items[0].skip.is_static
        assert items[0].skip.reason == "Always skip"

    def test_skip_with_false_bool_is_none(self) -> None:
        session = ProTestSession()

        @session.test(skip=False)
        def test_normal() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip is None

    def test_skip_with_callable(self) -> None:
        session = ProTestSession()

        @session.test(skip=lambda: True, skip_reason="Callable skip")
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip is not None
        assert items[0].skip.is_conditional
        assert callable(items[0].skip.condition)
        assert items[0].skip.reason == "Callable skip"

    def test_skip_with_skip_object_and_condition(self) -> None:
        session = ProTestSession()

        @session.test(skip=Skip(condition=lambda: True, reason="Explicit Skip"))
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip is not None
        assert items[0].skip.reason == "Explicit Skip"
        assert items[0].skip.is_conditional

    def test_suite_skip_with_callable(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("test")
        session.add_suite(suite)

        @suite.test(skip=lambda: True, skip_reason="Suite conditional skip")
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip is not None
        assert items[0].skip.reason == "Suite conditional skip"


class TestStaticSkipExecution:
    """Test static skip (bool condition) execution."""

    def test_static_skip_true_skips_test(self) -> None:
        session = ProTestSession()
        executed = []

        @session.test(skip=True)
        def test_skipped() -> None:
            executed.append("skipped")

        @session.test()
        def test_normal() -> None:
            executed.append("normal")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["normal"]

    def test_static_skip_false_runs_test(self) -> None:
        session = ProTestSession()
        executed = []

        @session.test(skip=False)
        def test_normal() -> None:
            executed.append("normal")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["normal"]

    def test_static_skip_counts_as_skipped(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin(PluginBase):
            def on_session_complete(self, result: SessionResult) -> None:
                results["passed"] = result.passed
                results["skipped"] = result.skipped
                results["failed"] = result.failed

        session.register_plugin(CountingPlugin())

        @session.test(skip=True)
        def test_skipped() -> None:
            pass

        @session.test()
        def test_normal() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert results["passed"] == 1
        assert results["skipped"] == 1
        assert results["failed"] == 0

    def test_static_skip_emits_skip_event(self) -> None:
        session = ProTestSession()
        skip_results: list[TestResult] = []

        class SkipPlugin(PluginBase):
            def on_test_skip(self, result: TestResult) -> None:
                skip_results.append(result)

        session.register_plugin(SkipPlugin())

        @session.test(skip=True, skip_reason="Platform check failed")
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(skip_results) == 1
        assert skip_results[0].skip_reason == "Platform check failed"


class TestConditionalSkipExecution:
    """Test runtime skip (callable condition) execution."""

    def test_conditional_skip_no_params_true(self) -> None:
        session = ProTestSession()
        condition_called = []

        def always_skip() -> bool:
            condition_called.append(True)
            return True

        @session.test(skip=always_skip, skip_reason="Always skip")
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert condition_called == [True]

    def test_conditional_skip_no_params_false(self) -> None:
        session = ProTestSession()
        executed = []

        def never_skip() -> bool:
            return False

        @session.test(skip=never_skip)
        def test_runs() -> None:
            executed.append("ran")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["ran"]

    def test_conditional_skip_with_fixtures(self) -> None:
        session = ProTestSession()
        executed = []

        @fixture()
        def config() -> dict[str, bool]:
            return {"skip_test": True}

        session.bind(config)

        @session.test(
            skip=lambda config: config["skip_test"],
            skip_reason="Config says skip",
        )
        def test_skipped(cfg: Annotated[dict[str, bool], Use(config)]) -> None:
            executed.append("skipped")

        @session.test()
        def test_normal() -> None:
            executed.append("normal")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["normal"]

    def test_conditional_skip_receives_only_requested_kwargs(self) -> None:
        session = ProTestSession()
        received_kwargs: list[str] = []

        @fixture()
        def fixture_a() -> str:
            return "A"

        @fixture()
        def fixture_b() -> str:
            return "B"

        session.bind(fixture_a)
        session.bind(fixture_b)

        def condition(a: str) -> bool:
            received_kwargs.append(a)
            return False

        @session.test(skip=condition)
        def test_check(
            a: Annotated[str, Use(fixture_a)],
            b: Annotated[str, Use(fixture_b)],
        ) -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert received_kwargs == ["A"]

    def test_conditional_skip_counts_as_skipped(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin(PluginBase):
            def on_session_complete(self, result: SessionResult) -> None:
                results["skipped"] = result.skipped

        session.register_plugin(CountingPlugin())

        @session.test(skip=lambda: True)
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert results["skipped"] == 1


class TestSkipPriority:
    """Test static skip takes priority over conditional skip."""

    def test_static_skip_reason_takes_priority_over_condition(self) -> None:
        session = ProTestSession()
        skip_results: list[TestResult] = []

        class SkipPlugin(PluginBase):
            def on_test_skip(self, result: TestResult) -> None:
                skip_results.append(result)

        session.register_plugin(SkipPlugin())

        # Skip with reason string (static) should be used, not a callable
        @session.test(skip="Explicit skip reason")
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(skip_results) == 1
        assert skip_results[0].skip_reason == "Explicit skip reason"

    def test_conditional_skip_reason_in_result(self) -> None:
        session = ProTestSession()
        skip_results: list[TestResult] = []

        class SkipPlugin(PluginBase):
            def on_test_skip(self, result: TestResult) -> None:
                skip_results.append(result)

        session.register_plugin(SkipPlugin())

        @session.test(skip=lambda: True, skip_reason="Platform not supported")
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(skip_results) == 1
        assert skip_results[0].skip_reason == "Platform not supported"


class TestConditionalSkipWithParameterized:
    """Test conditional skip with parameterized tests."""

    def test_static_skip_applies_to_all_variations(self) -> None:
        session = ProTestSession()
        executed = []

        VALUES = ForEach([1, 2, 3])  # noqa: N806 - test constant

        @session.test(skip=True, skip_reason="Skip all")
        def test_parameterized(val: Annotated[int, From(VALUES)]) -> None:
            executed.append(val)

        runner = TestRunner(session)
        runner.run()

        assert executed == []

    def test_static_skip_counts_all_variations(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin(PluginBase):
            def on_session_complete(self, result: SessionResult) -> None:
                results["skipped"] = result.skipped

        session.register_plugin(CountingPlugin())

        VALUES = ForEach([1, 2, 3])  # noqa: N806 - test constant

        @session.test(skip=True)
        def test_parameterized(val: Annotated[int, From(VALUES)]) -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert results["skipped"] == 3


class TestConditionalSkipWithXfailRetry:
    """Test interaction with xfail and retry."""

    def test_skip_with_xfail_skip_wins(self) -> None:
        session = ProTestSession()
        executed = []

        @session.test(skip=True, xfail="Known bug")
        def test_skipped() -> None:
            executed.append("ran")

        runner = TestRunner(session)
        runner.run()

        assert executed == []

    def test_skip_with_retry_skip_wins(self) -> None:
        session = ProTestSession()
        executed = []

        @session.test(skip=True, retry=3)
        def test_skipped() -> None:
            executed.append("ran")

        runner = TestRunner(session)
        runner.run()

        assert executed == []


class TestConditionalSkipEdgeCases:
    """Test edge cases and error handling."""

    def test_skip_callable_raises_error(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin(PluginBase):
            def on_session_complete(self, result: SessionResult) -> None:
                results["errors"] = result.errors

        session.register_plugin(CountingPlugin())

        def bad_condition() -> bool:
            raise RuntimeError("Condition failed")

        @session.test(skip=bad_condition)
        def test_error() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        # Should be treated as ERROR, not FAIL or SKIP
        assert results["errors"] == 1

    def test_async_skip_condition(self) -> None:
        session = ProTestSession()
        executed = []

        async def async_condition() -> bool:
            return True

        @session.test(skip=async_condition, skip_reason="Async skip")
        def test_skipped() -> None:
            executed.append("ran")

        runner = TestRunner(session)
        runner.run()

        assert executed == []

    def test_skip_callable_with_missing_fixture_causes_error(self) -> None:
        """Skip callable that requests a fixture not used by test causes ERROR."""
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin(PluginBase):
            def on_session_complete(self, result: SessionResult) -> None:
                results["errors"] = result.errors

        session.register_plugin(CountingPlugin())

        @fixture()
        def unused_fixture() -> str:
            return "unused"

        session.bind(unused_fixture)

        # This condition requests 'unused_fixture' but test doesn't use it
        # The callable will be called without the required argument -> TypeError
        def condition(unused_fixture: str) -> bool:
            return True

        @session.test(skip=condition)
        def test_errors() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        # Test errors because the callable doesn't receive required kwargs
        assert results["errors"] == 1
