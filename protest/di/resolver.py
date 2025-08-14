import inspect
from collections.abc import Callable
from inspect import signature
from typing import Annotated, Any, get_args, get_origin

from protest.core.fixture import Fixture
from protest.core.scope import Scope
from protest.di.markers import Use
from protest.exceptions import ProTestError


class ScopeMismatchError(ProTestError):
    def __init__(
        self,
        requester_name: str,
        requester_scope: str,
        dependency_name: str,
        dependency_scope: str,
    ):
        super().__init__(
            f"Fixture '{requester_name}' with scope {requester_scope} "
            f"cannot depend on '{dependency_name}' with scope {dependency_scope}."
        )


class AlreadyRegisteredError(ProTestError):
    def __init__(self, function_name: str):
        super().__init__(f"Function '{function_name}' is already registered.")


class UnregisteredDependencyError(ProTestError):
    def __init__(self, fixture_name: str, dependency_name: str):
        super().__init__(
            f"Fixture '{fixture_name}' depends on unregistered "
            f"function '{dependency_name}'. "
            f"Register '{dependency_name}' first."
        )


class Resolver:
    """Manages fixture registration, dependency analysis, and resolution."""

    def __init__(self) -> None:
        self._registry: dict[Callable[..., Any], Fixture] = {}
        self._dependencies: dict[Callable[..., Any], dict[str, Callable[..., Any]]] = {}

    def register(self, func: Callable[..., Any], scope: Scope) -> None:
        """Analyzes a function's dependencies and registers it as a Fixture."""
        if func in self._registry:
            raise AlreadyRegisteredError(func.__name__)

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
            if dependency := self._extract_dependency_from_parameter(param):
                if dependency not in self._registry:
                    raise UnregisteredDependencyError(
                        fixture.func.__name__, dependency.__name__
                    )

                self._validate_scope(fixture, dependency)
                dependencies[param_name] = dependency
        self._dependencies[fixture.func] = dependencies

    def _validate_scope(
        self, requester: Fixture, dependency_func: Callable[..., Any]
    ) -> None:
        """Ensures a dependency has a wider or equal scope than its requester."""
        dependency_fixture = self._registry[dependency_func]
        if dependency_fixture.scope.value > requester.scope.value:
            raise ScopeMismatchError(
                requester.func.__name__,
                requester.scope.name,
                dependency_fixture.func.__name__,
                dependency_fixture.scope.name,
            )

    @staticmethod
    def _extract_dependency_from_parameter(
        param: inspect.Parameter,
    ) -> Callable[..., Any] | None:
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        return None
