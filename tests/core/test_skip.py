"""Test skip functionality."""

from typing import Annotated

from protest import ForEach, From, ProTestSession, ProTestSuite
from protest.core.collector import Collector
from protest.core.runner import TestRunner


class TestSkipDecorator:
    def test_skip_with_bool_sets_default_reason(self) -> None:
        session = ProTestSession()

        @session.test(skip=True)
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip_reason == "Skipped"

    def test_skip_with_string_sets_reason(self) -> None:
        session = ProTestSession()

        @session.test(skip="WIP: need auth refactor")
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip_reason == "WIP: need auth refactor"

    def test_no_skip_has_none_reason(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_normal() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip_reason is None

    def test_suite_skip_decorator(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("test")
        session.include_suite(suite)

        @suite.test(skip="Suite test skipped")
        def test_skipped() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        assert len(items) == 1
        assert items[0].skip_reason == "Suite test skipped"


class TestSkipExecution:
    def test_skipped_test_does_not_run(self) -> None:
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

    def test_skipped_test_counts_as_skipped(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: object) -> None:
                results["passed"] = result.passed  # type: ignore[attr-defined]
                results["skipped"] = result.skipped  # type: ignore[attr-defined]
                results["failed"] = result.failed  # type: ignore[attr-defined]

        session.use(CountingPlugin())

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

    def test_skipped_test_emits_skip_event(self) -> None:
        session = ProTestSession()
        skip_results: list[object] = []

        class SkipPlugin:
            def on_test_skip(self, result: object) -> None:
                skip_results.append(result)

        session.use(SkipPlugin())

        @session.test(skip="My reason")
        def test_skipped() -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        assert len(skip_results) == 1
        assert skip_results[0].skip_reason == "My reason"  # type: ignore[attr-defined]


class TestSkipWithParameterizedTests:
    def test_skip_applies_to_all_variations(self) -> None:
        session = ProTestSession()
        executed = []

        VALUES = ForEach([1, 2, 3])  # noqa: N806

        @session.test(skip="Skip all variations")
        def test_parameterized(val: Annotated[int, From(VALUES)]) -> None:
            executed.append(val)

        runner = TestRunner(session)
        runner.run()

        assert executed == []

    def test_skip_counts_all_variations(self) -> None:
        session = ProTestSession()
        results: dict[str, int] = {}

        class CountingPlugin:
            def on_session_complete(self, result: object) -> None:
                results["skipped"] = result.skipped  # type: ignore[attr-defined]

        session.use(CountingPlugin())

        VALUES = ForEach([1, 2, 3])  # noqa: N806

        @session.test(skip=True)
        def test_parameterized(val: Annotated[int, From(VALUES)]) -> None:
            pass

        runner = TestRunner(session)
        runner.run()

        expected_skipped_count = 3
        assert results["skipped"] == expected_skipped_count
