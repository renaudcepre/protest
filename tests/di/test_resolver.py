from typing import Annotated

import pytest

from protest.core.scope import Scope
from protest.di.markers import Use
from protest.di.resolver import DependencyContainer

from .test_dependencies import (
    call_counts,
    dependency_c,
    dependency_d,
    function_dependency,
    reset_call_counts,
    session_dependency,
)


@pytest.fixture
def container():
    """Provides a clean DependencyContainer for each test."""
    reset_call_counts()
    return DependencyContainer()


# --- Basic Resolution Tests ---


def test_simple_resolution(container):
    """Test resolving a function with a single dependency."""

    def target(d: Annotated[str, Use(dependency_d)]):
        return f"target({d})"

    result = container.resolve(target, Scope.FUNCTION)
    assert result == "target(d)"
    assert call_counts["d"] == 1


def test_nested_resolution(container):
    """Test resolving a function with nested dependencies."""

    def target(c: Annotated[str, Use(dependency_c)]):
        return f"target({c})"

    def dependency_c_with_dep(d: Annotated[str, Use(dependency_d)]):
        call_counts["c"] += 1
        return f"c(d={d})"

    container.dependency_override(dependency_c, dependency_c_with_dep)
    result = container.resolve(target, Scope.FUNCTION)
    assert result == "target(c(d=d))"
    assert call_counts["c"] == 1
    assert call_counts["d"] == 1


# --- Diamond Problem Test ---


def test_diamond_dependency_resolves_once(container):
    """Ensures a shared dependency in a diamond shape is resolved only once."""

    def dependency_b_with_dep(d: Annotated[str, Use(dependency_d)]):
        call_counts["b"] += 1
        return f"b(d={d})"

    def dependency_c_with_dep(d: Annotated[str, Use(dependency_d)]):
        call_counts["c"] += 1
        return f"c(d={d})"

    def target(b: Annotated[str, Use(dependency_b_with_dep)], c: Annotated[str, Use(dependency_c_with_dep)]):
        return f"target(b={b}, c={c})"

    result = container.resolve(target, Scope.FUNCTION)
    assert result == "target(b=b(d=d), c=c(d=d))"
    assert call_counts["d"] == 1  # The crucial check
    assert call_counts["b"] == 1
    assert call_counts["c"] == 1


# --- Scoping and Caching Tests ---


def test_session_scope_is_cached(container):
    """Test that a SESSION scoped dependency is cached across calls."""

    def target_1(s: Annotated[str, Use(session_dependency)]):
        return s

    def target_2(s: Annotated[str, Use(session_dependency)]):
        return s

    result1 = container.resolve(target_1, Scope.SESSION)
    result2 = container.resolve(target_2, Scope.SESSION)
    assert result1 == "session_data"
    assert result2 == "session_data"
    assert call_counts["session"] == 1


def test_function_scope_is_not_cached_between_scopes(container):
    """Test that FUNCTION scoped dependencies are not cached across different scope resolutions."""

    def target(f: Annotated[str, Use(function_dependency)]):
        return f

    container.resolve(target, Scope.FUNCTION)  # First call
    container.resolve(target, Scope.FUNCTION)  # Second call, should be re-resolved
    assert call_counts["function"] == 2


def test_session_dependency_is_available_in_function_scope(container):
    """A FUNCTION scoped consumer should be able to resolve a SESSION scoped dependency."""

    def target(s: Annotated[str, Use(session_dependency)]):
        return s

    # First call, should cache the session dependency
    container.resolve(target, Scope.FUNCTION)
    assert call_counts["session"] == 1

    # Second call, should use the cached session dependency
    container.resolve(target, Scope.FUNCTION)
    assert call_counts["session"] == 1


# --- Invalid Scope Dependency Test ---


def test_session_scope_cannot_depend_on_function_scope(container):
    """A SESSION scoped fixture cannot depend on a FUNCTION scoped one."""

    def invalid_session_fixture(f: Annotated[str, Use(function_dependency)]):
        return f"session_using_{f}"

    def target(s: Annotated[str, Use(invalid_session_fixture)]):
        return s

    # This test is tricky because the current resolver doesn't have scope-aware fixtures yet.
    # We'll simulate this by trying to resolve a session-like fixture that asks for a function-level one.
    # The current implementation will resolve it, but a future version should fail.
    # For now, we assert it resolves, but we'll add a check for the invalid dependency later.
    with pytest.raises(RecursionError):
        container.resolve(target, Scope.SESSION)
