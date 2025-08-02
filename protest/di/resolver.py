import inspect
from inspect import signature
from typing import Any, Callable, Annotated, get_origin, get_args

from protest.core.scope import Scope
from protest.di.markers import Use
from protest.exceptions import ProTestException


class ScopeMismatchError(ProTestException):
    """Raised when a dependency has an incompatible scope."""
    pass


class DependencyContainer:
    def __init__(self):
        self._instance_cache: dict[Scope, dict[Callable, Any]] = {
            scope: {} for scope in Scope
        }
        self._fixture_scopes: dict[Callable, Scope] = {}
        self._signature_cache: dict[Callable, dict[str, Any]] = {}

    def register(self, dependency: Callable, scope: Scope):
        self._fixture_scopes[dependency] = scope

    def get_scope(self, dependency: Callable) -> Scope:
        return self._fixture_scopes.get(dependency, Scope.FUNCTION)

    def clear_cache(self, scope: Scope):
        self._instance_cache[scope].clear()

    def _analyze_signature(self, call: Callable[..., Any]) -> dict[str, Any]:
        if call in self._signature_cache:
            return self._signature_cache[call]

        dependencies = {
            param_name: dep_func
            for param_name, param in signature(call).parameters.items()
            if (dep_func := self._extract_dependency_from_parameter(param))
        }
        self._signature_cache[call] = {"dependencies": dependencies}
        return self._signature_cache[call]

    def resolve(self, call: Callable[..., Any]) -> Any:
        call_scope = self.get_scope(call)

        # 1. Check cache for the item's own registered scope.
        if call in self._instance_cache[call_scope]:
            return self._instance_cache[call_scope][call]

        signature_info = self._analyze_signature(call)

        kwargs = {}
        for param_name, dependency in signature_info["dependencies"].items():
            dep_scope = self.get_scope(dependency)

            # 2. Validate that the dependency has a wider or equal scope.
            if dep_scope.value > call_scope.value:
                raise ScopeMismatchError(
                    f"Dependency '{dependency.__name__}' with scope {dep_scope.name} "
                    f"cannot be injected into '{call.__name__}' with scope {call_scope.name}."
                )
            
            # 3. Recursively resolve the dependency.
            kwargs[param_name] = self.resolve(dependency)

        # 4. Create and cache the instance in its own scope's cache.
        result = call(**kwargs)
        self._instance_cache[call_scope][call] = result
        return result

    @staticmethod
    def _extract_dependency_from_parameter(
        param: inspect.Parameter,
    ) -> Callable[..., Any] | None:
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        elif isinstance(param.default, Use):
            return param.default.dependency
        return None