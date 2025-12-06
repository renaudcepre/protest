"""Tests for combinations of --lf, -x (exitfirst), and tag filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest import ProTestSession, run_session
from protest.cache.storage import CacheStorage

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Return a temporary cache directory."""
    return tmp_path / ".protest"


def create_session(cache_dir: Path) -> ProTestSession:
    """Create a fresh session with the given cache directory."""
    session = ProTestSession(default_reporter=False, default_cache=True)
    session._cache_storage = CacheStorage(cache_dir=cache_dir, cache_file="cache.json")
    return session


class TestLastFailedWithTags:
    """Tests for --lf combined with tag filtering."""

    def test_lf_and_include_tag_intersection(self, cache_dir: Path) -> None:
        """--lf --tag X returns only failed tests that have tag X."""
        session1 = create_session(cache_dir)
        first_run_executed: list[str] = []

        @session1.test(tags=["slow"])
        def test_slow_fail() -> None:
            first_run_executed.append("slow")
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_fail() -> None:
            first_run_executed.append("fast")
            raise AssertionError("fails")

        @session1.test(tags=["slow"])
        def test_slow_pass() -> None:
            first_run_executed.append("slow_pass")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_fail_2() -> None:
            second_run_executed.append("slow")

        test_slow_fail_2.__name__ = "test_slow_fail"

        @session2.test(tags=["fast"])
        def test_fast_fail_2() -> None:
            second_run_executed.append("fast")

        test_fast_fail_2.__name__ = "test_fast_fail"

        @session2.test(tags=["slow"])
        def test_slow_pass_2() -> None:
            second_run_executed.append("slow_pass")

        test_slow_pass_2.__name__ = "test_slow_pass"

        success = run_session(session2, last_failed=True, include_tags={"slow"})

        assert success is True
        assert second_run_executed == ["slow"]

    def test_lf_and_exclude_tag_intersection(self, cache_dir: Path) -> None:
        """--lf --exclude-tag X returns failed tests that don't have tag X."""
        session1 = create_session(cache_dir)

        @session1.test(tags=["slow"])
        def test_slow_fail() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_fail() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_fail_2() -> None:
            second_run_executed.append("slow")

        test_slow_fail_2.__name__ = "test_slow_fail"

        @session2.test(tags=["fast"])
        def test_fast_fail_2() -> None:
            second_run_executed.append("fast")

        test_fast_fail_2.__name__ = "test_fast_fail"

        success = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert success is True
        assert second_run_executed == ["fast"]

    def test_lf_exclude_tag_results_in_zero_tests(self, cache_dir: Path) -> None:
        """--lf --exclude-tag X with all failed tests having tag X = 0 tests."""
        session1 = create_session(cache_dir)

        @session1.test(tags=["slow"])
        def test_slow_1() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["slow"])
        def test_slow_2() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_pass() -> None:
            pass

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_1_v2() -> None:
            second_run_executed.append("slow_1")

        test_slow_1_v2.__name__ = "test_slow_1"

        @session2.test(tags=["slow"])
        def test_slow_2_v2() -> None:
            second_run_executed.append("slow_2")

        test_slow_2_v2.__name__ = "test_slow_2"

        @session2.test(tags=["fast"])
        def test_fast_pass_v2() -> None:
            second_run_executed.append("fast")

        test_fast_pass_v2.__name__ = "test_fast_pass"

        success = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert success is True
        assert second_run_executed == []

    def test_lf_with_tag_no_matching_failures(self, cache_dir: Path) -> None:
        """--lf --tag X where no failed test has tag X falls back to all matching tag X."""
        session1 = create_session(cache_dir)

        @session1.test(tags=["slow"])
        def test_slow_pass() -> None:
            pass

        @session1.test(tags=["fast"])
        def test_fast_fail() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_pass_v2() -> None:
            second_run_executed.append("slow")

        test_slow_pass_v2.__name__ = "test_slow_pass"

        @session2.test(tags=["fast"])
        def test_fast_fail_v2() -> None:
            second_run_executed.append("fast")

        test_fast_fail_v2.__name__ = "test_fast_fail"

        success = run_session(session2, last_failed=True, include_tags={"slow"})

        assert success is True
        assert second_run_executed == ["slow"]


class TestLastFailedWithExitFirst:
    """Tests for --lf combined with -x (exitfirst)."""

    def test_lf_exitfirst_stops_on_failure(self, cache_dir: Path) -> None:
        """--lf -x stops after first failure among failed tests."""
        session1 = create_session(cache_dir)

        @session1.test()
        def test_fail_1() -> None:
            raise AssertionError("fails")

        @session1.test()
        def test_fail_2() -> None:
            raise AssertionError("fails")

        @session1.test()
        def test_pass() -> None:
            pass

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test()
        def test_fail_1_v2() -> None:
            second_run_executed.append("fail_1")
            raise AssertionError("still fails")

        test_fail_1_v2.__name__ = "test_fail_1"

        @session2.test()
        def test_fail_2_v2() -> None:
            second_run_executed.append("fail_2")
            raise AssertionError("still fails")

        test_fail_2_v2.__name__ = "test_fail_2"

        @session2.test()
        def test_pass_v2() -> None:
            second_run_executed.append("pass")

        test_pass_v2.__name__ = "test_pass"

        success = run_session(session2, last_failed=True, exitfirst=True)

        assert success is False
        assert "fail_1" in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed

    def test_exitfirst_then_lf_runs_only_failed(self, cache_dir: Path) -> None:
        """After -x run, --lf should run only the test that failed."""
        session1 = create_session(cache_dir)
        first_run_executed: list[str] = []

        @session1.test()
        def test_a() -> None:
            first_run_executed.append("a")

        @session1.test()
        def test_b() -> None:
            first_run_executed.append("b")
            raise AssertionError("fails")

        @session1.test()
        def test_c() -> None:
            first_run_executed.append("c")

        success_first = run_session(session1, exitfirst=True)
        assert success_first is False

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test()
        def test_a_v2() -> None:
            second_run_executed.append("a")

        test_a_v2.__name__ = "test_a"

        @session2.test()
        def test_b_v2() -> None:
            second_run_executed.append("b")

        test_b_v2.__name__ = "test_b"

        @session2.test()
        def test_c_v2() -> None:
            second_run_executed.append("c")

        test_c_v2.__name__ = "test_c"

        success_second = run_session(session2, last_failed=True)

        assert success_second is True
        assert second_run_executed == ["b"]

    def test_exitfirst_partial_cache_then_lf_fallback(self, cache_dir: Path) -> None:
        """After -x with failure fixed, --lf falls back to all tests."""
        session1 = create_session(cache_dir)

        @session1.test()
        def test_only_one() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test()
        def test_only_one_v2() -> None:
            second_run_executed.append("only_one")

        test_only_one_v2.__name__ = "test_only_one"

        @session2.test()
        def test_new() -> None:
            second_run_executed.append("new")

        success = run_session(session2, last_failed=True)

        assert success is True
        assert "only_one" in second_run_executed
        expected_test_count = 1
        assert len(second_run_executed) == expected_test_count


class TestTagsWithExitFirst:
    """Tests for tag filtering combined with -x (exitfirst)."""

    def test_tag_filter_with_exitfirst(self) -> None:
        """--tag X -x stops after first failure among tagged tests."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test(tags=["unit"])
        def test_unit_1() -> None:
            executed.append("unit_1")
            raise AssertionError("fails")

        @session.test(tags=["unit"])
        def test_unit_2() -> None:
            executed.append("unit_2")

        @session.test(tags=["integration"])
        def test_integration() -> None:
            executed.append("integration")
            raise AssertionError("should not run")

        success = run_session(session, include_tags={"unit"}, exitfirst=True)

        assert success is False
        assert "unit_1" in executed
        assert "integration" not in executed

    def test_exclude_tag_with_exitfirst(self) -> None:
        """--exclude-tag X -x stops after first failure, skipping excluded."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test(tags=["slow"])
        def test_slow() -> None:
            executed.append("slow")
            raise AssertionError("should not run")

        @session.test(tags=["fast"])
        def test_fast_fail() -> None:
            executed.append("fast_fail")
            raise AssertionError("fails")

        @session.test(tags=["fast"])
        def test_fast_pass() -> None:
            executed.append("fast_pass")

        success = run_session(session, exclude_tags={"slow"}, exitfirst=True)

        assert success is False
        assert "slow" not in executed
        assert "fast_fail" in executed


class TestAllThreeCombined:
    """Tests combining --lf, -x, and tag filters."""

    def test_lf_tag_exitfirst_together(self, cache_dir: Path) -> None:
        """--lf --tag X -x: failed + tagged, stop on first failure."""
        session1 = create_session(cache_dir)

        @session1.test(tags=["slow"])
        def test_slow_fail_1() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["slow"])
        def test_slow_fail_2() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_fail() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_fail_1_v2() -> None:
            second_run_executed.append("slow_1")
            raise AssertionError("still fails")

        test_slow_fail_1_v2.__name__ = "test_slow_fail_1"

        @session2.test(tags=["slow"])
        def test_slow_fail_2_v2() -> None:
            second_run_executed.append("slow_2")
            raise AssertionError("still fails")

        test_slow_fail_2_v2.__name__ = "test_slow_fail_2"

        @session2.test(tags=["fast"])
        def test_fast_fail_v2() -> None:
            second_run_executed.append("fast")
            raise AssertionError("should not run - wrong tag")

        test_fast_fail_v2.__name__ = "test_fast_fail"

        success = run_session(
            session2, last_failed=True, include_tags={"slow"}, exitfirst=True
        )

        assert success is False
        assert "slow_1" in second_run_executed
        assert "fast" not in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed

    def test_lf_exclude_tag_exitfirst_together(self, cache_dir: Path) -> None:
        """--lf --exclude-tag X -x: failed without tag, stop on first failure."""
        session1 = create_session(cache_dir)

        @session1.test(tags=["slow"])
        def test_slow_fail() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_fail_1() -> None:
            raise AssertionError("fails")

        @session1.test(tags=["fast"])
        def test_fast_fail_2() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        second_run_executed: list[str] = []

        @session2.test(tags=["slow"])
        def test_slow_fail_v2() -> None:
            second_run_executed.append("slow")
            raise AssertionError("should not run - excluded")

        test_slow_fail_v2.__name__ = "test_slow_fail"

        @session2.test(tags=["fast"])
        def test_fast_fail_1_v2() -> None:
            second_run_executed.append("fast_1")
            raise AssertionError("still fails")

        test_fast_fail_1_v2.__name__ = "test_fast_fail_1"

        @session2.test(tags=["fast"])
        def test_fast_fail_2_v2() -> None:
            second_run_executed.append("fast_2")
            raise AssertionError("still fails")

        test_fast_fail_2_v2.__name__ = "test_fast_fail_2"

        success = run_session(
            session2, last_failed=True, exclude_tags={"slow"}, exitfirst=True
        )

        assert success is False
        assert "slow" not in second_run_executed
        assert "fast_1" in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed
