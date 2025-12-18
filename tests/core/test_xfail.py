"""Test xfail functionality."""

from typing import Annotated

from protest import ForEach, From, ProTestSession, ProTestSuite
from protest.core.collector import Collector
from protest.core.runner import TestRunner
from protest.entities import SessionResult, TestResult


class TestXfailDecorator:
    def test_xfail_with_bool_sets_default_reason(self) -> None:
        session = ProTestSession()

        @session.test(xfail=True)
        def test_xfailed() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 1
        assert len(items) == expected_item_count
        assert items[0].xfail is not None
        assert items[0].xfail.reason == "Expected failure"

    def test_xfail_with_string_sets_reason(self) -> None:
        session = ProTestSession()

        @session.test(xfail="Bug #123: known race condition")
        def test_xfailed() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 1
        assert len(items) == expected_item_count
        assert items[0].xfail is not None
        assert items[0].xfail.reason == "Bug #123: known race condition"

    def test_no_xfail_has_none_reason(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_normal() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 1
        assert len(items) == expected_item_count
        assert items[0].xfail is None

    def test_suite_xfail_decorator(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("test")
        session.include_suite(suite)

        @suite.test(xfail="Suite test xfailed")
        def test_xfailed() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 1
        assert len(items) == expected_item_count
        assert items[0].xfail is not None
        assert items[0].xfail.reason == "Suite test xfailed"


class TestXfailExecution:
    def test_xfailed_test_runs_and_counts_as_xfail(self) -> None:
        session = ProTestSession()
        executed = []
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: SessionResult) -> None:
                results["xfailed"] = result.xfailed
                results["xpassed"] = result.xpassed
                results["failed"] = result.failed

        session.register_plugin(CountingPlugin())

        @session.test(xfail="Known bug")
        def test_xfailed() -> None:
            executed.append("xfailed")
            raise AssertionError("Expected failure")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["xfailed"]
        assert results["xfailed"] == 1
        assert results["xpassed"] == 0
        assert results["failed"] == 0

    def test_xpassed_test_runs_and_counts_as_xpass(self) -> None:
        session = ProTestSession()
        executed = []
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: SessionResult) -> None:
                results["xfailed"] = result.xfailed
                results["xpassed"] = result.xpassed
                results["passed"] = result.passed

        session.register_plugin(CountingPlugin())

        @session.test(xfail="Should fail but doesn't")
        def test_xpassed() -> None:
            executed.append("xpassed")
            assert True

        runner = TestRunner(session)
        runner.run()

        assert executed == ["xpassed"]
        assert results["xfailed"] == 0
        assert results["xpassed"] == 1
        assert results["passed"] == 0

    def test_xfail_emits_xfail_event(self) -> None:
        session = ProTestSession()
        xfail_results: list[TestResult] = []

        class XfailPlugin:
            def on_test_xfail(self, result: TestResult) -> None:
                xfail_results.append(result)

        session.register_plugin(XfailPlugin())

        @session.test(xfail="My xfail reason")
        def test_xfailed() -> None:
            raise ValueError("Expected")

        runner = TestRunner(session)
        runner.run()

        expected_result_count = 1
        assert len(xfail_results) == expected_result_count
        assert xfail_results[0].xfail_reason == "My xfail reason"

    def test_xpass_emits_xpass_event(self) -> None:
        session = ProTestSession()
        xpass_results: list[TestResult] = []

        class XpassPlugin:
            def on_test_xpass(self, result: TestResult) -> None:
                xpass_results.append(result)

        session.register_plugin(XpassPlugin())

        @session.test(xfail="Should fail")
        def test_xpassed() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        expected_result_count = 1
        assert len(xpass_results) == expected_result_count
        assert xpass_results[0].xfail_reason == "Should fail"

    def test_xfail_does_not_affect_exit_code(self) -> None:
        session = ProTestSession()

        @session.test(xfail=True)
        def test_xfailed() -> None:
            raise AssertionError("Expected")

        @session.test()
        def test_normal() -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True

    def test_xpass_causes_failure_exit_code(self) -> None:
        session = ProTestSession()

        @session.test(xfail=True)
        def test_xpassed() -> None:
            pass

        @session.test()
        def test_normal() -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is False


class TestXfailWithParameterizedTests:
    def test_xfail_applies_to_all_variations(self) -> None:
        session = ProTestSession()
        executed = []
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: SessionResult) -> None:
                results["xfailed"] = result.xfailed

        session.register_plugin(CountingPlugin())

        VALUES = ForEach([1, 2, 3])  # noqa

        @session.test(xfail="All variations xfail")
        def test_parameterized(val: Annotated[int, From(VALUES)]) -> None:
            executed.append(val)
            raise ValueError(f"Expected failure for {val}")

        runner = TestRunner(session)
        runner.run()

        expected_executed = [1, 2, 3]
        assert sorted(executed) == expected_executed
        expected_xfailed_count = 3
        assert results["xfailed"] == expected_xfailed_count


class TestXfailWithSkip:
    def test_skip_takes_priority_over_xfail(self) -> None:
        session = ProTestSession()
        executed = []
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: SessionResult) -> None:
                results["skipped"] = result.skipped
                results["xfailed"] = result.xfailed

        session.register_plugin(CountingPlugin())

        @session.test(skip="Skipped", xfail="Would xfail")
        def test_skip_and_xfail() -> None:
            executed.append("should not run")
            raise AssertionError("Should not run")

        runner = TestRunner(session)
        runner.run()

        assert executed == []
        assert results["skipped"] == 1
        assert results["xfailed"] == 0
