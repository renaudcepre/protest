import pytest
from typing import Annotated

from protest.di.resolver import DependencyContainer, ScopeMismatchError
from protest.di.markers import Use
from protest.core.scope import Scope
from tests.di.test_dependencies import (
    reset_call_counts, call_counts,
    session_dependency, function_dependency
)

@pytest.fixture
def container():
    """Provides a clean DependencyContainer for each test."""
    reset_call_counts()
    return DependencyContainer()

# --- Scoping and Caching Tests ---

def test_session_scope_is_cached(container):
    """Test that a SESSION scoped dependency is cached across calls."""
    container.register(session_dependency, Scope.SESSION)
    def target(s: Annotated[str, Use(session_dependency)]):
        return s
    container.register(target, Scope.SESSION) # Register the target to resolve it

    container.resolve(target)
    container.resolve(target)
    
    assert call_counts["session"] == 1, "Session dependency should be created only once"

def test_function_scope_is_not_cached_across_runs(container):
    """Test that FUNCTION scoped dependencies are re-created for each run."""
    container.register(function_dependency, Scope.FUNCTION)
    def target(f: Annotated[str, Use(function_dependency)]):
        return f
    # Target is implicitly FUNCTION scope

    container.resolve(target)
    assert call_counts["function"] == 1

    container.clear_cache(Scope.FUNCTION)

    container.resolve(target)
    assert call_counts["function"] == 2, "Function dependency should be re-created"

def test_session_dependency_is_available_in_function_scope(container):
    """A FUNCTION scoped consumer should be able to resolve a SESSION scoped dependency."""
    container.register(session_dependency, Scope.SESSION)
    def target(s: Annotated[str, Use(session_dependency)]):
        return s
    # Target is implicitly FUNCTION scope

    container.resolve(target)
    container.clear_cache(Scope.FUNCTION)
    container.resolve(target)
    
    assert call_counts["session"] == 1, "Session dependency should be cached and reused"

# --- Invalid Scope Dependency Test ---

def test_session_scope_cannot_depend_on_function_scope(container):
    """A SESSION scoped fixture cannot depend on a FUNCTION scoped one."""
    container.register(function_dependency, Scope.FUNCTION)
    
    def invalid_session_fixture(f: Annotated[str, Use(function_dependency)]):
        return f"session_using_{f}"
    container.register(invalid_session_fixture, Scope.SESSION)

    with pytest.raises(ScopeMismatchError) as exc_info:
        container.resolve(invalid_session_fixture)
    
    assert "scope FUNCTION" in str(exc_info.value)
    assert "scope SESSION" in str(exc_info.value)
