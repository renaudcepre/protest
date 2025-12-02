"""Tests for TestRunner - the core test execution engine."""

import asyncio
import time
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use
from protest.core.collector import TestItem
from protest.core.runner import TestRunner
from protest.plugin import PluginBase
from tests.conftest import (
    CollectedEvents,
    ConcurrencyTracker,
    register_concurrent_tests,
)


class TestRunnerBasics:
    """Basic test execution."""

    def test_runner_with_passing_test(self) -> None:
        """Runner returns True when all tests pass."""
        session = ProTestSession()

        @session.test()
        def passing_test() -> None:
            assert True

        runner = TestRunner(session)
        result = runner.run()

        assert result is True

    def test_runner_with_failing_test(self) -> None:
        """Runner returns False when any test fails."""
        session = ProTestSession()

        @session.test()
        def failing_test() -> None:
            raise AssertionError("intentional failure")

        runner = TestRunner(session)
        result = runner.run()

        assert result is False

    def test_runner_with_mixed_results(self) -> None:
        """Runner returns False if any test fails."""
        session = ProTestSession()

        @session.test()
        def passing_test() -> None:
            assert True

        @session.test()
        def failing_test() -> None:
            raise ValueError("intentional failure")

        runner = TestRunner(session)
        result = runner.run()

        assert result is False

    def test_runner_with_no_tests(self) -> None:
        """Runner returns True when no tests to run."""
        session = ProTestSession()
        runner = TestRunner(session)
        result = runner.run()

        assert result is True


class TestRunnerEvents:
    """Event emission during test execution."""

    def test_runner_emits_session_events(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """Runner emits SESSION_START, SESSION_END, SESSION_COMPLETE."""
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def simple_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert "session_start" in collected.events
        assert "session_end" in collected.events
        assert "session_complete" in collected.events

    def test_runner_emits_test_pass_event(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """Runner emits TEST_PASS for passing tests."""
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def my_passing_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        expected_pass_count = 1
        assert len(collected.test_passes) == expected_pass_count
        assert collected.test_passes[0].name == "my_passing_test"
        assert collected.test_passes[0].error is None

    def test_runner_emits_test_fail_event(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """Runner emits TEST_FAIL for failing tests."""
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def my_failing_test() -> None:
            raise ValueError("test error")

        runner = TestRunner(session)
        runner.run()

        expected_fail_count = 1
        assert len(collected.test_fails) == expected_fail_count
        assert collected.test_fails[0].name == "my_failing_test"
        assert isinstance(collected.test_fails[0].error, ValueError)


class TestRunnerWithFixtures:
    """Test execution with fixture injection."""

    def test_runner_injects_session_fixtures(self) -> None:
        """Runner injects session-scoped fixtures into tests."""
        session = ProTestSession()
        received_value: list[str] = []

        @session.fixture()
        def my_fixture() -> str:
            return "fixture_value"

        @session.test()
        def test_with_fixture(val: Annotated[str, Use(my_fixture)]) -> None:
            received_value.append(val)

        runner = TestRunner(session)
        runner.run()

        assert received_value == ["fixture_value"]

    def test_runner_handles_generator_fixtures(self) -> None:
        """Runner handles generator fixtures with teardown."""
        session = ProTestSession()
        teardown_called = False

        @session.fixture()
        def generator_fixture():
            yield "gen_value"
            nonlocal teardown_called
            teardown_called = True

        @session.test()
        def test_with_gen(val: Annotated[str, Use(generator_fixture)]) -> None:
            assert val == "gen_value"

        runner = TestRunner(session)
        runner.run()

        assert teardown_called


class TestRunnerWithSuites:
    """Test execution with suites."""

    def test_runner_executes_suite_tests(self) -> None:
        """Runner executes tests in suites."""
        session = ProTestSession()
        suite = ProTestSuite("test_suite")
        session.add_suite(suite)

        executed: list[str] = []

        @suite.test()
        def suite_test() -> None:
            executed.append("suite_test")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["suite_test"]

    def test_runner_emits_suite_events(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """Runner emits SUITE_START and SUITE_END."""
        plugin, collected = event_collector
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.add_suite(suite)
        session.use(plugin)

        @suite.test()
        def suite_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert ("start", "my_suite") in collected.suite_events
        assert ("end", "my_suite") in collected.suite_events

    def test_runner_uses_suite_max_concurrency(self) -> None:
        """Suite max_concurrency caps effective concurrency."""
        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("capped_suite", max_concurrency=1)
        session.add_suite(suite)

        execution_order: list[int] = []

        @suite.test()
        def test_first() -> None:
            execution_order.append(1)

        @suite.test()
        def test_second() -> None:
            execution_order.append(2)

        runner = TestRunner(session)
        runner.run()

        expected_test_count = 2
        assert len(execution_order) == expected_test_count

    def test_suite_max_concurrency_takes_min_with_session(self) -> None:
        """Effective concurrency is min(session, suite.max_concurrency)."""
        # Given: session with concurrency=2, suite with higher max_concurrency=10
        session = ProTestSession(concurrency=2)
        suite = ProTestSuite("high_cap_suite", max_concurrency=10)
        session.add_suite(suite)
        tracker = ConcurrencyTracker()

        register_concurrent_tests(suite, count=4, tracker=tracker)

        # When: running tests
        runner = TestRunner(session)
        runner.run()

        # Then: effective concurrency capped at session level (2)
        expected_max = 2
        assert tracker.max_seen <= expected_max


class TestRunnerParallelExecution:
    """Parallel test execution."""

    def test_runner_respects_concurrency_limit(self) -> None:
        """Runner limits concurrent tests to session.concurrency."""
        # Given: session with concurrency=2 and 3 tests
        session = ProTestSession(concurrency=2)
        suite = ProTestSuite("test_suite")
        session.add_suite(suite)
        tracker = ConcurrencyTracker()

        register_concurrent_tests(suite, count=3, tracker=tracker)

        # When: running tests
        runner = TestRunner(session)
        runner.run()

        # Then: max concurrent tests never exceeds session concurrency
        expected_max_concurrency = 2
        assert tracker.max_seen <= expected_max_concurrency

    def test_parallel_execution_faster_than_sequential(self) -> None:
        """Parallel execution should be faster than sequential."""
        session = ProTestSession(concurrency=3)

        @session.test()
        async def test_a() -> None:
            await asyncio.sleep(0.1)

        @session.test()
        async def test_b() -> None:
            await asyncio.sleep(0.1)

        @session.test()
        async def test_c() -> None:
            await asyncio.sleep(0.1)

        runner = TestRunner(session)
        start = time.perf_counter()
        runner.run()
        duration = time.perf_counter() - start

        sequential_would_take = 0.3
        assert duration < sequential_would_take


class TestRunnerCollectionEvent:
    """COLLECTION_FINISH event allows filtering tests."""

    def test_collection_finish_event_emitted(
        self, event_collector: tuple[PluginBase, CollectedEvents]
    ) -> None:
        """COLLECTION_FINISH event is emitted with collected items."""
        plugin, collected = event_collector
        session = ProTestSession()
        session.use(plugin)

        @session.test()
        def test_a() -> None:
            pass

        @session.test()
        def test_b() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        expected_collected_count = 2
        assert len(collected.collection_items) == expected_collected_count

    def test_collection_finish_can_filter_tests(self) -> None:
        """COLLECTION_FINISH handler can filter which tests run."""
        session = ProTestSession()
        executed: list[str] = []

        class FilterPlugin(PluginBase):
            def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
                return [
                    item
                    for item in items
                    if "run" in getattr(item.func, "__name__", "")
                ]

        session.use(FilterPlugin())

        @session.test()
        def test_run_this() -> None:
            executed.append("run_this")

        @session.test()
        def test_skip_this() -> None:
            executed.append("skip_this")

        runner = TestRunner(session)
        runner.run()

        assert executed == ["run_this"]


class TestRunnerSmartTeardown:
    """Suite teardown happens only after last chunk of that suite."""

    def test_suite_fixture_available_throughout_suite_tests(self) -> None:
        """Suite-scoped fixture remains available for all suite tests."""
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.add_suite(suite)

        @suite.fixture()
        def suite_resource() -> str:
            return "resource_value"

        results: list[str] = []

        @suite.test()
        def test_first(res: Annotated[str, Use(suite_resource)]) -> None:
            results.append(res)

        @suite.test()
        def test_second(res: Annotated[str, Use(suite_resource)]) -> None:
            results.append(res)

        runner = TestRunner(session)
        runner.run()

        expected_result_count = 2
        assert len(results) == expected_result_count
        assert all(res == "resource_value" for res in results)

    def test_suite_teardown_called_after_all_suite_tests(self) -> None:
        """Suite generator fixture teardown runs after all suite tests complete."""
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.add_suite(suite)

        teardown_at_test_count = -1
        test_execution_count = 0

        @suite.fixture()
        def tracked_fixture():
            yield "tracked"
            nonlocal teardown_at_test_count, test_execution_count
            teardown_at_test_count = test_execution_count

        @suite.test()
        def test_one(val: Annotated[str, Use(tracked_fixture)]) -> None:
            nonlocal test_execution_count
            test_execution_count += 1

        @suite.test()
        def test_two(val: Annotated[str, Use(tracked_fixture)]) -> None:
            nonlocal test_execution_count
            test_execution_count += 1

        runner = TestRunner(session)
        runner.run()

        expected_test_count = 2
        assert test_execution_count == expected_test_count
        assert teardown_at_test_count == expected_test_count


class TestRunnerNestedSuites:
    """Tests for nested suite execution."""

    def test_runner_executes_nested_suite_tests(self) -> None:
        """Runner executes tests in nested suites."""
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        executed: list[str] = []

        @parent.test()
        def parent_test() -> None:
            executed.append("parent")

        @child.test()
        def child_test() -> None:
            executed.append("child")

        runner = TestRunner(session)
        runner.run()

        assert "parent" in executed
        assert "child" in executed

    def test_nested_suite_uses_parent_fixture(self) -> None:
        """Nested suite tests can use parent suite's fixtures."""
        session = ProTestSession()
        parent = ProTestSuite("Parent")
        child = ProTestSuite("Child")
        parent.add_suite(child)
        session.add_suite(parent)

        @parent.fixture()
        def parent_resource() -> str:
            return "parent_data"

        results: list[str] = []

        @child.test()
        def child_test(res: Annotated[str, Use(parent_resource)]) -> None:
            results.append(res)

        runner = TestRunner(session)
        runner.run()

        assert results == ["parent_data"]


class TestRunnerExitFirst:
    """Tests for -x / --exitfirst behavior."""

    def test_exitfirst_stops_after_first_failure(self) -> None:
        """With exitfirst=True, remaining tests are cancelled after first failure."""
        # Given: session with exitfirst enabled and mix of fast/slow tests
        session = ProTestSession(concurrency=4)
        session.exitfirst = True
        executed: list[str] = []

        @session.test()
        async def test_slow_pass() -> None:
            await asyncio.sleep(0.1)
            executed.append("slow_pass")

        @session.test()
        async def test_fast_fail() -> None:
            await asyncio.sleep(0.01)
            executed.append("fast_fail")
            raise ValueError("intentional failure")

        @session.test()
        async def test_slow_pass_2() -> None:
            await asyncio.sleep(0.1)
            executed.append("slow_pass_2")

        @session.test()
        async def test_slow_pass_3() -> None:
            await asyncio.sleep(0.1)
            executed.append("slow_pass_3")

        # When: running tests
        runner = TestRunner(session)
        result = runner.run()

        # Then: stops after first failure, not all tests executed
        assert result is False
        assert "fast_fail" in executed
        executed_count = len(executed)
        total_tests = 4
        assert executed_count < total_tests

    def test_exitfirst_false_runs_all_tests(self) -> None:
        """With exitfirst=False (default), all tests run even after failure."""
        session = ProTestSession(concurrency=4)
        session.exitfirst = False

        executed: list[str] = []

        @session.test()
        async def test_pass_1() -> None:
            await asyncio.sleep(0.01)
            executed.append("pass_1")

        @session.test()
        async def test_fail() -> None:
            await asyncio.sleep(0.01)
            executed.append("fail")
            raise ValueError("intentional failure")

        @session.test()
        async def test_pass_2() -> None:
            await asyncio.sleep(0.01)
            executed.append("pass_2")

        runner = TestRunner(session)
        runner.run()

        expected_count = 3
        assert len(executed) == expected_count

    def test_exitfirst_stops_on_error(self) -> None:
        """exitfirst also stops on fixture errors."""
        session = ProTestSession(concurrency=4)
        session.exitfirst = True

        executed: list[str] = []

        @session.fixture()
        def broken_fixture() -> str:
            raise RuntimeError("fixture error")

        @session.test()
        async def test_fast_error(val: Annotated[str, Use(broken_fixture)]) -> None:
            await asyncio.sleep(0.01)
            executed.append("fast_error")

        @session.test()
        async def test_slow_pass() -> None:
            await asyncio.sleep(0.1)
            executed.append("slow_pass")

        runner = TestRunner(session)
        result = runner.run()

        assert result is False
        assert "fast_error" not in executed

    def test_exitfirst_across_chunks(self) -> None:
        """exitfirst stops processing subsequent chunks."""
        session = ProTestSession(concurrency=1)
        session.exitfirst = True

        suite1 = ProTestSuite("Suite1")
        suite2 = ProTestSuite("Suite2")
        session.add_suite(suite1)
        session.add_suite(suite2)

        executed: list[str] = []

        @suite1.test()
        def test_suite1_fail() -> None:
            executed.append("suite1_fail")
            raise ValueError("fail")

        @suite2.test()
        def test_suite2_should_not_run() -> None:
            executed.append("suite2")

        runner = TestRunner(session)
        runner.run()

        assert "suite1_fail" in executed
        assert "suite2" not in executed
