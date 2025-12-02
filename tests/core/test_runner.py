"""Tests for TestRunner - the core test execution engine."""

import asyncio
import time
from typing import Annotated

from protest import ProTestSession, ProTestSuite, Use
from protest.core.collector import TestItem
from protest.core.runner import TestRunner
from protest.events.data import SessionResult, TestResult
from protest.plugin import PluginBase


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

    def test_runner_emits_session_events(self) -> None:
        """Runner emits SESSION_START, SESSION_END, SESSION_COMPLETE."""
        session = ProTestSession()
        events_received: list[str] = []

        class EventCollector(PluginBase):
            def on_session_start(self) -> None:
                events_received.append("session_start")

            def on_session_end(self, result: SessionResult) -> None:
                events_received.append("session_end")

            def on_session_complete(self, result: SessionResult) -> None:
                events_received.append("session_complete")

        session.use(EventCollector())

        @session.test()
        def simple_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert "session_start" in events_received
        assert "session_end" in events_received
        assert "session_complete" in events_received

    def test_runner_emits_test_pass_event(self) -> None:
        """Runner emits TEST_PASS for passing tests."""
        session = ProTestSession()
        results: list[TestResult] = []

        class ResultCollector(PluginBase):
            def on_test_pass(self, result: TestResult) -> None:
                results.append(result)

        session.use(ResultCollector())

        @session.test()
        def my_passing_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        assert results[0].name == "my_passing_test"
        assert results[0].error is None

    def test_runner_emits_test_fail_event(self) -> None:
        """Runner emits TEST_FAIL for failing tests."""
        session = ProTestSession()
        results: list[TestResult] = []

        class ResultCollector(PluginBase):
            def on_test_fail(self, result: TestResult) -> None:
                results.append(result)

        session.use(ResultCollector())

        @session.test()
        def my_failing_test() -> None:
            raise ValueError("test error")

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        assert results[0].name == "my_failing_test"
        assert isinstance(results[0].error, ValueError)


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

    def test_runner_emits_suite_events(self) -> None:
        """Runner emits SUITE_START and SUITE_END."""
        session = ProTestSession()
        suite = ProTestSuite("my_suite")
        session.add_suite(suite)
        events_received: list[tuple[str, str]] = []

        class SuiteEventCollector(PluginBase):
            def on_suite_start(self, name: str) -> None:
                events_received.append(("start", name))

            def on_suite_end(self, name: str) -> None:
                events_received.append(("end", name))

        session.use(SuiteEventCollector())

        @suite.test()
        def suite_test() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert ("start", "my_suite") in events_received
        assert ("end", "my_suite") in events_received

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
        session = ProTestSession(concurrency=2)
        suite = ProTestSuite("high_cap_suite", max_concurrency=10)
        session.add_suite(suite)

        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        @suite.test()
        async def test_a() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        @suite.test()
        async def test_b() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        @suite.test()
        async def test_c() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        @suite.test()
        async def test_d() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        runner = TestRunner(session)
        runner.run()

        expected_max = 2
        assert max_concurrent <= expected_max


class TestRunnerParallelExecution:
    """Parallel test execution."""

    def test_runner_respects_concurrency_limit(self) -> None:
        """Runner limits concurrent tests to session.concurrency."""
        session = ProTestSession(concurrency=2)
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        @session.test()
        async def test_a() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        @session.test()
        async def test_b() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        @session.test()
        async def test_c() -> None:
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        runner = TestRunner(session)
        runner.run()

        expected_max_concurrency = 2
        assert max_concurrent <= expected_max_concurrency

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

    def test_collection_finish_event_emitted(self) -> None:
        """COLLECTION_FINISH event is emitted with collected items."""
        session = ProTestSession()
        collected_items: list[TestItem] = []

        class CollectionCollector(PluginBase):
            def on_collection_finish(self, items: list[TestItem]) -> list[TestItem]:
                collected_items.extend(items)
                return items

        session.use(CollectionCollector())

        @session.test()
        def test_a() -> None:
            pass

        @session.test()
        def test_b() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        expected_collected_count = 2
        assert len(collected_items) == expected_collected_count

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
