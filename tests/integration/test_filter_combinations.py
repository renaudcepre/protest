"""Tests for combinations of --lf, -x (exitfirst), tag, suite, and keyword filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest import ProTestSession, ProTestSuite, run_session
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

        result = run_session(session2, last_failed=True, include_tags={"slow"})

        assert result.success is True
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

        result = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert result.success is True
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

        result = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert result.success is True
        assert second_run_executed == []

    def test_lf_with_tag_no_matching_failures(self, cache_dir: Path) -> None:
        """--lf --tag X where no failed test has tag X runs 0 tests (no fallback)."""
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

        result = run_session(session2, last_failed=True, include_tags={"slow"})

        assert result.success is True
        assert second_run_executed == []


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

        result = run_session(session2, last_failed=True, exitfirst=True)

        assert result.success is False
        expected_executed_count = 1
        assert len(second_run_executed) == expected_executed_count
        assert second_run_executed[0] in ("fail_1", "fail_2")

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

        result_first = run_session(session1, exitfirst=True)
        assert result_first.success is False

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

        result_second = run_session(session2, last_failed=True)

        assert result_second.success is True
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

        result = run_session(session2, last_failed=True)

        assert result.success is True
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

        result = run_session(session, include_tags={"unit"}, exitfirst=True)

        assert result.success is False
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

        result = run_session(session, exclude_tags={"slow"}, exitfirst=True)

        assert result.success is False
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

        result = run_session(
            session2, last_failed=True, include_tags={"slow"}, exitfirst=True
        )

        assert result.success is False
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

        result = run_session(
            session2, last_failed=True, exclude_tags={"slow"}, exitfirst=True
        )

        assert result.success is False
        assert "slow" not in second_run_executed
        assert "fast_1" in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed


class TestSuiteFilter:
    """Tests for suite filtering (::SuiteName syntax)."""

    def test_suite_filter_basic(self) -> None:
        """Suite filter runs only tests in specified suite."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @session.test()
        def test_standalone() -> None:
            executed.append("standalone")

        @api_suite.test()
        def test_api() -> None:
            executed.append("api")

        result = run_session(session, suite_filter="API")

        assert result.success is True
        assert executed == ["api"]

    def test_suite_filter_with_nested_suites(self) -> None:
        """Suite filter includes child suites."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        users_suite = ProTestSuite("Users")
        api_suite.add_suite(users_suite)
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test()
        def test_api() -> None:
            executed.append("api")

        @users_suite.test()
        def test_users() -> None:
            executed.append("users")

        result = run_session(session, suite_filter="API")

        assert result.success is True
        assert set(executed) == {"api", "users"}

    def test_suite_filter_specific_child(self) -> None:
        """Suite filter for nested suite excludes parent tests."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        users_suite = ProTestSuite("Users")
        api_suite.add_suite(users_suite)
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test()
        def test_api() -> None:
            executed.append("api")

        @users_suite.test()
        def test_users() -> None:
            executed.append("users")

        result = run_session(session, suite_filter="API::Users")

        assert result.success is True
        assert executed == ["users"]

    def test_suite_filter_nonexistent(self) -> None:
        """Suite filter with nonexistent suite runs zero tests."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test()
        def test_api() -> None:
            executed.append("api")

        result = run_session(session, suite_filter="NonExistent")

        assert result.success is True
        assert executed == []


class TestKeywordFilter:
    """Tests for keyword filtering (-k flag)."""

    def test_keyword_filter_basic(self) -> None:
        """Keyword filter matches test names."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test()
        def test_login() -> None:
            executed.append("login")

        @session.test()
        def test_logout() -> None:
            executed.append("logout")

        @session.test()
        def test_dashboard() -> None:
            executed.append("dashboard")

        result = run_session(session, keyword_patterns=["login"])

        assert result.success is True
        assert executed == ["login"]

    def test_keyword_filter_substring(self) -> None:
        """Keyword filter matches substrings."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test()
        def test_user_login() -> None:
            executed.append("user_login")

        @session.test()
        def test_admin_login() -> None:
            executed.append("admin_login")

        @session.test()
        def test_logout() -> None:
            executed.append("logout")

        result = run_session(session, keyword_patterns=["login"])

        assert result.success is True
        assert set(executed) == {"user_login", "admin_login"}

    def test_keyword_filter_multiple_or_logic(self) -> None:
        """Multiple keyword patterns use OR logic."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test()
        def test_login() -> None:
            executed.append("login")

        @session.test()
        def test_auth() -> None:
            executed.append("auth")

        @session.test()
        def test_dashboard() -> None:
            executed.append("dashboard")

        result = run_session(session, keyword_patterns=["login", "auth"])

        assert result.success is True
        assert set(executed) == {"login", "auth"}

    def test_keyword_filter_no_match(self) -> None:
        """Keyword filter with no matches runs zero tests."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test()
        def test_login() -> None:
            executed.append("login")

        result = run_session(session, keyword_patterns=["nonexistent"])

        assert result.success is True
        assert executed == []


class TestSuiteFilterWithTags:
    """Tests for suite filter combined with tag filtering."""

    def test_suite_and_include_tag(self) -> None:
        """Suite filter + tag filter intersect."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test(tags=["slow"])
        def test_api_slow() -> None:
            executed.append("api_slow")

        @api_suite.test(tags=["fast"])
        def test_api_fast() -> None:
            executed.append("api_fast")

        @session.test(tags=["slow"])
        def test_standalone_slow() -> None:
            executed.append("standalone_slow")

        result = run_session(session, suite_filter="API", include_tags={"slow"})

        assert result.success is True
        assert executed == ["api_slow"]

    def test_suite_and_exclude_tag(self) -> None:
        """Suite filter + exclude tag filter."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test(tags=["slow"])
        def test_api_slow() -> None:
            executed.append("api_slow")

        @api_suite.test(tags=["fast"])
        def test_api_fast() -> None:
            executed.append("api_fast")

        result = run_session(session, suite_filter="API", exclude_tags={"slow"})

        assert result.success is True
        assert executed == ["api_fast"]


class TestKeywordFilterWithTags:
    """Tests for keyword filter combined with tag filtering."""

    def test_keyword_and_tag(self) -> None:
        """Keyword filter + tag filter intersect."""
        session = ProTestSession(default_reporter=False)
        executed: list[str] = []

        @session.test(tags=["api"])
        def test_login_api() -> None:
            executed.append("login_api")

        @session.test(tags=["api"])
        def test_logout_api() -> None:
            executed.append("logout_api")

        @session.test(tags=["unit"])
        def test_login_unit() -> None:
            executed.append("login_unit")

        result = run_session(session, keyword_patterns=["login"], include_tags={"api"})

        assert result.success is True
        assert executed == ["login_api"]


class TestSuiteAndKeywordCombined:
    """Tests for suite + keyword filters together."""

    def test_suite_and_keyword(self) -> None:
        """Suite filter + keyword filter intersect."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test()
        def test_api_login() -> None:
            executed.append("api_login")

        @api_suite.test()
        def test_api_logout() -> None:
            executed.append("api_logout")

        @session.test()
        def test_standalone_login() -> None:
            executed.append("standalone_login")

        result = run_session(session, suite_filter="API", keyword_patterns=["login"])

        assert result.success is True
        assert executed == ["api_login"]


class TestAllFiltersCombined:
    """Tests combining suite, keyword, tag, and --lf filters."""

    def test_suite_keyword_tag_combined(self) -> None:
        """Suite + keyword + tag filters all intersect."""
        session = ProTestSession(default_reporter=False)
        api_suite = ProTestSuite("API")
        session.add_suite(api_suite)
        executed: list[str] = []

        @api_suite.test(tags=["slow"])
        def test_api_login_slow() -> None:
            executed.append("api_login_slow")

        @api_suite.test(tags=["fast"])
        def test_api_login_fast() -> None:
            executed.append("api_login_fast")

        @api_suite.test(tags=["slow"])
        def test_api_logout_slow() -> None:
            executed.append("api_logout_slow")

        @session.test(tags=["slow"])
        def test_standalone_login_slow() -> None:
            executed.append("standalone_login_slow")

        result = run_session(
            session,
            suite_filter="API",
            keyword_patterns=["login"],
            include_tags={"slow"},
        )

        assert result.success is True
        assert executed == ["api_login_slow"]

    def test_suite_keyword_tag_lf_combined(self, cache_dir: Path) -> None:
        """Suite + keyword + tag + --lf filters all intersect."""
        session1 = create_session(cache_dir)
        api_suite1 = ProTestSuite("API")
        session1.add_suite(api_suite1)

        @api_suite1.test(tags=["slow"])
        def test_api_login_slow_fail() -> None:
            raise AssertionError("fails")

        @api_suite1.test(tags=["slow"])
        def test_api_login_slow_pass() -> None:
            pass

        @api_suite1.test(tags=["fast"])
        def test_api_login_fast_fail() -> None:
            raise AssertionError("fails")

        run_session(session1)

        session2 = create_session(cache_dir)
        api_suite2 = ProTestSuite("API")
        session2.add_suite(api_suite2)
        executed: list[str] = []

        @api_suite2.test(tags=["slow"])
        def test_api_login_slow_fail_v2() -> None:
            executed.append("api_login_slow_fail")

        test_api_login_slow_fail_v2.__name__ = "test_api_login_slow_fail"

        @api_suite2.test(tags=["slow"])
        def test_api_login_slow_pass_v2() -> None:
            executed.append("api_login_slow_pass")

        test_api_login_slow_pass_v2.__name__ = "test_api_login_slow_pass"

        @api_suite2.test(tags=["fast"])
        def test_api_login_fast_fail_v2() -> None:
            executed.append("api_login_fast_fail")

        test_api_login_fast_fail_v2.__name__ = "test_api_login_fast_fail"

        result = run_session(
            session2,
            suite_filter="API",
            keyword_patterns=["login"],
            include_tags={"slow"},
            last_failed=True,
        )

        assert result.success is True
        assert executed == ["api_login_slow_fail"]
