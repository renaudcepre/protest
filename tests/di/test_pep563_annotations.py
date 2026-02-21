"""Tests for PEP 563 (stringified annotations) support.

This file MUST use `from __future__ import annotations` to test that the resolver
correctly handles stringified annotations via get_type_hints().
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import pytest

from protest import ForEach, ProTestSession, fixture
from protest.core.runner import TestRunner
from protest.di.markers import From, Use
from protest.events.types import Event

if TYPE_CHECKING:
    from protest.entities import TestResult


@fixture()
def module_level_fixture() -> str:
    """Module-level fixture that can be resolved with PEP 563."""
    return "resolved_value"


@fixture()
def module_level_fixture_that_raises() -> str:
    """Module-level fixture that raises to test error handling."""
    raise RuntimeError("Fixture error")


# Module-level ForEach — mirrors real usage where ForEach is defined at module scope
module_numbers = ForEach([10, 20, 30])
module_numbers_short = ForEach([1, 2])


class TestPEP563Annotations:
    """Tests for PEP 563 stringified annotations support."""

    @pytest.fixture
    def session(self) -> ProTestSession:
        return ProTestSession()

    def test_resolves_module_level_fixture_with_future_annotations(
        self, session: ProTestSession
    ) -> None:
        """Fixture injection works with `from __future__ import annotations`."""
        captured_values: list[str] = []

        @session.test()
        def test_with_fixture(
            value: Annotated[str, Use(module_level_fixture)],
        ) -> None:
            captured_values.append(value)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert captured_values == ["resolved_value"]

    def test_fixture_error_detected_with_future_annotations(
        self, session: ProTestSession
    ) -> None:
        """Fixture errors are properly detected with stringified annotations."""
        results: list[TestResult] = []
        session.events.on(Event.TEST_FAIL, lambda r: results.append(r))

        @session.test()
        def test_with_broken_fixture(
            value: Annotated[str, Use(module_level_fixture_that_raises)],
        ) -> None:
            pass

        runner = TestRunner(session)
        result = runner.run()

        assert not result.success
        assert len(results) == 1
        assert results[0].is_fixture_error
        assert "Fixture error" in str(results[0].error)

    def test_from_params_resolved_with_future_annotations(
        self, session: ProTestSession
    ) -> None:
        """ForEach/From parameterization works with `from __future__ import annotations`."""
        captured_values: list[int] = []

        @session.test()
        def test_parameterized(
            num: Annotated[int, From(module_numbers)],
        ) -> None:
            captured_values.append(num)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert sorted(captured_values) == [10, 20, 30]

    def test_from_and_use_combined_with_future_annotations(
        self, session: ProTestSession
    ) -> None:
        """From() + Use() in same test works with `from __future__ import annotations`."""
        captured: list[tuple[str, int]] = []

        @session.test()
        def test_combined(
            value: Annotated[str, Use(module_level_fixture)],
            num: Annotated[int, From(module_numbers_short)],
        ) -> None:
            captured.append((value, num))

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert len(captured) == 2
        assert all(v == "resolved_value" for v, _ in captured)
        assert sorted(n for _, n in captured) == [1, 2]
