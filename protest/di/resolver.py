import inspect
from inspect import signature
from typing import Any, Callable, Dict, Annotated, get_origin, get_args

from protest.core.fixture import Fixture
from protest.core.scope import Scope
from protest.di.markers import Use
from protest.exceptions import ProTestException


class ScopeMismatchError(ProTestException):
    """Raised when a dependency has an incompatible scope."""
    pass


class Resolver:
    """Manages fixture registration, dependency analysis, and resolution."""

    def __init__(self) -> None:
        self._registry: Dict[Callable[..., Any], Fixture] = {}
        self._dependencies: Dict[Callable[..., Any], Dict[str, Callable[..., Any]]] = {}

    def register(self, func: Callable[..., Any], scope: Scope) -> None:
        """Analyzes a function's dependencies and registers it as a Fixture."""
        if func in self._registry:
            if scope.value < self._registry[func].scope.value:
                self._registry[func].scope = scope
            return

        fixture = Fixture(func, scope)
        self._analyze_and_store_dependencies(fixture)
        self._registry[func] = fixture

    def resolve(self, target_func: Callable[..., Any]) -> Any:
        """Resolves a fixture by creating its dependencies and calling it."""
        target_fixture = self._registry[target_func]

        if target_fixture.is_cached:
            return target_fixture.cached_value

        kwargs = {}
        dependencies = self._dependencies.get(target_func, {})
        for param_name, dep_func in dependencies.items():
            kwargs[param_name] = self.resolve(dep_func)

        result = target_fixture.func(**kwargs)
        target_fixture.cached_value = result
        target_fixture.is_cached = True
        return result

    def clear_cache(self, scope: Scope) -> None:
        """Clears the cache for all fixtures within a specific scope."""
        for fixture in self._registry.values():
            if fixture.scope == scope:
                fixture.clear_cache()

    def _analyze_and_store_dependencies(self, fixture: Fixture) -> None:
        """Analyzes a fixture's function signature and populates its dependencies."""
        func_signature = signature(fixture.func)
        dependencies = {}
        for param_name, param in func_signature.parameters.items():
            dep_func = self._extract_dependency_from_parameter(param)
            if dep_func:
                if dep_func not in self._registry:
                    self.register(dep_func, Scope.FUNCTION)
                
                self._validate_scope(fixture, dep_func)
                dependencies[param_name] = dep_func
        
        if dependencies:
            self._dependencies[fixture.func] = dependencies

    def _validate_scope(self, requester: Fixture, dependency_func: Callable[..., Any]) -> None:
        """Ensures a dependency has a wider or equal scope than its requester."""
        dependency_fixture = self._registry[dependency_func]
        if dependency_fixture.scope.value > requester.scope.value:
            raise ScopeMismatchError(
                f"Fixture '{requester.func.__name__}' with scope {requester.scope.name} "
                f"cannot depend on '{dependency_fixture.func.__name__}' with scope {dependency_fixture.scope.name}."
            )

    @staticmethod
    def _extract_dependency_from_parameter(param: inspect.Parameter) -> Callable[..., Any] | None:
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        elif isinstance(param.default, Use):
            return param.default.dependency
        return None
