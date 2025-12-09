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


class SessionFactory:
    """Factory that creates sessions with consistent test functions for cache persistence testing."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._test_behaviors: dict[str, dict] = {}

    def create_session(self) -> ProTestSession:
        """Create a fresh session with the given cache directory."""
        session = ProTestSession(default_reporter=False, default_cache=True)
        session._cache_storage = CacheStorage(
            cache_dir=self._cache_dir, cache_file="cache.json"
        )
        return session

    def register_test(
        self,
        session: ProTestSession,
        name: str,
        tags: set[str] | None = None,
        should_fail: bool = False,
        executed_list: list[str] | None = None,
        suite: ProTestSuite | None = None,
    ) -> None:
        """Register a test with consistent naming across sessions."""
        tag_list = list(tags) if tags else []
        tracker = executed_list if executed_list is not None else []
        fail = should_fail

        def test_func() -> None:
            tracker.append(name)
            if fail:
                raise AssertionError(f"{name} fails")

        test_func.__name__ = name
        test_func.__module__ = "tests.integration.test_filter_combinations"

        target = suite if suite else session
        if tag_list:
            target.test(tags=tag_list)(test_func)
        else:
            target.test()(test_func)


@pytest.fixture
def session_factory(cache_dir: Path) -> SessionFactory:
    """Provide a session factory for cache persistence tests."""
    return SessionFactory(cache_dir)


class TestLastFailedWithTags:
    """Tests for --lf combined with tag filtering."""

    def test_lf_and_include_tag_intersection(
        self, session_factory: SessionFactory
    ) -> None:
        """Given failed tests with different tags, when --lf --tag X, then only failed tests with tag X run."""
        first_run_executed: list[str] = []
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1,
            "test_slow_fail",
            tags={"slow"},
            should_fail=True,
            executed_list=first_run_executed,
        )
        session_factory.register_test(
            session1,
            "test_fast_fail",
            tags={"fast"},
            should_fail=True,
            executed_list=first_run_executed,
        )
        session_factory.register_test(
            session1,
            "test_slow_pass",
            tags={"slow"},
            should_fail=False,
            executed_list=first_run_executed,
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_fail",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail",
            tags={"fast"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_slow_pass",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        result = run_session(session2, last_failed=True, include_tags={"slow"})

        assert result.success is True
        assert second_run_executed == ["test_slow_fail"]

    def test_lf_and_exclude_tag_intersection(
        self, session_factory: SessionFactory
    ) -> None:
        """Given failed tests with different tags, when --lf --exclude-tag X, then failed tests without tag X run."""
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_slow_fail", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_fast_fail", tags={"fast"}, should_fail=True
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_fail",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail",
            tags={"fast"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        result = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert result.success is True
        assert second_run_executed == ["test_fast_fail"]

    def test_lf_exclude_tag_results_in_zero_tests(
        self, session_factory: SessionFactory
    ) -> None:
        """Given all failed tests have excluded tag, when --lf --exclude-tag X, then 0 tests run."""
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_slow_1", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_slow_2", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_fast_pass", tags={"fast"}, should_fail=False
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_1",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_slow_2",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_pass",
            tags={"fast"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        result = run_session(session2, last_failed=True, exclude_tags={"slow"})

        assert result.success is True
        assert second_run_executed == []

    def test_lf_with_tag_no_matching_failures(
        self, session_factory: SessionFactory
    ) -> None:
        """Given no failed test has tag X, when --lf --tag X, then 0 tests run (no fallback)."""
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_slow_pass", tags={"slow"}, should_fail=False
        )
        session_factory.register_test(
            session1, "test_fast_fail", tags={"fast"}, should_fail=True
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_pass",
            tags={"slow"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail",
            tags={"fast"},
            should_fail=False,
            executed_list=second_run_executed,
        )
        result = run_session(session2, last_failed=True, include_tags={"slow"})

        assert result.success is True
        assert second_run_executed == []


class TestLastFailedWithExitFirst:
    """Tests for --lf combined with -x (exitfirst)."""

    def test_lf_exitfirst_stops_on_failure(
        self, session_factory: SessionFactory
    ) -> None:
        """Given multiple failed tests, when --lf -x, then stop after first failure."""
        session1 = session_factory.create_session()
        session_factory.register_test(session1, "test_fail_1", should_fail=True)
        session_factory.register_test(session1, "test_fail_2", should_fail=True)
        session_factory.register_test(session1, "test_pass", should_fail=False)
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2, "test_fail_1", should_fail=True, executed_list=second_run_executed
        )
        session_factory.register_test(
            session2, "test_fail_2", should_fail=True, executed_list=second_run_executed
        )
        session_factory.register_test(
            session2, "test_pass", should_fail=False, executed_list=second_run_executed
        )
        result = run_session(session2, last_failed=True, exitfirst=True)

        assert result.success is False
        expected_executed_count = 1
        assert len(second_run_executed) == expected_executed_count
        assert second_run_executed[0] in ("test_fail_1", "test_fail_2")

    def test_exitfirst_then_lf_runs_only_failed(
        self, session_factory: SessionFactory
    ) -> None:
        """Given -x stopped on failure, when --lf on second run, then only failed test runs."""
        first_run_executed: list[str] = []
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_a", should_fail=False, executed_list=first_run_executed
        )
        session_factory.register_test(
            session1, "test_b", should_fail=True, executed_list=first_run_executed
        )
        session_factory.register_test(
            session1, "test_c", should_fail=False, executed_list=first_run_executed
        )
        result_first = run_session(session1, exitfirst=True)
        assert result_first.success is False

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2, "test_a", should_fail=False, executed_list=second_run_executed
        )
        session_factory.register_test(
            session2, "test_b", should_fail=False, executed_list=second_run_executed
        )
        session_factory.register_test(
            session2, "test_c", should_fail=False, executed_list=second_run_executed
        )
        result_second = run_session(session2, last_failed=True)

        assert result_second.success is True
        assert second_run_executed == ["test_b"]

    def test_exitfirst_partial_cache_then_lf(
        self, session_factory: SessionFactory
    ) -> None:
        """Given -x stopped and failure is fixed, when --lf, then only previously failed test runs."""
        session1 = session_factory.create_session()
        session_factory.register_test(session1, "test_only_one", should_fail=True)
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_only_one",
            should_fail=False,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2, "test_new", should_fail=False, executed_list=second_run_executed
        )
        result = run_session(session2, last_failed=True)

        assert result.success is True
        assert "test_only_one" in second_run_executed
        expected_test_count = 1
        assert len(second_run_executed) == expected_test_count


class TestTagsWithExitFirst:
    """Tests for tag filtering combined with -x (exitfirst)."""

    def test_tag_filter_with_exitfirst(self) -> None:
        """Given tests with different tags, when --tag X -x, then stop after first tagged failure."""
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
        """Given tests with different tags, when --exclude-tag X -x, then stop after first non-excluded failure."""
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

    def test_lf_tag_exitfirst_together(self, session_factory: SessionFactory) -> None:
        """Given failed tests with different tags, when --lf --tag X -x, then stop on first tagged failure."""
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_slow_fail_1", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_slow_fail_2", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_fast_fail", tags={"fast"}, should_fail=True
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_fail_1",
            tags={"slow"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_slow_fail_2",
            tags={"slow"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail",
            tags={"fast"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        result = run_session(
            session2, last_failed=True, include_tags={"slow"}, exitfirst=True
        )

        assert result.success is False
        assert "test_fast_fail" not in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed

    def test_lf_exclude_tag_exitfirst_together(
        self, session_factory: SessionFactory
    ) -> None:
        """Given failed tests with different tags, when --lf --exclude-tag X -x, then stop on first non-excluded failure."""
        session1 = session_factory.create_session()
        session_factory.register_test(
            session1, "test_slow_fail", tags={"slow"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_fast_fail_1", tags={"fast"}, should_fail=True
        )
        session_factory.register_test(
            session1, "test_fast_fail_2", tags={"fast"}, should_fail=True
        )
        run_session(session1)

        second_run_executed: list[str] = []
        session2 = session_factory.create_session()
        session_factory.register_test(
            session2,
            "test_slow_fail",
            tags={"slow"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail_1",
            tags={"fast"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        session_factory.register_test(
            session2,
            "test_fast_fail_2",
            tags={"fast"},
            should_fail=True,
            executed_list=second_run_executed,
        )
        result = run_session(
            session2, last_failed=True, exclude_tags={"slow"}, exitfirst=True
        )

        assert result.success is False
        assert "test_slow_fail" not in second_run_executed
        expected_max_executed = 1
        assert len(second_run_executed) == expected_max_executed


class TestSuiteFilter:
    """Tests for suite filtering (::SuiteName syntax)."""

    def test_suite_filter_basic(self) -> None:
        """Given tests in different suites, when suite filter applied, then only suite tests run."""
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
        """Given nested suites, when parent suite filter applied, then child suite tests also run."""
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
        """Given nested suites, when child suite filter applied, then parent suite tests excluded."""
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
        """Given nonexistent suite filter, when session runs, then 0 tests run."""
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

    @pytest.mark.parametrize(
        "keyword_patterns,expected_executed",
        [
            pytest.param(["login"], ["login"], id="exact_match"),
            pytest.param(["nonexistent"], [], id="no_match"),
        ],
    )
    def test_keyword_filter_single_pattern(
        self, keyword_patterns: list[str], expected_executed: list[str]
    ) -> None:
        """Given tests with different names, when keyword filter applied, then matching tests run."""
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

        result = run_session(session, keyword_patterns=keyword_patterns)

        assert result.success is True
        assert executed == expected_executed

    def test_keyword_filter_substring(self) -> None:
        """Given tests with similar names, when keyword filter applied, then all matching substrings run."""
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
        """Given multiple keyword patterns, when applied, then OR logic is used."""
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


class TestSuiteFilterWithTags:
    """Tests for suite filter combined with tag filtering."""

    def test_suite_and_include_tag(self) -> None:
        """Given suite tests with different tags, when suite + tag filter applied, then intersection runs."""
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
        """Given suite tests with different tags, when suite + exclude tag filter, then intersection runs."""
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
        """Given tests with different names and tags, when keyword + tag filter, then intersection runs."""
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
        """Given suite tests with different names, when suite + keyword filter, then intersection runs."""
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
        """Given tests in suite with different names and tags, when all filters applied, then intersection runs."""
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

    def test_suite_keyword_tag_lf_combined(
        self, session_factory: SessionFactory
    ) -> None:
        """Given all filters + --lf, when applied, then full intersection runs."""
        session1 = session_factory.create_session()
        api_suite1 = ProTestSuite("API")
        session1.add_suite(api_suite1)
        session_factory.register_test(
            session1,
            "test_api_login_slow_fail",
            tags={"slow"},
            should_fail=True,
            suite=api_suite1,
        )
        session_factory.register_test(
            session1,
            "test_api_login_slow_pass",
            tags={"slow"},
            should_fail=False,
            suite=api_suite1,
        )
        session_factory.register_test(
            session1,
            "test_api_login_fast_fail",
            tags={"fast"},
            should_fail=True,
            suite=api_suite1,
        )
        run_session(session1)

        executed: list[str] = []
        session2 = session_factory.create_session()
        api_suite2 = ProTestSuite("API")
        session2.add_suite(api_suite2)
        session_factory.register_test(
            session2,
            "test_api_login_slow_fail",
            tags={"slow"},
            should_fail=False,
            executed_list=executed,
            suite=api_suite2,
        )
        session_factory.register_test(
            session2,
            "test_api_login_slow_pass",
            tags={"slow"},
            should_fail=False,
            executed_list=executed,
            suite=api_suite2,
        )
        session_factory.register_test(
            session2,
            "test_api_login_fast_fail",
            tags={"fast"},
            should_fail=False,
            executed_list=executed,
            suite=api_suite2,
        )
        result = run_session(
            session2,
            suite_filter="API",
            keyword_patterns=["login"],
            include_tags={"slow"},
            last_failed=True,
        )

        assert result.success is True
        assert executed == ["test_api_login_slow_fail"]
