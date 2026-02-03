import asyncio
from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import AsyncExitStack
from typing import Annotated, Any

import pytest

from protest.core.fixture import is_generator_like
from protest.di.container import FixtureContainer
from protest.di.decorators import FixtureWrapper, fixture
from protest.di.markers import Use
from protest.entities import FixtureScope, SuitePath
from protest.exceptions import (
    AlreadyRegisteredError,
    CircularDependencyError,
    PlainFunctionError,
    ScopeMismatchError,
)
from tests.di.dependencies import (
    function_dependency,
    generator_function_fixture,
    generator_session_fixture,
    generator_without_try_finally,
    session_dependency,
)
from tests.di.utils import call_counts, reset_call_counts, teardown_counts


@pytest.fixture
def resolver() -> FixtureContainer:
    reset_call_counts()
    return FixtureContainer()


# --- Scoping and Caching Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target_scope",
    [
        pytest.param(FixtureScope.SESSION, id="session_target"),
        pytest.param(FixtureScope.TEST, id="test_target"),
    ],
)
async def test_session_dependency_is_cached(
    resolver: FixtureContainer, target_scope: FixtureScope
) -> None:
    """Given a session dependency, when resolved twice from any scope, then only called once."""
    resolver.register(session_dependency, scope=FixtureScope.SESSION)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, scope=target_scope)

    await resolver.resolve(target)
    await resolver.resolve(target)

    expected_call_count = 1
    assert call_counts["session"] == expected_call_count


@pytest.mark.asyncio
async def test_test_scope_is_not_cached_across_runs(resolver: FixtureContainer) -> None:
    """Given a test-scoped fixture, when resolved twice, then called each time."""
    resolver.register(function_dependency, scope=FixtureScope.TEST)

    def target(function_data: Annotated[str, Use(function_dependency)]) -> str:
        return function_data

    resolver.register(target, scope=FixtureScope.TEST)

    await resolver.resolve(target)
    expected_call_count_first = 1
    assert call_counts["function"] == expected_call_count_first

    await resolver.resolve(target)
    expected_call_count_second = 2
    assert call_counts["function"] == expected_call_count_second


# --- Invalid Scope Dependency Test ---


def test_session_scope_cannot_depend_on_test_scope(resolver: FixtureContainer) -> None:
    resolver.register(function_dependency, scope=FixtureScope.TEST)

    def invalid_session_fixture(
        function_data: Annotated[str, Use(function_dependency)],
    ) -> str:
        return f"session_using_{function_data}"

    with pytest.raises(ScopeMismatchError):
        resolver.register(invalid_session_fixture, scope=FixtureScope.SESSION)


# --- Already Registered Error Test ---


def test_cannot_register_same_function_twice(resolver: FixtureContainer) -> None:
    def my_fixture() -> str:
        return "test"

    resolver.register(my_fixture, scope=FixtureScope.TEST)

    with pytest.raises(
        AlreadyRegisteredError, match=r"Function 'my_fixture' is already registered\."
    ):
        resolver.register(my_fixture, scope=FixtureScope.SESSION)


# --- Auto-registration and Scope Mismatch Tests ---


def test_undecorated_dependency_raises_plain_function_error(
    resolver: FixtureContainer,
) -> None:
    """Plain functions without @fixture()/@factory() raise PlainFunctionError."""

    def unregistered_dependency() -> str:
        return "unregistered_data"

    @fixture()
    def fixture_with_unregistered_dep(
        dep: Annotated[str, Use(unregistered_dependency)],
    ) -> str:
        return f"fixture({dep})"

    with pytest.raises(PlainFunctionError) as exc_info:
        resolver.register(
            fixture_with_unregistered_dep.func, scope=FixtureScope.SESSION
        )

    assert "unregistered_dependency" in str(exc_info.value)


def test_extract_dependency_returns_none_for_regular_annotation() -> None:
    result = FixtureContainer._extract_dependency_from_annotation(str)

    assert result is None


# --- Generator Fixture Tests ---


@pytest.mark.asyncio
async def test_generator_fixture_yields_value(resolver: FixtureContainer) -> None:
    resolver.register(generator_session_fixture, scope=FixtureScope.SESSION)

    async with resolver:
        result = await resolver.resolve(generator_session_fixture)
        assert result == "generator_session_data"
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exit(resolver: FixtureContainer) -> None:
    resolver.register(generator_session_fixture, scope=FixtureScope.SESSION)

    async with resolver:
        await resolver.resolve(generator_session_fixture)
        assert teardown_counts["generator_session"] == 0

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_is_cached(resolver: FixtureContainer) -> None:
    resolver.register(generator_session_fixture, scope=FixtureScope.SESSION)

    async with resolver:
        result_first = await resolver.resolve(generator_session_fixture)
        result_second = await resolver.resolve(generator_session_fixture)
        assert result_first == result_second
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_with_dependency(resolver: FixtureContainer) -> None:
    resolver.register(session_dependency, scope=FixtureScope.SESSION)

    def generator_with_dep(
        data: Annotated[str, Use(session_dependency)],
    ) -> Generator[str, None, None]:
        call_counts["generator_with_dep"] += 1
        yield f"generated_{data}"
        teardown_counts["generator_with_dep"] += 1

    resolver.register(generator_with_dep, scope=FixtureScope.SESSION)

    async with resolver:
        result = await resolver.resolve(generator_with_dep)
        assert result == "generated_session_data"
        assert call_counts["session"] == 1
        assert call_counts["generator_with_dep"] == 1

    assert teardown_counts["generator_with_dep"] == 1


@pytest.mark.asyncio
async def test_multiple_generator_fixtures_teardown_in_reverse_order(
    resolver: FixtureContainer,
) -> None:
    """Generators with dependencies should teardown in LIFO order."""
    teardown_order: list[str] = []

    # Given: two generator fixtures with dependency chain
    def first_generator() -> Generator[str, None, None]:
        call_counts["first"] += 1
        yield "first_value"
        teardown_order.append("first")

    def second_generator(
        first: Annotated[str, Use(first_generator)],
    ) -> Generator[str, None, None]:
        call_counts["second"] += 1
        yield f"second_with_{first}"
        teardown_order.append("second")

    resolver.register(first_generator, scope=FixtureScope.SESSION)
    resolver.register(second_generator, scope=FixtureScope.SESSION)

    # When: resolving and exiting context
    async with resolver:
        result = await resolver.resolve(second_generator)
        assert result == "second_with_first_value"

    # Then: teardown in reverse order (LIFO)
    assert teardown_order == ["second", "first"]


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exception(
    resolver: FixtureContainer,
) -> None:
    resolver.register(generator_session_fixture, scope=FixtureScope.SESSION)

    with pytest.raises(ValueError, match="test exception"):
        async with resolver:
            await resolver.resolve(generator_session_fixture)
            raise ValueError("test exception")

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_teardown_without_try_finally_on_exception(
    resolver: FixtureContainer,
) -> None:
    """Proves that AsyncExitStack pattern guarantees teardown even without try/finally.

    When an exception is raised OUTSIDE the generator (in test code), it's caught
    at the test level, not inside the generator. Later, when the exit stack closes,
    it sends GeneratorExit (not the original exception) to the generator, which
    allows the code after yield to execute normally.

    This is different from raising an exception INSIDE an `async with` block,
    where the exception would be injected via athrow() and skip post-yield code.
    """
    resolver.register(generator_without_try_finally, scope=FixtureScope.SESSION)

    async with resolver:
        await resolver.resolve(generator_without_try_finally)
        try:
            raise ValueError("test exception caught outside generator")
        except ValueError:
            pass

    expected_teardown_count = 1
    assert teardown_counts["no_try_finally"] == expected_teardown_count


@pytest.mark.asyncio
async def test_mixed_regular_and_generator_fixtures(resolver: FixtureContainer) -> None:
    resolver.register(session_dependency, scope=FixtureScope.SESSION)
    resolver.register(generator_function_fixture, scope=FixtureScope.TEST)

    def mixed_target(
        regular: Annotated[str, Use(session_dependency)],
        generated: Annotated[str, Use(generator_function_fixture)],
    ) -> str:
        return f"{regular}_{generated}"

    resolver.register(mixed_target, scope=FixtureScope.TEST)

    async with resolver:
        result = await resolver.resolve(mixed_target)
        assert result == "session_data_generator_function_data"

    assert teardown_counts["generator_function"] == 1


class TestIsGeneratorLike:
    @pytest.mark.parametrize(
        "func_factory,expected",
        [
            pytest.param(
                lambda: (lambda: (yield "value")),
                True,
                id="sync_generator_with_yield",
            ),
            pytest.param(
                lambda: (lambda: "value"),
                False,
                id="regular_function",
            ),
        ],
    )
    def test_is_generator_like_by_code_inspection(
        self, func_factory: Callable[[], Callable[..., Any]], expected: bool
    ) -> None:
        """Given a function, when checked for generator-like, then result depends on yield presence."""
        func = func_factory()
        assert is_generator_like(func) is expected

    def test_sync_generator_with_annotation(self) -> None:
        """Given a function with Generator annotation and yield, then is_generator_like returns True."""

        def sync_gen() -> Generator[str, None, None]:
            yield "value"

        assert is_generator_like(sync_gen) is True

    def test_unannotated_generator(self) -> None:
        """Given an unannotated function with yield, then is_generator_like returns True."""

        def unannotated_gen():  # type: ignore[no-untyped-def]
            yield "value"

        assert is_generator_like(unannotated_gen) is True

    def test_fake_generator_annotation_without_yield(self) -> None:
        """Given a function with Generator annotation but no yield, then is_generator_like returns False."""

        def fake_gen() -> Generator[str, None, None]:
            return "value"  # type: ignore[return-value]

        assert is_generator_like(fake_gen) is False


# --- Auto-registration Tests ---


@pytest.mark.asyncio
async def test_decorated_function_auto_registered_and_resolved(
    resolver: FixtureContainer,
) -> None:
    """@fixture() decorated functions are auto-registered with FUNCTION scope."""

    @fixture()
    def my_fixture() -> str:
        return "auto_registered_data"

    async with resolver:
        result = await resolver.resolve(my_fixture)
        assert result == "auto_registered_data"


# --- Edge Case Tests ---


@pytest.mark.asyncio
async def test_fixture_error_during_setup_propagates(
    resolver: FixtureContainer,
) -> None:
    """Test that errors during fixture setup are propagated correctly."""

    @fixture()
    def failing_fixture() -> str:
        raise RuntimeError("Setup failed intentionally")

    resolver.register(failing_fixture.func, scope=FixtureScope.SESSION)

    with pytest.raises(RuntimeError, match="Setup failed intentionally"):
        await resolver.resolve(failing_fixture)


@pytest.mark.asyncio
async def test_concurrent_resolution_only_executes_fixture_once(
    resolver: FixtureContainer,
) -> None:
    """Test that concurrent resolution of the same fixture only executes it once."""
    execution_count = 0

    # Given: a slow async fixture
    async def slow_fixture() -> str:
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.05)
        return "slow_value"

    resolver.register(slow_fixture, scope=FixtureScope.SESSION)

    # When: resolving concurrently from multiple coroutines
    async with resolver:
        results = await asyncio.gather(
            resolver.resolve(slow_fixture),
            resolver.resolve(slow_fixture),
            resolver.resolve(slow_fixture),
        )

    # Then: fixture executed only once, all get same value
    expected_execution_count = 1
    assert execution_count == expected_execution_count
    assert all(result == "slow_value" for result in results)


# --- Suite Scope Tests ---


@pytest.mark.asyncio
async def test_suite_scope_is_cached_within_suite(resolver: FixtureContainer) -> None:
    """Suite-scoped fixtures are cached within the same suite path (current_path)."""

    def suite_fixture() -> str:
        call_counts["suite"] += 1
        return "suite_data"

    resolver.register(suite_fixture, scope=FixtureScope.SUITE)

    async with resolver:
        result1 = await resolver.resolve(suite_fixture, current_path="MySuite")
        result2 = await resolver.resolve(suite_fixture, current_path="MySuite")

        assert result1 == result2
        assert call_counts["suite"] == 1


@pytest.mark.asyncio
async def test_suite_scope_not_cached_across_suites(resolver: FixtureContainer) -> None:
    """Suite-scoped fixtures have separate instances per suite (current_path)."""

    def suite_fixture() -> str:
        call_counts["suite_multi"] += 1
        return "suite_data"

    resolver.register(suite_fixture, scope=FixtureScope.SUITE)

    async with resolver:
        result1 = await resolver.resolve(suite_fixture, current_path="SuiteA")
        result2 = await resolver.resolve(suite_fixture, current_path="SuiteB")

        assert result1 == result2 == "suite_data"
        # Called twice: once for SuiteA, once for SuiteB
        assert call_counts["suite_multi"] == 2


@pytest.mark.asyncio
async def test_suite_fixture_can_depend_on_session_fixture(
    resolver: FixtureContainer,
) -> None:
    """Suite-scoped fixture can depend on session-scoped fixture."""

    def session_fixture() -> str:
        call_counts["session_dep"] += 1
        return "session_data"

    def suite_fixture(
        session: Annotated[str, Use(session_fixture)],
    ) -> str:
        call_counts["suite_dep"] += 1
        return f"suite_using_{session}"

    resolver.register(session_fixture, scope=FixtureScope.SESSION)
    resolver.register(suite_fixture, scope=FixtureScope.SUITE)

    async with resolver:
        result = await resolver.resolve(suite_fixture, current_path="MySuite")
        assert result == "suite_using_session_data"
        assert call_counts["session_dep"] == 1
        assert call_counts["suite_dep"] == 1


def test_suite_scope_cannot_depend_on_test_scope(resolver: FixtureContainer) -> None:
    """Suite-scoped fixture cannot depend on test-scoped fixture."""

    def test_fixture() -> str:
        return "test_data"

    def suite_fixture(
        dep: Annotated[str, Use(test_fixture)],
    ) -> str:
        return f"using_{dep}"

    resolver.register(test_fixture, scope=FixtureScope.TEST)

    with pytest.raises(ScopeMismatchError):
        resolver.register(suite_fixture, scope=FixtureScope.SUITE)


@pytest.mark.asyncio
async def test_suite_teardown(resolver: FixtureContainer) -> None:
    """Suite fixtures are torn down when teardown_path is called."""

    def suite_gen() -> Generator[str, None, None]:
        call_counts["suite_gen"] += 1
        yield "suite_gen_data"
        teardown_counts["suite_gen"] += 1

    resolver.register(suite_gen, scope=FixtureScope.SUITE)

    async with resolver:
        await resolver.resolve(suite_gen, current_path="MySuite")
        assert teardown_counts["suite_gen"] == 0

        await resolver.teardown_path("MySuite")
        assert teardown_counts["suite_gen"] == 1


@pytest.mark.asyncio
async def test_teardown_order_is_lifo_across_paths(resolver: FixtureContainer) -> None:
    """Teardown happens in LIFO order based on resolution order."""
    teardown_order: list[str] = []

    def fixture_a() -> Generator[str, None, None]:
        yield "a"
        teardown_order.append("a")

    def fixture_b() -> Generator[str, None, None]:
        yield "b"
        teardown_order.append("b")

    def fixture_c() -> Generator[str, None, None]:
        yield "c"
        teardown_order.append("c")

    resolver.register(fixture_a, scope=FixtureScope.SUITE)
    resolver.register(fixture_b, scope=FixtureScope.SUITE)
    resolver.register(fixture_c, scope=FixtureScope.SUITE)

    async with resolver:
        await resolver.resolve(fixture_a, current_path="Parent")
        await resolver.resolve(fixture_b, current_path="Parent::Child")
        await resolver.resolve(fixture_c, current_path="Parent::Child::GrandChild")

    # Teardown in reverse order of path registration
    assert teardown_order == ["c", "b", "a"]


class TestFixtureContainerWithFixtureWrapper:
    def test_has_fixture_with_wrapper(self, resolver: FixtureContainer) -> None:
        @fixture()
        def my_fixture() -> str:
            return "data"

        resolver.register(my_fixture.func, scope=FixtureScope.SESSION)

        assert resolver.has_fixture(my_fixture) is True
        assert isinstance(my_fixture, FixtureWrapper)

    def test_get_fixture_with_wrapper(self, resolver: FixtureContainer) -> None:
        @fixture()
        def my_fixture() -> str:
            return "data"

        resolver.register(my_fixture.func, scope=FixtureScope.SESSION)

        result = resolver.get_fixture(my_fixture)
        assert result is not None
        assert result.func is my_fixture.func

    def test_get_scope_with_wrapper(self, resolver: FixtureContainer) -> None:
        @fixture()
        def my_fixture() -> str:
            return "data"

        resolver.register(my_fixture.func, scope=FixtureScope.SUITE)

        result = resolver.get_scope(my_fixture)
        assert result == FixtureScope.SUITE


class TestTransitiveTags:
    def test_get_transitive_tags_single_level(self, resolver: FixtureContainer) -> None:
        @fixture()
        def db_fixture() -> str:
            return "db"

        @fixture()
        def api_fixture(db: Annotated[str, Use(db_fixture)]) -> str:
            return f"api_{db}"

        resolver.register(
            db_fixture.func, scope=FixtureScope.SESSION, tags={"database"}
        )
        resolver.register(api_fixture.func, scope=FixtureScope.SESSION, tags={"api"})

        tags = resolver.get_transitive_tags(api_fixture)
        assert tags == {"api", "database"}

    def test_get_transitive_tags_multi_level(self, resolver: FixtureContainer) -> None:
        @fixture()
        def fixture_a() -> str:
            return "a"

        @fixture()
        def fixture_b(dep: Annotated[str, Use(fixture_a)]) -> str:
            return f"b_{dep}"

        @fixture()
        def fixture_c(dep: Annotated[str, Use(fixture_b)]) -> str:
            return f"c_{dep}"

        resolver.register(fixture_a.func, scope=FixtureScope.SESSION, tags={"level1"})
        resolver.register(fixture_b.func, scope=FixtureScope.SESSION, tags={"level2"})
        resolver.register(fixture_c.func, scope=FixtureScope.SESSION, tags={"level3"})

        tags = resolver.get_transitive_tags(fixture_c)
        assert tags == {"level1", "level2", "level3"}

    def test_get_transitive_tags_diamond_pattern(
        self, resolver: FixtureContainer
    ) -> None:
        """Diamond dependency: A→B→D and A→C→D collects D's tags once.

        This test covers the `if actual_func in visited: return set()` branch
        in _collect_transitive_tags which handles shared dependencies.
        """

        @fixture()
        def fixture_d() -> str:
            return "d"

        @fixture()
        def fixture_b(dep: Annotated[str, Use(fixture_d)]) -> str:
            return f"b_{dep}"

        @fixture()
        def fixture_c(dep: Annotated[str, Use(fixture_d)]) -> str:
            return f"c_{dep}"

        @fixture()
        def fixture_a(
            b: Annotated[str, Use(fixture_b)],
            c: Annotated[str, Use(fixture_c)],
        ) -> str:
            return f"a_{b}_{c}"

        resolver.register(fixture_d.func, scope=FixtureScope.SESSION, tags={"shared"})
        resolver.register(fixture_b.func, scope=FixtureScope.SESSION, tags={"branch_b"})
        resolver.register(fixture_c.func, scope=FixtureScope.SESSION, tags={"branch_c"})
        resolver.register(fixture_a.func, scope=FixtureScope.SESSION, tags={"top"})

        tags = resolver.get_transitive_tags(fixture_a)
        assert tags == {"top", "branch_b", "branch_c", "shared"}

    def test_get_fixture_tags_direct(self, resolver: FixtureContainer) -> None:
        @fixture()
        def tagged_fixture() -> str:
            return "tagged"

        resolver.register(
            tagged_fixture.func,
            scope=FixtureScope.SESSION,
            tags={"slow", "integration"},
        )

        tags = resolver.get_fixture_tags(tagged_fixture)
        assert tags == {"slow", "integration"}


class TestAsyncGeneratorFixtures:
    @pytest.mark.asyncio
    async def test_async_generator_fixture_yields_value(
        self, resolver: FixtureContainer
    ) -> None:
        async def async_gen_fixture() -> AsyncGenerator[str, None]:
            call_counts["async_gen"] += 1
            yield "async_gen_data"
            teardown_counts["async_gen"] += 1

        resolver.register(async_gen_fixture, scope=FixtureScope.SESSION)

        async with resolver:
            result = await resolver.resolve(async_gen_fixture)
            assert result == "async_gen_data"
            assert call_counts["async_gen"] == 1

    @pytest.mark.asyncio
    async def test_async_generator_fixture_teardown_on_exit(
        self, resolver: FixtureContainer
    ) -> None:
        async def async_gen_fixture() -> AsyncGenerator[str, None]:
            call_counts["async_gen_teardown"] += 1
            yield "async_gen_data"
            teardown_counts["async_gen_teardown"] += 1

        resolver.register(async_gen_fixture, scope=FixtureScope.SESSION)

        async with resolver:
            await resolver.resolve(async_gen_fixture)
            assert teardown_counts["async_gen_teardown"] == 0

        assert teardown_counts["async_gen_teardown"] == 1

    @pytest.mark.asyncio
    async def test_async_generator_with_dependency(
        self, resolver: FixtureContainer
    ) -> None:
        resolver.register(session_dependency, scope=FixtureScope.SESSION)

        async def async_gen_with_dep(
            data: Annotated[str, Use(session_dependency)],
        ) -> AsyncGenerator[str, None]:
            call_counts["async_gen_dep"] += 1
            yield f"async_{data}"
            teardown_counts["async_gen_dep"] += 1

        resolver.register(async_gen_with_dep, scope=FixtureScope.SESSION)

        async with resolver:
            result = await resolver.resolve(async_gen_with_dep)
            assert result == "async_session_data"

        assert teardown_counts["async_gen_dep"] == 1


class TestSuiteScopeConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_resolution_same_suite_fixture(
        self, resolver: FixtureContainer
    ) -> None:
        execution_count = 0

        async def slow_suite_fixture() -> str:
            nonlocal execution_count
            execution_count += 1
            await asyncio.sleep(0.05)
            return "slow_suite_value"

        resolver.register(slow_suite_fixture, scope=FixtureScope.SUITE)

        async with resolver:
            results = await asyncio.gather(
                resolver.resolve(slow_suite_fixture, current_path="MySuite"),
                resolver.resolve(slow_suite_fixture, current_path="MySuite"),
                resolver.resolve(slow_suite_fixture, current_path="MySuite"),
            )

        expected_execution_count = 1
        assert execution_count == expected_execution_count
        assert all(result == "slow_suite_value" for result in results)


class TestAutouseWithWrapper:
    def test_is_autouse_with_fixture_wrapper(self, resolver: FixtureContainer) -> None:
        @fixture()
        def autouse_fixture() -> str:
            return "autouse_data"

        resolver.register(
            autouse_fixture.func, scope=FixtureScope.SESSION, autouse=True
        )

        assert resolver.is_autouse(autouse_fixture) is True

    def test_is_autouse_with_non_autouse(self, resolver: FixtureContainer) -> None:
        @fixture()
        def regular_fixture() -> str:
            return "regular_data"

        resolver.register(
            regular_fixture.func, scope=FixtureScope.SESSION, autouse=False
        )

        assert resolver.is_autouse(regular_fixture) is False

    @pytest.mark.asyncio
    async def test_autouse_valid_for_test_scope(
        self, resolver: FixtureContainer
    ) -> None:
        """TEST-scoped autouse fixtures are resolved via resolve_test_autouse."""
        call_count = 0

        def test_autouse_fixture() -> str:
            nonlocal call_count
            call_count += 1
            return "autouse_value"

        resolver.register(test_autouse_fixture, scope=FixtureScope.TEST, autouse=True)

        assert resolver.is_autouse(test_autouse_fixture) is True

        # TEST-scoped autouse requires context cache and exit stack

        context_cache: dict = {}
        async with AsyncExitStack() as exit_stack:
            await resolver.resolve_test_autouse(
                current_path=None,
                context_cache=context_cache,
                context_exit_stack=exit_stack,
            )

        assert call_count == 1
        assert test_autouse_fixture in context_cache
        assert context_cache[test_autouse_fixture] == "autouse_value"


class TestTeardownEdgeCases:
    @pytest.mark.asyncio
    async def test_teardown_nonexistent_path_is_safe(
        self, resolver: FixtureContainer
    ) -> None:
        async with resolver:
            await resolver.teardown_path("NonExistent")

    @pytest.mark.asyncio
    async def test_teardown_path_clears_cache(self, resolver: FixtureContainer) -> None:
        def suite_fixture() -> str:
            call_counts["cache_test"] += 1
            return "cached_data"

        resolver.register(suite_fixture, scope=FixtureScope.SUITE)

        async with resolver:
            await resolver.resolve(suite_fixture, current_path="MySuite")
            assert call_counts["cache_test"] == 1

            await resolver.teardown_path("MySuite")

            await resolver.resolve(suite_fixture, current_path="MySuite")
            expected_count = 2
            assert call_counts["cache_test"] == expected_count


class TestCircularDependencyDetection:
    @pytest.mark.asyncio
    async def test_direct_cycle_a_depends_on_a(
        self, resolver: FixtureContainer
    ) -> None:
        """Given A depends on itself, when resolving A, then CircularDependencyError is raised."""

        def fixture_a() -> str:
            return "a"

        resolver.register(fixture_a, scope=FixtureScope.SESSION)
        resolver._dependencies[fixture_a] = {"dep": fixture_a}

        with pytest.raises(CircularDependencyError, match=r"fixture_a -> fixture_a"):
            async with resolver:
                await resolver.resolve(fixture_a)

    @pytest.mark.asyncio
    async def test_two_fixture_cycle_a_b_a(self, resolver: FixtureContainer) -> None:
        """Given A → B → A cycle, when resolving A, then CircularDependencyError shows full path."""

        def fixture_a() -> str:
            return "a"

        def fixture_b() -> str:
            return "b"

        resolver.register(fixture_a, scope=FixtureScope.SESSION)
        resolver.register(fixture_b, scope=FixtureScope.SESSION)
        resolver._dependencies[fixture_a] = {"dep": fixture_b}
        resolver._dependencies[fixture_b] = {"dep": fixture_a}

        with pytest.raises(
            CircularDependencyError, match=r"fixture_a -> fixture_b -> fixture_a"
        ):
            async with resolver:
                await resolver.resolve(fixture_a)

    @pytest.mark.asyncio
    async def test_three_fixture_cycle_a_b_c_a(
        self, resolver: FixtureContainer
    ) -> None:
        """Given A → B → C → A cycle, when resolving A, then CircularDependencyError shows full chain."""

        def fixture_a() -> str:
            return "a"

        def fixture_b() -> str:
            return "b"

        def fixture_c() -> str:
            return "c"

        resolver.register(fixture_a, scope=FixtureScope.SESSION)
        resolver.register(fixture_b, scope=FixtureScope.SESSION)
        resolver.register(fixture_c, scope=FixtureScope.SESSION)
        resolver._dependencies[fixture_a] = {"dep": fixture_b}
        resolver._dependencies[fixture_b] = {"dep": fixture_c}
        resolver._dependencies[fixture_c] = {"dep": fixture_a}

        with pytest.raises(
            CircularDependencyError,
            match=r"fixture_a -> fixture_b -> fixture_c -> fixture_a",
        ):
            async with resolver:
                await resolver.resolve(fixture_a)

    @pytest.mark.asyncio
    async def test_diamond_dependency_no_cycle(
        self, resolver: FixtureContainer
    ) -> None:
        """Given a diamond (A→B, A→C, B→D, C→D), when resolving, then no cycle error."""

        def fixture_d() -> str:
            call_counts["diamond_d"] += 1
            return "d"

        def fixture_b(dep: Annotated[str, Use(fixture_d)]) -> str:
            return f"b_{dep}"

        def fixture_c(dep: Annotated[str, Use(fixture_d)]) -> str:
            return f"c_{dep}"

        def fixture_a(
            dep_b: Annotated[str, Use(fixture_b)],
            dep_c: Annotated[str, Use(fixture_c)],
        ) -> str:
            return f"a_{dep_b}_{dep_c}"

        resolver.register(fixture_d, scope=FixtureScope.SESSION)
        resolver.register(fixture_b, scope=FixtureScope.SESSION)
        resolver.register(fixture_c, scope=FixtureScope.SESSION)
        resolver.register(fixture_a, scope=FixtureScope.SESSION)

        async with resolver:
            result = await resolver.resolve(fixture_a)
            assert result == "a_b_d_c_d"
            expected_call_count = 1
            assert call_counts["diamond_d"] == expected_call_count


class TestTypeHintEdgeCases:
    """Tests for edge cases in type hint resolution."""

    def test_fixture_with_failing_type_hints_still_works(
        self, resolver: FixtureContainer
    ) -> None:
        """When get_type_hints() fails, fixture registration proceeds without deps.

        This covers lines where get_type_hints raises an exception
        (e.g., due to forward references that can't be resolved).
        """

        # Create a fixture and manually set an invalid forward reference
        def fixture_with_bad_hints(dep: object) -> str:
            return "works"

        # Override annotation with unresolvable forward reference
        fixture_with_bad_hints.__annotations__["dep"] = "NonExistentType"

        # Should not raise - the exception in get_type_hints is caught
        resolver.register(fixture_with_bad_hints, scope=FixtureScope.SESSION)

        # Fixture registered with no dependencies (since hints couldn't be resolved)
        assert fixture_with_bad_hints in resolver._registry
        assert resolver._dependencies.get(fixture_with_bad_hints, {}) == {}


class TestSameScopeDependency:
    """Tests for fixtures depending on fixtures in the same scope."""

    def test_suite_fixture_can_depend_on_suite_fixture(
        self, resolver: FixtureContainer
    ) -> None:
        """Suite-scoped fixture can depend on another suite-scoped fixture."""

        def base_fixture() -> str:
            return "base"

        def dependent_fixture(
            base: Annotated[str, Use(base_fixture)],
        ) -> str:
            return f"dependent_{base}"

        # Both fixtures have SUITE scope
        resolver.register(base_fixture, scope=FixtureScope.SUITE)
        resolver.register(dependent_fixture, scope=FixtureScope.SUITE)

        # Should not raise ScopeMismatchError
        assert resolver.get_scope(base_fixture) == FixtureScope.SUITE
        assert resolver.get_scope(dependent_fixture) == FixtureScope.SUITE

    @pytest.mark.asyncio
    async def test_same_scope_fixtures_resolve_correctly(
        self, resolver: FixtureContainer
    ) -> None:
        """Suite-scoped fixtures resolve and cache correctly."""

        def base_fixture() -> str:
            call_counts["same_suite_base"] += 1
            return "base_value"

        def dependent_fixture(
            base: Annotated[str, Use(base_fixture)],
        ) -> str:
            return f"dependent_{base}"

        resolver.register(base_fixture, scope=FixtureScope.SUITE)
        resolver.register(dependent_fixture, scope=FixtureScope.SUITE)

        async with resolver:
            result = await resolver.resolve(dependent_fixture, current_path="MySuite")
            assert result == "dependent_base_value"
            assert call_counts["same_suite_base"] == 1


class TestGetSuitePath:
    """Tests for get_suite_path()."""

    def test_returns_path_for_suite_fixture(self, resolver: FixtureContainer) -> None:
        """get_suite_path returns the owner path for SUITE fixtures."""

        def suite_fixture() -> str:
            return "suite_data"

        suite_path = SuitePath("MySuite")
        resolver.register(
            suite_fixture, scope=FixtureScope.SUITE, suite_path=suite_path
        )

        assert resolver.get_suite_path(suite_fixture) == suite_path

    def test_returns_none_for_session_fixture(self, resolver: FixtureContainer) -> None:
        """get_suite_path returns None for SESSION fixtures (no owner path)."""

        def session_fixture() -> str:
            return "session_data"

        resolver.register(session_fixture, scope=FixtureScope.SESSION)

        assert resolver.get_suite_path(session_fixture) is None


class TestAutouseResolvers:
    """Tests for resolve_suite_autouse and resolve_session_autouse."""

    @pytest.mark.asyncio
    async def test_resolve_suite_autouse_skips_non_suite_fixtures(
        self, resolver: FixtureContainer
    ) -> None:
        """resolve_suite_autouse only resolves SUITE-scoped autouse fixtures."""
        session_calls = 0
        suite_calls = 0
        test_calls = 0

        def session_autouse() -> str:
            nonlocal session_calls
            session_calls += 1
            return "session"

        def suite_autouse() -> str:
            nonlocal suite_calls
            suite_calls += 1
            return "suite"

        def test_autouse() -> str:
            nonlocal test_calls
            test_calls += 1
            return "test"

        suite_path = SuitePath("MySuite")
        resolver.register(session_autouse, scope=FixtureScope.SESSION, autouse=True)
        resolver.register(
            suite_autouse, scope=FixtureScope.SUITE, autouse=True, suite_path=suite_path
        )
        resolver.register(test_autouse, scope=FixtureScope.TEST, autouse=True)

        async with resolver:
            await resolver.resolve_suite_autouse(suite_path)

        # Only SUITE fixture should be called
        assert session_calls == 0
        assert suite_calls == 1
        assert test_calls == 0

    @pytest.mark.asyncio
    async def test_resolve_suite_autouse_skips_fixtures_without_path(
        self, resolver: FixtureContainer
    ) -> None:
        """resolve_suite_autouse skips SUITE fixtures without an owner path."""
        calls = 0

        def orphan_suite_fixture() -> str:
            nonlocal calls
            calls += 1
            return "orphan"

        # Register as SUITE but without suite_path
        resolver.register(orphan_suite_fixture, scope=FixtureScope.SUITE, autouse=True)

        async with resolver:
            await resolver.resolve_suite_autouse(SuitePath("AnySuite"))

        # Should not be called (no owner path)
        assert calls == 0

    @pytest.mark.asyncio
    async def test_resolve_session_autouse(self, resolver: FixtureContainer) -> None:
        """resolve_session_autouse resolves SESSION-scoped autouse fixtures."""
        session_calls = 0
        suite_calls = 0

        def session_autouse() -> str:
            nonlocal session_calls
            session_calls += 1
            return "session"

        def suite_autouse() -> str:
            nonlocal suite_calls
            suite_calls += 1
            return "suite"

        resolver.register(session_autouse, scope=FixtureScope.SESSION, autouse=True)
        resolver.register(
            suite_autouse,
            scope=FixtureScope.SUITE,
            autouse=True,
            suite_path=SuitePath("MySuite"),
        )

        async with resolver:
            await resolver.resolve_session_autouse()

        # Only SESSION fixture should be called
        assert session_calls == 1
        assert suite_calls == 0
