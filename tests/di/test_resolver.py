from inspect import Parameter
from typing import Annotated

import pytest

from protest.core.scope import Scope
from protest.di.markers import Use
from protest.di.resolver import (
    AlreadyRegisteredError,
    Resolver,
    ScopeMismatchError,
    UnregisteredDependencyError,
)
from tests.di.dependencies import (
    function_dependency,
    session_dependency,
)
from tests.di.utils import call_counts, reset_call_counts


@pytest.fixture
def resolver() -> Resolver:
    """Provides a clean Resolver for each test."""
    reset_call_counts()
    return Resolver()


# --- Scoping and Caching Tests ---


def test_session_scope_is_cached(resolver: Resolver) -> None:
    resolver.register(session_dependency, Scope.SESSION)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, Scope.SESSION)

    resolver.resolve(target)
    resolver.resolve(target)

    assert call_counts["session"] == 1


def test_function_scope_is_not_cached_across_runs(resolver: Resolver) -> None:
    resolver.register(function_dependency, Scope.FUNCTION)

    def target(function_data: Annotated[str, Use(function_dependency)]) -> str:
        return function_data

    resolver.register(target, Scope.FUNCTION)

    resolver.resolve(target)
    assert call_counts["function"] == 1

    resolver.clear_cache(Scope.FUNCTION)

    resolver.resolve(target)
    assert call_counts["function"] == 2


def test_session_dependency_is_available_in_function_scope(resolver: Resolver) -> None:
    resolver.register(session_dependency, Scope.SESSION)

    def target(session_data: Annotated[str, Use(session_dependency)]) -> str:
        return session_data

    resolver.register(target, Scope.FUNCTION)

    resolver.resolve(target)
    resolver.clear_cache(Scope.FUNCTION)
    resolver.resolve(target)

    assert call_counts["session"] == 1


# --- Invalid Scope Dependency Test ---


def test_session_scope_cannot_depend_on_function_scope(resolver: Resolver) -> None:
    resolver.register(function_dependency, Scope.FUNCTION)

    def invalid_session_fixture(
        function_data: Annotated[str, Use(function_dependency)],
    ) -> str:
        return f"session_using_{function_data}"

    # This will fail fast, during registration/analysis
    with pytest.raises(ScopeMismatchError):
        resolver.register(invalid_session_fixture, Scope.SESSION)


# --- Already Registered Error Test ---


def test_cannot_register_same_function_twice(resolver: Resolver) -> None:
    def my_fixture() -> str:
        return "test"

    # First registration should work
    resolver.register(my_fixture, Scope.FUNCTION)

    # Second registration should fail
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
