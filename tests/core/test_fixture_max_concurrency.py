"""Tests for fixture max_concurrency (issue #61)."""

import asyncio
from dataclasses import dataclass, field
from typing import Annotated

import pytest

from protest import ProTestSession, ProTestSuite
from protest.core.runner import TestRunner
from protest.di.container import FixtureContainer
from protest.di.decorators import factory, fixture, get_fixture_marker
from protest.di.markers import Use
from protest.exceptions import InvalidMaxConcurrencyError


@dataclass
class FixtureConcurrencyTracker:
    """Tracks concurrent fixture access for validating max_concurrency."""

    current: int = 0
    max_seen: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def enter(self) -> None:
        """Track entering fixture access."""
        async with self.lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)

    async def exit(self) -> None:
        """Track exiting fixture access."""
        async with self.lock:
            self.current -= 1


class TestFixtureMaxConcurrencyValidation:
    """Tests for max_concurrency validation in @fixture/@factory decorators."""

    def test_fixture_rejects_zero_max_concurrency(self) -> None:
        """@fixture(max_concurrency=0) raises InvalidMaxConcurrencyError."""
        with pytest.raises(InvalidMaxConcurrencyError):

            @fixture(max_concurrency=0)
            def invalid() -> str:
                return "value"

    def test_fixture_rejects_negative_max_concurrency(self) -> None:
        """@fixture(max_concurrency=-1) raises InvalidMaxConcurrencyError."""
        with pytest.raises(InvalidMaxConcurrencyError):

            @fixture(max_concurrency=-1)
            def invalid() -> str:
                return "value"

    def test_factory_rejects_zero_max_concurrency(self) -> None:
        """@factory(max_concurrency=0) raises InvalidMaxConcurrencyError."""
        with pytest.raises(InvalidMaxConcurrencyError):

            @factory(max_concurrency=0)
            def invalid(name: str) -> str:
                return name

    def test_factory_rejects_negative_max_concurrency(self) -> None:
        """@factory(max_concurrency=-1) raises InvalidMaxConcurrencyError."""
        with pytest.raises(InvalidMaxConcurrencyError):

            @factory(max_concurrency=-1)
            def invalid(name: str) -> str:
                return name


class TestFixtureMarkerMaxConcurrency:
    """Tests for max_concurrency in @fixture() decorator."""

    def test_fixture_marker_stores_max_concurrency(self) -> None:
        """@fixture(max_concurrency=N) stores the value in marker."""

        @fixture(max_concurrency=3)
        def limited() -> str:
            return "value"

        marker = get_fixture_marker(limited)
        assert marker is not None
        assert marker.max_concurrency == 3

    def test_fixture_without_max_concurrency_is_none(self) -> None:
        """@fixture() without max_concurrency defaults to None."""

        @fixture()
        def unlimited() -> str:
            return "value"

        marker = get_fixture_marker(unlimited)
        assert marker is not None
        assert marker.max_concurrency is None

    def test_factory_marker_stores_max_concurrency(self) -> None:
        """@factory(max_concurrency=N) stores the value in marker."""

        @factory(max_concurrency=5)
        def limited_factory(name: str) -> str:
            return f"user_{name}"

        marker = get_fixture_marker(limited_factory)
        assert marker is not None
        assert marker.max_concurrency == 5

    def test_factory_without_max_concurrency_is_none(self) -> None:
        """@factory() without max_concurrency defaults to None."""

        @factory()
        def unlimited_factory(name: str) -> str:
            return f"user_{name}"

        marker = get_fixture_marker(unlimited_factory)
        assert marker is not None
        assert marker.max_concurrency is None


class TestContainerMaxConcurrency:
    """Tests for max_concurrency in FixtureContainer."""

    def test_register_stores_max_concurrency(self) -> None:
        """Container.register() stores max_concurrency."""
        container = FixtureContainer()

        def my_fixture() -> str:
            return "value"

        container.register(my_fixture, max_concurrency=3)
        assert container.get_max_concurrency(my_fixture) == 3

    def test_get_max_concurrency_returns_none_for_unlimited(self) -> None:
        """get_max_concurrency returns None when not set."""
        container = FixtureContainer()

        def my_fixture() -> str:
            return "value"

        container.register(my_fixture)
        assert container.get_max_concurrency(my_fixture) is None

    def test_get_max_concurrency_returns_none_for_unregistered(self) -> None:
        """get_max_concurrency returns None for unregistered fixtures."""
        container = FixtureContainer()

        def unknown_fixture() -> str:
            return "value"

        assert container.get_max_concurrency(unknown_fixture) is None


class TestFixtureMaxConcurrencyIntegration:
    """Integration tests for fixture max_concurrency limiting concurrent tests."""

    def test_fixture_max_concurrency_limits_concurrent_tests(self) -> None:
        """Fixture with max_concurrency=2 allows max 2 concurrent tests."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def limited_api() -> str:
            await tracker.enter()
            yield "api_client"
            await tracker.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("api_tests")
        session.add_suite(suite)
        suite.bind(limited_api)

        test_count = 5

        for _ in range(test_count):

            @suite.test()
            async def test_api(
                api: Annotated[str, Use(limited_api)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        expected_max_concurrency = 2
        assert tracker.max_seen <= expected_max_concurrency

    def test_fixture_max_concurrency_one_is_serial(self) -> None:
        """Fixture with max_concurrency=1 serializes test access."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=1)
        async def serial_resource() -> str:
            await tracker.enter()
            yield "resource"
            await tracker.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("serial_tests")
        session.add_suite(suite)
        suite.bind(serial_resource)

        test_count = 4

        for _ in range(test_count):

            @suite.test()
            async def test_serial(
                res: Annotated[str, Use(serial_resource)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert tracker.max_seen == 1

    def test_unlimited_fixture_allows_full_concurrency(self) -> None:
        """Fixture without max_concurrency allows full session concurrency."""
        tracker = FixtureConcurrencyTracker()

        @fixture()
        async def unlimited_resource() -> str:
            await tracker.enter()
            yield "resource"
            await tracker.exit()

        session = ProTestSession(concurrency=4)
        suite = ProTestSuite("unlimited_tests")
        session.add_suite(suite)
        suite.bind(unlimited_resource)

        test_count = 8

        for _ in range(test_count):

            @suite.test()
            async def test_unlimited(
                res: Annotated[str, Use(unlimited_resource)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # Without max_concurrency, there's no artificial limit
        # (concurrency depends on scheduler timing, just verify it runs)

    def test_session_concurrency_caps_fixture_max_concurrency(self) -> None:
        """Session concurrency caps fixture max_concurrency."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=10)
        async def wide_fixture() -> str:
            await tracker.enter()
            yield "resource"
            await tracker.exit()

        session = ProTestSession(concurrency=2)
        suite = ProTestSuite("capped_tests")
        session.add_suite(suite)
        suite.bind(wide_fixture)

        test_count = 5

        for _ in range(test_count):

            @suite.test()
            async def test_capped(
                res: Annotated[str, Use(wide_fixture)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # min(session=2, fixture=10) = 2
        expected_max_concurrency = 2
        assert tracker.max_seen <= expected_max_concurrency

    def test_multiple_fixtures_with_max_concurrency(self) -> None:
        """Test using multiple fixtures with different max_concurrency."""
        tracker_a = FixtureConcurrencyTracker()
        tracker_b = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def fixture_a() -> str:
            await tracker_a.enter()
            yield "a"
            await tracker_a.exit()

        @fixture(max_concurrency=3)
        async def fixture_b() -> str:
            await tracker_b.enter()
            yield "b"
            await tracker_b.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("multi_fixture_tests")
        session.add_suite(suite)
        suite.bind(fixture_a)
        suite.bind(fixture_b)

        test_count = 6

        for _ in range(test_count):

            @suite.test()
            async def test_both(
                a: Annotated[str, Use(fixture_a)],
                b: Annotated[str, Use(fixture_b)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # Tests need both fixtures, so limited by the more restrictive one
        expected_max_a = 2
        expected_max_b = 3
        assert tracker_a.max_seen <= expected_max_a
        assert tracker_b.max_seen <= expected_max_b

    def test_fixture_error_releases_semaphore(self) -> None:
        """Fixture errors properly release semaphore slots."""

        @fixture(max_concurrency=1)
        async def failing_fixture() -> str:
            raise ValueError("Fixture failed!")
            yield "never_returned"  # type: ignore[misc]

        session = ProTestSession(concurrency=2)
        suite = ProTestSuite("error_tests")
        session.add_suite(suite)
        suite.bind(failing_fixture)

        test_count = 3

        for _ in range(test_count):

            @suite.test()
            async def test_error(
                res: Annotated[str, Use(failing_fixture)],
            ) -> None:
                pass  # Never reached

        runner = TestRunner(session)
        result = runner.run()

        # All tests should error (fixture failed), none should hang
        # Result is not success because of errors
        assert not result.success

    def test_interaction_with_suite_max_concurrency(self) -> None:
        """Both suite and fixture max_concurrency are applied."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=5)
        async def wide_fixture() -> str:
            await tracker.enter()
            yield "resource"
            await tracker.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("narrow_suite", max_concurrency=2)
        session.add_suite(suite)
        suite.bind(wide_fixture)

        test_count = 5

        for _ in range(test_count):

            @suite.test()
            async def test_narrow(
                res: Annotated[str, Use(wide_fixture)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # Suite limits to 2, even though fixture allows 5
        expected_max_concurrency = 2
        assert tracker.max_seen <= expected_max_concurrency

    def test_session_level_fixture_max_concurrency(self) -> None:
        """Session-level fixtures also support max_concurrency."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def session_limited() -> str:
            await tracker.enter()
            yield "session_resource"
            await tracker.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("session_tests")
        session.add_suite(suite)
        session.bind(session_limited)  # SESSION scope

        test_count = 5

        for _ in range(test_count):

            @suite.test()
            async def test_session(
                res: Annotated[str, Use(session_limited)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # max_concurrency limits concurrent access to session fixture
        expected_max_concurrency = 2
        assert tracker.max_seen <= expected_max_concurrency

    def test_transitive_max_concurrency_via_wrapper(self) -> None:
        """Transitive: test → wrapper → rate_limited(max_concurrency=1) is serialized."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=1)
        async def rate_limited() -> str:
            await tracker.enter()
            yield "limited"
            await tracker.exit()

        @fixture()
        async def wrapper(res: Annotated[str, Use(rate_limited)]) -> str:
            yield f"wrapped_{res}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("transitive_tests")
        session.add_suite(suite)
        suite.bind(rate_limited)
        suite.bind(wrapper)

        test_count = 4

        for _ in range(test_count):

            @suite.test()
            async def test_via_wrapper(
                w: Annotated[str, Use(wrapper)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # Even though tests use wrapper (not rate_limited directly),
        # they should be serialized because wrapper depends on rate_limited
        assert tracker.max_seen == 1

    def test_transitive_diamond_pattern(self) -> None:
        """Diamond: test → [svc_a, svc_b] → shared(max_concurrency=2)."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def shared_api() -> str:
            await tracker.enter()
            yield "shared"
            await tracker.exit()

        @fixture()
        async def service_a(api: Annotated[str, Use(shared_api)]) -> str:
            yield f"svc_a_{api}"

        @fixture()
        async def service_b(api: Annotated[str, Use(shared_api)]) -> str:
            yield f"svc_b_{api}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("diamond_tests")
        session.add_suite(suite)
        suite.bind(shared_api)
        suite.bind(service_a)
        suite.bind(service_b)

        test_count = 6

        for _ in range(test_count):

            @suite.test()
            async def test_diamond(
                a: Annotated[str, Use(service_a)],
                b: Annotated[str, Use(service_b)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # shared_api should be found via both paths but semaphore acquired once
        assert tracker.max_seen <= 2

    def test_transitive_multiple_rate_limited(self) -> None:
        """Multiple rate-limited fixtures in chain are all respected."""
        tracker_outer = FixtureConcurrencyTracker()
        tracker_inner = FixtureConcurrencyTracker()

        @fixture(max_concurrency=1)
        async def inner_limited() -> str:
            await tracker_inner.enter()
            yield "inner"
            await tracker_inner.exit()

        @fixture(max_concurrency=3)
        async def outer_limited(inner: Annotated[str, Use(inner_limited)]) -> str:
            await tracker_outer.enter()
            yield f"outer_{inner}"
            await tracker_outer.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("multi_limited")
        session.add_suite(suite)
        suite.bind(inner_limited)
        suite.bind(outer_limited)

        test_count = 5

        for _ in range(test_count):

            @suite.test()
            async def test_chain(
                outer: Annotated[str, Use(outer_limited)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # inner_limited has max_concurrency=1 (most restrictive)
        # outer_limited has max_concurrency=3
        # Both should be respected, but inner_limited limits everything to 1
        assert tracker_inner.max_seen == 1
        assert tracker_outer.max_seen == 1  # Limited by inner


class TestMaxConcurrencyUnboundFixtures:
    """Tests for max_concurrency on fixtures not explicitly bound (issue #73)."""

    def test_unbound_fixture_max_concurrency_is_respected(self) -> None:
        """max_concurrency works for fixtures used directly via Use() but not bound.

        This is the core issue #73: when a fixture with max_concurrency is used
        via Use() but NOT explicitly bound to session/suite, the max_concurrency
        was being ignored because get_max_concurrency() only looked in the registry.

        The fixture is registered lazily during resolution, but build_fixture_semaphores()
        calls get_max_concurrency() BEFORE resolution happens.
        """
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=1)
        async def unbound_rate_limited() -> str:
            """This fixture has max_concurrency but will NOT be bound."""
            await tracker.enter()
            yield "limited"
            await tracker.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("unbound_tests")
        session.add_suite(suite)
        # DO NOT bind unbound_rate_limited - tests use it directly via Use()

        test_count = 4

        for _ in range(test_count):

            @suite.test()
            async def test_direct(
                res: Annotated[str, Use(unbound_rate_limited)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # Even though unbound_rate_limited is NOT bound, its max_concurrency=1
        # should still serialize access
        assert tracker.max_seen == 1, (
            f"Expected max 1 concurrent access, but saw {tracker.max_seen}. "
            "This likely means max_concurrency is ignored for unbound fixtures."
        )

    def test_transitive_unbound_max_concurrency(self) -> None:
        """Transitive max_concurrency works through chain of unbound fixtures.

        fixtA (max_concurrency=1, unbound)
           ↑
        fixtB (no max_concurrency, unbound)
           ↑
        fixtC (max_concurrency=30, unbound)
           ↑
        test

        All fixtures are unbound (TEST scope). Expected: tests serialized
        because fixtA limits to 1.
        """
        tracker_a = FixtureConcurrencyTracker()

        @fixture(max_concurrency=1)
        async def fixt_a() -> str:
            """Unbound fixture with max_concurrency=1."""
            await tracker_a.enter()
            yield "a"
            await tracker_a.exit()

        @fixture()
        async def fixt_b(a: Annotated[str, Use(fixt_a)]) -> str:
            """Unbound fixture, depends on fixt_a."""
            yield f"b_{a}"

        @fixture(max_concurrency=30)
        async def fixt_c(b: Annotated[str, Use(fixt_b)]) -> str:
            """Unbound fixture with max_concurrency=30, depends on fixt_b."""
            yield f"c_{b}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("transitive_unbound")
        session.add_suite(suite)
        # NO fixtures are bound - all used directly via Use()

        test_count = 4

        for _ in range(test_count):

            @suite.test()
            async def test_transitive(
                c: Annotated[str, Use(fixt_c)],
                delay: float = 0.05,
            ) -> None:
                await asyncio.sleep(delay)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # fixt_a has max_concurrency=1, even though unbound
        # Tests should be serialized by fixt_a's semaphore
        assert tracker_a.max_seen == 1, (
            f"Expected max 1 concurrent access to fixt_a, but saw {tracker_a.max_seen}. "
            "Transitive max_concurrency not working for unbound fixtures."
        )


class TestMaxConcurrencyEffectiveMinimum:
    """Tests verifying that effective max_concurrency is the minimum across all transitive deps."""

    def test_linear_chain_takes_minimum(self) -> None:
        """Linear chain: A(max=2) → B(max=10) → test → effective is 2."""
        tracker_a = FixtureConcurrencyTracker()
        tracker_b = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def fixture_a() -> str:
            await tracker_a.enter()
            yield "a"
            await tracker_a.exit()

        @fixture(max_concurrency=10)
        async def fixture_b(a: Annotated[str, Use(fixture_a)]) -> str:
            await tracker_b.enter()
            yield f"b_{a}"
            await tracker_b.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("linear_chain")
        session.add_suite(suite)
        suite.bind(fixture_a)
        suite.bind(fixture_b)

        for _ in range(6):

            @suite.test()
            async def test_linear(
                b: Annotated[str, Use(fixture_b)],
            ) -> None:
                await asyncio.sleep(0.05)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # fixture_a limits to 2, even though fixture_b allows 10
        assert tracker_a.max_seen <= 2
        assert tracker_b.max_seen <= 2  # Limited by fixture_a

    def test_diamond_takes_minimum_of_both_branches(self) -> None:
        """Diamond: A(max=2) and B(max=5) → C → test → effective is 2."""
        tracker_a = FixtureConcurrencyTracker()
        tracker_b = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def branch_a() -> str:
            await tracker_a.enter()
            yield "a"
            await tracker_a.exit()

        @fixture(max_concurrency=5)
        async def branch_b() -> str:
            await tracker_b.enter()
            yield "b"
            await tracker_b.exit()

        @fixture()
        async def merger(
            a: Annotated[str, Use(branch_a)],
            b: Annotated[str, Use(branch_b)],
        ) -> str:
            yield f"{a}_{b}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("diamond")
        session.add_suite(suite)
        suite.bind(branch_a)
        suite.bind(branch_b)
        suite.bind(merger)

        for _ in range(8):

            @suite.test()
            async def test_diamond(
                m: Annotated[str, Use(merger)],
            ) -> None:
                await asyncio.sleep(0.05)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # branch_a limits to 2, branch_b to 5 → effective is min(2, 5) = 2
        assert tracker_a.max_seen <= 2
        assert tracker_b.max_seen <= 2  # Also limited by branch_a's semaphore

    def test_mixed_scopes_session_suite_test(self) -> None:
        """Mixed scopes: SESSION(max=2) → SUITE → TEST(unbound) → test."""
        tracker_session = FixtureConcurrencyTracker()

        @fixture(max_concurrency=2)
        async def session_limited() -> str:
            await tracker_session.enter()
            yield "session"
            await tracker_session.exit()

        @fixture()
        async def suite_wrapper(
            s: Annotated[str, Use(session_limited)],
        ) -> str:
            yield f"suite_{s}"

        @fixture()
        async def test_wrapper(
            sw: Annotated[str, Use(suite_wrapper)],
        ) -> str:
            yield f"test_{sw}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("mixed_scopes")
        session.add_suite(suite)
        session.bind(session_limited)  # SESSION scope
        suite.bind(suite_wrapper)  # SUITE scope
        # test_wrapper is unbound (TEST scope)

        for _ in range(6):

            @suite.test()
            async def test_mixed(
                tw: Annotated[str, Use(test_wrapper)],
            ) -> None:
                await asyncio.sleep(0.05)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # session_limited has max_concurrency=2, propagates through chain
        assert tracker_session.max_seen <= 2

    def test_multiple_rate_limited_in_chain(self) -> None:
        """Multiple rate-limited: A(max=3) → B(max=1) → C(max=5) → test → effective is 1."""
        tracker_a = FixtureConcurrencyTracker()
        tracker_b = FixtureConcurrencyTracker()
        tracker_c = FixtureConcurrencyTracker()

        @fixture(max_concurrency=3)
        async def level_a() -> str:
            await tracker_a.enter()
            yield "a"
            await tracker_a.exit()

        @fixture(max_concurrency=1)
        async def level_b(a: Annotated[str, Use(level_a)]) -> str:
            await tracker_b.enter()
            yield f"b_{a}"
            await tracker_b.exit()

        @fixture(max_concurrency=5)
        async def level_c(b: Annotated[str, Use(level_b)]) -> str:
            await tracker_c.enter()
            yield f"c_{b}"
            await tracker_c.exit()

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite("multi_limited")
        session.add_suite(suite)
        suite.bind(level_a)
        suite.bind(level_b)
        suite.bind(level_c)

        for _ in range(5):

            @suite.test()
            async def test_chain(
                c: Annotated[str, Use(level_c)],
            ) -> None:
                await asyncio.sleep(0.05)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        # level_b has the strictest limit (1)
        assert tracker_a.max_seen <= 1  # Limited by level_b downstream
        assert tracker_b.max_seen == 1
        assert tracker_c.max_seen <= 1  # Limited by level_b upstream

    @pytest.mark.parametrize(
        ("max_a", "max_b", "max_c", "expected_max"),
        [
            pytest.param(1, 10, 10, 1, id="bottleneck_at_root"),
            pytest.param(10, 1, 10, 1, id="bottleneck_in_middle"),
            pytest.param(10, 10, 1, 1, id="bottleneck_at_leaf"),
            pytest.param(2, 3, 5, 2, id="increasing_chain"),
            pytest.param(5, 3, 2, 2, id="decreasing_chain"),
            pytest.param(3, 3, 3, 3, id="uniform_chain"),
        ],
    )
    def test_parametrized_chain_minimum(
        self,
        max_a: int,
        max_b: int,
        max_c: int,
        expected_max: int,
    ) -> None:
        """Parametrized test: chain A → B → C with various max_concurrency values."""
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=max_a)
        async def fixt_a() -> str:
            await tracker.enter()
            yield "a"
            await tracker.exit()

        @fixture(max_concurrency=max_b)
        async def fixt_b(a: Annotated[str, Use(fixt_a)]) -> str:
            yield f"b_{a}"

        @fixture(max_concurrency=max_c)
        async def fixt_c(b: Annotated[str, Use(fixt_b)]) -> str:
            yield f"c_{b}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite(f"param_{max_a}_{max_b}_{max_c}")
        session.add_suite(suite)
        suite.bind(fixt_a)
        suite.bind(fixt_b)
        suite.bind(fixt_c)

        for _ in range(6):

            @suite.test()
            async def test_param(
                c: Annotated[str, Use(fixt_c)],
            ) -> None:
                await asyncio.sleep(0.03)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert tracker.max_seen <= expected_max, (
            f"Expected max {expected_max} concurrent, got {tracker.max_seen}"
        )

    @pytest.mark.parametrize(
        ("max_session", "max_suite", "max_test", "expected_max"),
        [
            pytest.param(1, 10, 10, 1, id="session_bottleneck"),
            pytest.param(10, 1, 10, 1, id="suite_bottleneck"),
            pytest.param(10, 10, 1, 1, id="test_bottleneck"),
            pytest.param(2, 5, 8, 2, id="session_is_min"),
            pytest.param(8, 2, 5, 2, id="suite_is_min"),
            pytest.param(5, 8, 2, 2, id="test_is_min"),
        ],
    )
    def test_parametrized_mixed_scopes(
        self,
        max_session: int,
        max_suite: int,
        max_test: int,
        expected_max: int,
    ) -> None:
        """Mixed scopes: SESSION(max_a) → SUITE(max_b) → TEST(max_c, unbound).

        The dependency chain crosses all three scopes, verifying that
        max_concurrency minimum is respected regardless of scope.
        """
        tracker = FixtureConcurrencyTracker()

        @fixture(max_concurrency=max_session)
        async def session_fixt() -> str:
            await tracker.enter()
            yield "session"
            await tracker.exit()

        @fixture(max_concurrency=max_suite)
        async def suite_fixt(s: Annotated[str, Use(session_fixt)]) -> str:
            yield f"suite_{s}"

        @fixture(max_concurrency=max_test)
        async def test_fixt(su: Annotated[str, Use(suite_fixt)]) -> str:
            yield f"test_{su}"

        session = ProTestSession(concurrency=10)
        suite = ProTestSuite(f"mixed_{max_session}_{max_suite}_{max_test}")
        session.add_suite(suite)
        session.bind(session_fixt)  # SESSION scope
        suite.bind(suite_fixt)  # SUITE scope
        # test_fixt is NOT bound → TEST scope (unbound)

        for _ in range(6):

            @suite.test()
            async def test_mixed_param(
                t: Annotated[str, Use(test_fixt)],
            ) -> None:
                await asyncio.sleep(0.03)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success
        assert tracker.max_seen <= expected_max, (
            f"Expected max {expected_max} concurrent, got {tracker.max_seen}"
        )
