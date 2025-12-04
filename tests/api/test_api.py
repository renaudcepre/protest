from __future__ import annotations

from protest import ProTestSession, ProTestSuite, collect_tests, list_tags, run_session


class TestRunSession:
    def test_run_session_all_passing(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_one() -> None:
            assert True

        @session.test()
        def test_two() -> None:
            assert 1 + 1 == 2

        success = run_session(session)
        assert success is True

    def test_run_session_with_failure(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_passing() -> None:
            assert True

        @session.test()
        def test_failing() -> None:
            raise AssertionError("intentional failure")

        success = run_session(session)
        assert success is False

    def test_run_session_with_concurrency(self) -> None:
        session = ProTestSession()

        @session.test()
        async def test_concurrent_0() -> None:
            assert True

        @session.test()
        async def test_concurrent_1() -> None:
            assert True

        @session.test()
        async def test_concurrent_2() -> None:
            assert True

        success = run_session(session, concurrency=2)
        assert success is True

    def test_run_session_exitfirst(self) -> None:
        session = ProTestSession()
        execution_order: list[str] = []

        @session.test()
        def test_first() -> None:
            execution_order.append("first")
            raise AssertionError("fail first")

        @session.test()
        def test_second() -> None:
            execution_order.append("second")

        success = run_session(session, exitfirst=True)
        assert success is False
        assert execution_order == ["first"]


class TestRunSessionTagFiltering:
    def test_include_tags(self) -> None:
        session = ProTestSession()

        @session.test(tags=["unit"])
        def test_unit() -> None:
            assert True

        @session.test(tags=["integration"])
        def test_integration() -> None:
            raise AssertionError("should not run")

        success = run_session(session, include_tags={"unit"})
        assert success is True

    def test_exclude_tags(self) -> None:
        session = ProTestSession()

        @session.test(tags=["unit"])
        def test_unit() -> None:
            assert True

        @session.test(tags=["slow"])
        def test_slow() -> None:
            raise AssertionError("should not run")

        success = run_session(session, exclude_tags={"slow"})
        assert success is True


class TestCollectTests:
    def test_collect_all_tests(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_one() -> None:
            pass

        @session.test()
        def test_two() -> None:
            pass

        items = collect_tests(session)
        expected_count = 2
        assert len(items) == expected_count

    def test_collect_with_suites(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("MySuite")
        session.add_suite(suite)

        @session.test()
        def test_session() -> None:
            pass

        @suite.test()
        def test_suite() -> None:
            pass

        items = collect_tests(session)
        expected_count = 2
        assert len(items) == expected_count
        node_ids = [item.node_id for item in items]
        assert any("test_session" in node_id for node_id in node_ids)
        assert any("MySuite::test_suite" in node_id for node_id in node_ids)

    def test_collect_with_tag_filter(self) -> None:
        session = ProTestSession()

        @session.test(tags=["unit"])
        def test_unit() -> None:
            pass

        @session.test(tags=["integration"])
        def test_integration() -> None:
            pass

        items = collect_tests(session, include_tags={"unit"})
        expected_count = 1
        assert len(items) == expected_count
        assert "test_unit" in items[0].node_id

    def test_collect_with_exclude_tags(self) -> None:
        session = ProTestSession()

        @session.test(tags=["unit"])
        def test_unit() -> None:
            pass

        @session.test(tags=["slow"])
        def test_slow() -> None:
            pass

        items = collect_tests(session, exclude_tags={"slow"})
        expected_count = 1
        assert len(items) == expected_count
        assert "test_unit" in items[0].node_id


class TestListTags:
    def test_list_tags_from_tests(self) -> None:
        session = ProTestSession()

        @session.test(tags=["unit", "fast"])
        def test_one() -> None:
            pass

        @session.test(tags=["integration"])
        def test_two() -> None:
            pass

        tags = list_tags(session)
        assert tags == {"unit", "fast", "integration"}

    def test_list_tags_from_fixtures(self) -> None:
        session = ProTestSession()

        @session.fixture(tags=["database"])
        def db_fixture() -> str:
            return "db"

        @session.test()
        def test_one() -> None:
            pass

        tags = list_tags(session)
        assert tags == {"database"}

    def test_list_tags_from_suites(self) -> None:
        session = ProTestSession()
        suite = ProTestSuite("API", tags=["api", "integration"])
        session.add_suite(suite)

        @suite.test(tags=["slow"])
        def test_api() -> None:
            pass

        tags = list_tags(session)
        assert tags == {"api", "integration", "slow"}

    def test_list_tags_nested_suites(self) -> None:
        session = ProTestSession()
        parent = ProTestSuite("Parent", tags=["parent"])
        child = ProTestSuite("Child", tags=["child"])
        parent.add_suite(child)
        session.add_suite(parent)

        @child.fixture(tags=["fixture_tag"])
        def child_fixture() -> str:
            return "fixture"

        @child.test(tags=["test_tag"])
        def test_child() -> None:
            pass

        tags = list_tags(session)
        assert tags == {"parent", "child", "fixture_tag", "test_tag"}

    def test_list_tags_empty_session(self) -> None:
        session = ProTestSession()

        @session.test()
        def test_no_tags() -> None:
            pass

        tags = list_tags(session)
        assert tags == set()
