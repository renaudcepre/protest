"""Tests for parameterized tests with ForEach and From."""

from dataclasses import dataclass
from typing import Annotated

import pytest

from protest import ForEach, From, ProTestSession, ProTestSuite, Use
from protest.core.collector import Collector
from protest.core.runner import TestRunner
from protest.di.decorators import fixture


@dataclass
class Scenario:
    name: str
    value: int
    expected: bool

    def __repr__(self) -> str:
        return self.name


class TestForEach:
    """Tests for ForEach container."""

    def test_foreach_stores_cases(self) -> None:
        cases = ForEach([1, 2, 3])

        assert len(cases) == 3
        assert list(cases) == [1, 2, 3]

    def test_foreach_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one case"):
            ForEach([])

    def test_foreach_get_id_default_uses_repr(self) -> None:
        cases = ForEach([42, "hello"])

        assert cases.get_id(42) == "42"
        assert cases.get_id("hello") == "'hello'"

    def test_foreach_get_id_custom(self) -> None:
        cases = ForEach([1, 2, 3], ids=lambda x: f"num_{x}")

        assert cases.get_id(1) == "num_1"
        assert cases.get_id(2) == "num_2"


class TestParameterizedCollection:
    """Tests for test collection with From() parameters."""

    def test_single_foreach(self) -> None:
        session = ProTestSession()
        numbers = ForEach([1, 2, 3])

        @session.test()
        def test_numbers(num: Annotated[int, From(numbers)]) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 3
        assert len(items) == expected_item_count

        assert items[0].case_ids == ["1"]
        assert items[1].case_ids == ["2"]
        assert items[2].case_ids == ["3"]

        assert items[0].case_kwargs == {"num": 1}
        assert items[1].case_kwargs == {"num": 2}
        assert items[2].case_kwargs == {"num": 3}

        assert items[0].node_id.endswith("[1]")
        assert items[0].test_name == "test_numbers"

    def test_dataclass_with_custom_ids(self) -> None:
        session = ProTestSession()

        scenarios = ForEach(
            [
                Scenario("positive", 10, True),
                Scenario("zero", 0, False),
            ],
            ids=lambda s: s.name,
        )

        @session.test()
        def test_scenario(case: Annotated[Scenario, From(scenarios)]) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 2
        assert len(items) == expected_item_count
        assert items[0].case_ids == ["positive"]
        assert items[1].case_ids == ["zero"]

    def test_cartesian_product(self) -> None:
        session = ProTestSession()

        users = ForEach(["alice", "bob"], ids=lambda u: u)
        roles = ForEach(["admin", "user"], ids=lambda r: r)

        @session.test()
        def test_matrix(
            user: Annotated[str, From(users)],
            role: Annotated[str, From(roles)],
        ) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 4
        assert len(items) == expected_item_count

        all_case_ids = [item.case_ids for item in items]
        assert ["alice", "admin"] in all_case_ids
        assert ["alice", "user"] in all_case_ids
        assert ["bob", "admin"] in all_case_ids
        assert ["bob", "user"] in all_case_ids

    def test_foreach_with_fixtures(self) -> None:
        session = ProTestSession()

        @fixture()
        def multiplier() -> int:
            return 10

        session.fixture(multiplier)

        numbers = ForEach([1, 2, 3])

        @session.test()
        def test_combined(
            num: Annotated[int, From(numbers)],
            mult: Annotated[int, Use(multiplier)],
        ) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 3
        assert len(items) == expected_item_count
        assert "mult" not in items[0].case_kwargs
        assert "num" in items[0].case_kwargs

    def test_no_foreach_single_item(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_simple() -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 1
        assert len(items) == expected_item_count
        assert items[0].case_kwargs == {}
        assert items[0].case_ids == []
        assert "[" not in items[0].node_id

    def test_triple_cartesian(self) -> None:
        session = ProTestSession()

        a_vals = ForEach([1, 2])
        b_vals = ForEach(["x", "y"])
        c_vals = ForEach([True, False])

        @session.test()
        def test_triple(
            a_val: Annotated[int, From(a_vals)],
            b_val: Annotated[str, From(b_vals)],
            c_val: Annotated[bool, From(c_vals)],
        ) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        expected_item_count = 8
        assert len(items) == expected_item_count

    def test_structured_data_for_reporters(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("API")
        session.include_suite(suite)

        users = ForEach(["alice"], ids=lambda u: u)

        @suite.test()
        def test_user(user: Annotated[str, From(users)]) -> None:
            pass

        collector = Collector()
        items = collector.collect(session)

        item = items[0]
        assert item.test_name == "test_user"
        assert item.suite_path == "API"
        assert item.case_ids == ["alice"]
        assert item.case_kwargs == {"user": "alice"}
        assert "API" in item.node_id
        assert "[alice]" in item.node_id


class TestParameterizedExecution:
    """Tests for actual execution of parameterized tests."""

    def test_foreach_values_injected(self) -> None:
        session = ProTestSession()
        collected_values: list[int] = []

        numbers = ForEach([10, 20, 30])

        @session.test()
        def test_collect(num: Annotated[int, From(numbers)]) -> None:
            collected_values.append(num)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert sorted(collected_values) == [10, 20, 30]

    def test_cartesian_product_execution(self) -> None:
        session = ProTestSession()
        collected_pairs: list[tuple[str, str]] = []

        users = ForEach(["alice", "bob"], ids=lambda u: u)
        roles = ForEach(["admin", "user"], ids=lambda r: r)

        @session.test()
        def test_pairs(
            user: Annotated[str, From(users)],
            role: Annotated[str, From(roles)],
        ) -> None:
            collected_pairs.append((user, role))

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        expected_pair_count = 4
        assert len(collected_pairs) == expected_pair_count
        assert ("alice", "admin") in collected_pairs
        assert ("alice", "user") in collected_pairs
        assert ("bob", "admin") in collected_pairs
        assert ("bob", "user") in collected_pairs

    def test_foreach_with_fixture_execution(self) -> None:
        session = ProTestSession()
        results: list[int] = []

        @fixture()
        def multiplier() -> int:
            return 10

        session.fixture(multiplier)

        numbers = ForEach([1, 2, 3])

        @session.test()
        def test_multiply(
            num: Annotated[int, From(numbers)],
            mult: Annotated[int, Use(multiplier)],
        ) -> None:
            results.append(num * mult)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert sorted(results) == [10, 20, 30]

    def test_foreach_failure_reported_correctly(self) -> None:
        session = ProTestSession()

        numbers = ForEach([1, 2, 3])

        @session.test()
        def test_fail_on_two(num: Annotated[int, From(numbers)]) -> None:
            assert num != 2, f"Failed on {num}"

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
