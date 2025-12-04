import asyncio
from collections.abc import Generator
from inspect import Parameter
from typing import Annotated

import pytest

from protest.core.fixture import is_generator_like
from protest.di.decorators import fixture
from protest.di.markers import Use
from protest.di.resolver import (
    AlreadyRegisteredError,
    Resolver,
    ScopeMismatchError,
)
from protest.exceptions import PlainFunctionError
from tests.di.dependencies import (
    function_dependency,
    generator_function_fixture,
    generator_session_fixture,
    session_dependency,
)
from tests.di.utils import call_counts, reset_call_counts, teardown_counts


@pytest.fixture
def resolver() -> Resolver:
    reset_call_counts()
    return Resolver()


# --- Scoping and Caching Tests ---


@pytest.mark.asyncio
async def test_session_scope_is_cached(resolver: Resolver) -> None:
    resolver.register(session_dependency, scope_path=None)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, scope_path=None)

    await resolver.resolve(target)
    await resolver.resolve(target)

    assert call_counts["session"] == 1


@pytest.mark.asyncio
async def test_function_scope_is_not_cached_across_runs(resolver: Resolver) -> None:
    resolver.register(function_dependency, scope_path=Resolver.FUNCTION_SCOPE)

    def target(function_data: Annotated[str, Use(function_dependency)]) -> str:
        return function_data

    resolver.register(target, scope_path=Resolver.FUNCTION_SCOPE)

    await resolver.resolve(target)
    assert call_counts["function"] == 1

    await resolver.resolve(target)
    assert call_counts["function"] == 2


@pytest.mark.asyncio
async def test_session_dependency_is_available_in_function_scope(
    resolver: Resolver,
) -> None:
    resolver.register(session_dependency, scope_path=None)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, scope_path=Resolver.FUNCTION_SCOPE)

    await resolver.resolve(target)
    await resolver.resolve(target)

    assert call_counts["session"] == 1


# --- Invalid Scope Dependency Test ---


def test_session_scope_cannot_depend_on_function_scope(resolver: Resolver) -> None:
    resolver.register(function_dependency, scope_path=Resolver.FUNCTION_SCOPE)

    def invalid_session_fixture(
        function_data: Annotated[str, Use(function_dependency)],
    ) -> str:
        return f"session_using_{function_data}"

    with pytest.raises(ScopeMismatchError):
        resolver.register(invalid_session_fixture, scope_path=None)


# --- Already Registered Error Test ---


def test_cannot_register_same_function_twice(resolver: Resolver) -> None:
    def my_fixture() -> str:
        return "test"

    resolver.register(my_fixture, scope_path=Resolver.FUNCTION_SCOPE)

    with pytest.raises(
        AlreadyRegisteredError, match=r"Function 'my_fixture' is already registered\."
    ):
        resolver.register(my_fixture, scope_path=None)


# --- Auto-registration and Scope Mismatch Tests ---


def test_undecorated_dependency_raises_plain_function_error(
    resolver: Resolver,
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
        resolver.register(fixture_with_unregistered_dep.func, scope_path=None)

    assert "unregistered_dependency" in str(exc_info.value)


def test_extract_dependency_returns_none_for_regular_params() -> None:
    regular_param = Parameter(
        "regular_param", Parameter.POSITIONAL_OR_KEYWORD, annotation=str
    )

    result = Resolver._extract_dependency_from_parameter(regular_param)

    assert result is None


# --- Generator Fixture Tests ---


@pytest.mark.asyncio
async def test_generator_fixture_yields_value(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, scope_path=None)

    async with resolver:
        result = await resolver.resolve(generator_session_fixture)
        assert result == "generator_session_data"
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exit(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, scope_path=None)

    async with resolver:
        await resolver.resolve(generator_session_fixture)
        assert teardown_counts["generator_session"] == 0

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_is_cached(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, scope_path=None)

    async with resolver:
        result_first = await resolver.resolve(generator_session_fixture)
        result_second = await resolver.resolve(generator_session_fixture)
        assert result_first == result_second
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_with_dependency(resolver: Resolver) -> None:
    resolver.register(session_dependency, scope_path=None)

    def generator_with_dep(
        data: Annotated[str, Use(session_dependency)],
    ) -> Generator[str, None, None]:
        call_counts["generator_with_dep"] += 1
        yield f"generated_{data}"
        teardown_counts["generator_with_dep"] += 1

    resolver.register(generator_with_dep, scope_path=None)

    async with resolver:
        result = await resolver.resolve(generator_with_dep)
        assert result == "generated_session_data"
        assert call_counts["session"] == 1
        assert call_counts["generator_with_dep"] == 1

    assert teardown_counts["generator_with_dep"] == 1


@pytest.mark.asyncio
async def test_multiple_generator_fixtures_teardown_in_reverse_order(
    resolver: Resolver,
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

    resolver.register(first_generator, scope_path=None)
    resolver.register(second_generator, scope_path=None)

    # When: resolving and exiting context
    async with resolver:
        result = await resolver.resolve(second_generator)
        assert result == "second_with_first_value"

    # Then: teardown in reverse order (LIFO)
    assert teardown_order == ["second", "first"]


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exception(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, scope_path=None)

    with pytest.raises(ValueError, match="test exception"):
        async with resolver:
            await resolver.resolve(generator_session_fixture)
            raise ValueError("test exception")

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_mixed_regular_and_generator_fixtures(resolver: Resolver) -> None:
    resolver.register(session_dependency, scope_path=None)
    resolver.register(generator_function_fixture, scope_path=Resolver.FUNCTION_SCOPE)

    def mixed_target(
        regular: Annotated[str, Use(session_dependency)],
        generated: Annotated[str, Use(generator_function_fixture)],
    ) -> str:
        return f"{regular}_{generated}"

    resolver.register(mixed_target, scope_path=Resolver.FUNCTION_SCOPE)

    async with resolver:
        result = await resolver.resolve(mixed_target)
        assert result == "session_data_generator_function_data"

    assert teardown_counts["generator_function"] == 1


def test_is_generator_like_with_sync_generator() -> None:
    def sync_gen() -> Generator[str, None, None]:
        yield "value"

    assert is_generator_like(sync_gen) is True


def test_is_generator_like_with_unannotated_generator() -> None:
    def unannotated_gen():  # type: ignore[no-untyped-def]
        yield "value"

    assert is_generator_like(unannotated_gen) is True


def test_is_generator_like_with_regular_function() -> None:
    def regular_func() -> str:
        return "value"

    assert is_generator_like(regular_func) is False


def test_is_generator_like_ignores_annotation_without_yield() -> None:
    def fake_gen() -> Generator[str, None, None]:
        return "value"  # type: ignore[return-value]

    assert is_generator_like(fake_gen) is False


# --- Auto-registration Tests ---


@pytest.mark.asyncio
async def test_decorated_function_auto_registered_and_resolved(
    resolver: Resolver,
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
async def test_fixture_error_during_setup_propagates(resolver: Resolver) -> None:
    """Test that errors during fixture setup are propagated correctly."""

    @fixture()
    def failing_fixture() -> str:
        raise RuntimeError("Setup failed intentionally")

    resolver.register(failing_fixture.func, scope_path=None)

    with pytest.raises(RuntimeError, match="Setup failed intentionally"):
        await resolver.resolve(failing_fixture)


@pytest.mark.asyncio
async def test_concurrent_resolution_only_executes_fixture_once(
    resolver: Resolver,
) -> None:
    """Test that concurrent resolution of the same fixture only executes it once."""
    execution_count = 0

    # Given: a slow async fixture
    async def slow_fixture() -> str:
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.05)
        return "slow_value"

    resolver.register(slow_fixture, scope_path=None)

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
async def test_suite_scope_is_cached_within_suite(resolver: Resolver) -> None:
    """Suite-scoped fixtures are cached within the same suite path."""

    def suite_fixture() -> str:
        call_counts["suite"] += 1
        return "suite_data"

    resolver.register(suite_fixture, scope_path="MySuite")

    async with resolver:
        result1 = await resolver.resolve(suite_fixture, current_path="MySuite")
        result2 = await resolver.resolve(suite_fixture, current_path="MySuite")

        assert result1 == result2
        assert call_counts["suite"] == 1


@pytest.mark.asyncio
async def test_nested_suite_can_access_parent_fixture(resolver: Resolver) -> None:
    """Nested suite can depend on parent suite's fixtures."""

    def parent_fixture() -> str:
        call_counts["parent"] += 1
        return "parent_data"

    def child_fixture(
        parent: Annotated[str, Use(parent_fixture)],
    ) -> str:
        call_counts["child"] += 1
        return f"child_using_{parent}"

    resolver.register(parent_fixture, scope_path="Parent")
    resolver.register(child_fixture, scope_path="Parent::Child")

    async with resolver:
        result = await resolver.resolve(child_fixture, current_path="Parent::Child")
        assert result == "child_using_parent_data"
        assert call_counts["parent"] == 1
        assert call_counts["child"] == 1


def test_child_suite_cannot_depend_on_sibling_suite(resolver: Resolver) -> None:
    """Suite cannot depend on fixtures from sibling suites."""

    def sibling_fixture() -> str:
        return "sibling_data"

    def my_fixture(
        sibling: Annotated[str, Use(sibling_fixture)],
    ) -> str:
        return f"using_{sibling}"

    resolver.register(sibling_fixture, scope_path="Sibling")

    with pytest.raises(ScopeMismatchError):
        resolver.register(my_fixture, scope_path="MySuite")


@pytest.mark.asyncio
async def test_suite_teardown(resolver: Resolver) -> None:
    """Suite fixtures are torn down when teardown_path is called."""

    def suite_gen() -> Generator[str, None, None]:
        call_counts["suite_gen"] += 1
        yield "suite_gen_data"
        teardown_counts["suite_gen"] += 1

    resolver.register(suite_gen, scope_path="MySuite")

    async with resolver:
        await resolver.resolve(suite_gen, current_path="MySuite")
        assert teardown_counts["suite_gen"] == 0

        await resolver.teardown_path("MySuite")
        assert teardown_counts["suite_gen"] == 1


@pytest.mark.asyncio
async def test_teardown_order_is_lifo(resolver: Resolver) -> None:
    """Teardown happens in LIFO order: children before parents."""
    teardown_order: list[str] = []

    def parent_fixture() -> Generator[str, None, None]:
        yield "parent"
        teardown_order.append("parent")

    def child_fixture() -> Generator[str, None, None]:
        yield "child"
        teardown_order.append("child")

    def grandchild_fixture() -> Generator[str, None, None]:
        yield "grandchild"
        teardown_order.append("grandchild")

    resolver.register(parent_fixture, scope_path="Parent")
    resolver.register(child_fixture, scope_path="Parent::Child")
    resolver.register(grandchild_fixture, scope_path="Parent::Child::GrandChild")

    async with resolver:
        await resolver.resolve(parent_fixture, current_path="Parent")
        await resolver.resolve(child_fixture, current_path="Parent::Child")
        await resolver.resolve(
            grandchild_fixture, current_path="Parent::Child::GrandChild"
        )

    assert teardown_order == ["grandchild", "child", "parent"]
