from collections.abc import Generator
from inspect import Parameter
from typing import Annotated

import pytest

from protest.core.fixture import is_generator_like
from protest.core.scope import Scope
from protest.di.markers import Use
from protest.di.resolver import (
    AlreadyRegisteredError,
    FixtureNotFoundError,
    Resolver,
    ScopeMismatchError,
    UnregisteredDependencyError,
)
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
    resolver.register(session_dependency, Scope.SESSION)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, Scope.SESSION)

    await resolver.resolve(target)
    await resolver.resolve(target)

    assert call_counts["session"] == 1


@pytest.mark.asyncio
async def test_function_scope_is_not_cached_across_runs(resolver: Resolver) -> None:
    resolver.register(function_dependency, Scope.FUNCTION)

    def target(function_data: Annotated[str, Use(function_dependency)]) -> str:
        return function_data

    resolver.register(target, Scope.FUNCTION)

    await resolver.resolve(target)
    assert call_counts["function"] == 1

    resolver.clear_cache(Scope.FUNCTION)

    await resolver.resolve(target)
    assert call_counts["function"] == 2


@pytest.mark.asyncio
async def test_session_dependency_is_available_in_function_scope(
    resolver: Resolver,
) -> None:
    resolver.register(session_dependency, Scope.SESSION)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, Scope.FUNCTION)

    await resolver.resolve(target)
    resolver.clear_cache(Scope.FUNCTION)
    await resolver.resolve(target)

    assert call_counts["session"] == 1


# --- Invalid Scope Dependency Test ---


def test_session_scope_cannot_depend_on_function_scope(resolver: Resolver) -> None:
    resolver.register(function_dependency, Scope.FUNCTION)

    def invalid_session_fixture(
        function_data: Annotated[str, Use(function_dependency)],
    ) -> str:
        return f"session_using_{function_data}"

    with pytest.raises(ScopeMismatchError):
        resolver.register(invalid_session_fixture, Scope.SESSION)


# --- Already Registered Error Test ---


def test_cannot_register_same_function_twice(resolver: Resolver) -> None:
    def my_fixture() -> str:
        return "test"

    resolver.register(my_fixture, Scope.FUNCTION)

    with pytest.raises(
        AlreadyRegisteredError, match=r"Function 'my_fixture' is already registered\."
    ):
        resolver.register(my_fixture, Scope.SESSION)


# --- Unregistered Dependency Error Test ---


def test_fails_on_unregistered_dependency(resolver: Resolver) -> None:
    def unregistered_dependency() -> str:
        return "unregistered_data"

    def fixture_with_unregistered_dep(
        dep: Annotated[str, Use(unregistered_dependency)],
    ) -> str:
        return f"fixture({dep})"

    with pytest.raises(UnregisteredDependencyError, match=r"unregistered function"):
        resolver.register(fixture_with_unregistered_dep, Scope.SESSION)


def test_extract_dependency_returns_none_for_regular_params() -> None:
    regular_param = Parameter(
        "regular_param", Parameter.POSITIONAL_OR_KEYWORD, annotation=str
    )

    result = Resolver._extract_dependency_from_parameter(regular_param)

    assert result is None


# --- Generator Fixture Tests ---


@pytest.mark.asyncio
async def test_generator_fixture_yields_value(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, Scope.SESSION)

    async with resolver:
        result = await resolver.resolve(generator_session_fixture)
        assert result == "generator_session_data"
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exit(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, Scope.SESSION)

    async with resolver:
        await resolver.resolve(generator_session_fixture)
        assert teardown_counts["generator_session"] == 0

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_is_cached(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, Scope.SESSION)

    async with resolver:
        result_first = await resolver.resolve(generator_session_fixture)
        result_second = await resolver.resolve(generator_session_fixture)
        assert result_first == result_second
        assert call_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_generator_fixture_with_dependency(resolver: Resolver) -> None:
    resolver.register(session_dependency, Scope.SESSION)

    def generator_with_dep(
        data: Annotated[str, Use(session_dependency)],
    ) -> Generator[str, None, None]:
        call_counts["generator_with_dep"] += 1
        yield f"generated_{data}"
        teardown_counts["generator_with_dep"] += 1

    resolver.register(generator_with_dep, Scope.SESSION)

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
    teardown_order: list[str] = []

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

    resolver.register(first_generator, Scope.SESSION)
    resolver.register(second_generator, Scope.SESSION)

    async with resolver:
        result = await resolver.resolve(second_generator)
        assert result == "second_with_first_value"

    assert teardown_order == ["second", "first"]


@pytest.mark.asyncio
async def test_generator_fixture_teardown_on_exception(resolver: Resolver) -> None:
    resolver.register(generator_session_fixture, Scope.SESSION)

    with pytest.raises(ValueError, match="test exception"):
        async with resolver:
            await resolver.resolve(generator_session_fixture)
            raise ValueError("test exception")

    assert teardown_counts["generator_session"] == 1


@pytest.mark.asyncio
async def test_mixed_regular_and_generator_fixtures(resolver: Resolver) -> None:
    resolver.register(session_dependency, Scope.SESSION)
    resolver.register(generator_function_fixture, Scope.FUNCTION)

    def mixed_target(
        regular: Annotated[str, Use(session_dependency)],
        generated: Annotated[str, Use(generator_function_fixture)],
    ) -> str:
        return f"{regular}_{generated}"

    resolver.register(mixed_target, Scope.FUNCTION)

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


# --- FixtureNotFoundError Tests ---


@pytest.mark.asyncio
async def test_resolve_unregistered_fixture_raises_fixture_not_found(
    resolver: Resolver,
) -> None:
    """Test that resolving an unregistered fixture raises FixtureNotFoundError."""

    def unregistered_fixture() -> str:
        return "data"

    with pytest.raises(FixtureNotFoundError, match=r"not registered"):
        await resolver.resolve(unregistered_fixture)
