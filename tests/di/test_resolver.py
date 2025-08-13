import pytest
from typing import Annotated

from protest.di.resolver import Resolver, ScopeMismatchError, AlreadyRegisteredError
from protest.di.markers import Use
from protest.core.scope import Scope
from tests.di.test_dependencies import (
    reset_call_counts, call_counts,
    session_dependency, function_dependency
)

@pytest.fixture
def resolver() -> Resolver:
    """Provides a clean Resolver for each test."""
    reset_call_counts()
    return Resolver()

# --- Scoping and Caching Tests ---

def test_session_scope_is_cached(resolver):
    resolver.register(session_dependency, Scope.SESSION)
    def target(s: Annotated[str, Use(session_dependency)]):
        return s
    resolver.register(target, Scope.SESSION)

    resolver.resolve(target)
    resolver.resolve(target)
    
    assert call_counts["session"] == 1

def test_function_scope_is_not_cached_across_runs(resolver):
    resolver.register(function_dependency, Scope.FUNCTION)
    def target(f: Annotated[str, Use(function_dependency)]):
        return f
    resolver.register(target, Scope.FUNCTION)

    resolver.resolve(target)
    assert call_counts["function"] == 1

    resolver.clear_cache(Scope.FUNCTION)

    resolver.resolve(target)
    assert call_counts["function"] == 2

def test_session_dependency_is_available_in_function_scope(resolver):
    resolver.register(session_dependency, Scope.SESSION)
    def target(s: Annotated[str, Use(session_dependency)]):
        return s
    resolver.register(target, Scope.FUNCTION)

    resolver.resolve(target)
    resolver.clear_cache(Scope.FUNCTION)
    resolver.resolve(target)
    
    assert call_counts["session"] == 1

# --- Invalid Scope Dependency Test ---

def test_session_scope_cannot_depend_on_function_scope(resolver):
    resolver.register(function_dependency, Scope.FUNCTION)
    
    def invalid_session_fixture(f: Annotated[str, Use(function_dependency)]):
        return f"session_using_{f}"
    
    # This will fail fast, during registration/analysis
    with pytest.raises(ScopeMismatchError):
        resolver.register(invalid_session_fixture, Scope.SESSION)

# --- Already Registered Error Test ---

def test_cannot_register_same_function_twice(resolver):
    def my_fixture() -> str:
        return "test"
    
    # First registration should work
    resolver.register(my_fixture, Scope.FUNCTION)
    
    # Second registration should fail
    with pytest.raises(AlreadyRegisteredError, match=r"Function 'my_fixture' is already registered\."):
        resolver.register(my_fixture, Scope.SESSION)