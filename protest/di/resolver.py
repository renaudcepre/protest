import inspect
from collections.abc import Callable
from inspect import signature
from typing import Annotated, Any, get_args, get_origin

from protest.core.scope import Scope
from protest.di.markers import Use


class DependencyContainer:
    def __init__(self) -> None:
        self._instance_cache: dict[Scope, dict[Callable[..., Any], Any]] = {scope: {} for scope in Scope}
        self._signature_cache: dict[Callable[..., Any], dict[str, Any]] = {}
        self._dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] = {}

    def dependency_override(self, original: Callable[..., Any], override: Callable[..., Any]) -> None:
        self._dependency_overrides[original] = override

    def clear_dependency_overrides(self) -> None:
        self._dependency_overrides.clear()
        self._signature_cache.clear()

    @staticmethod
    def _extract_dependency_from_parameter(
        param: inspect.Parameter,
    ) -> Callable[..., Any] | None:
        # Case 1: Annotated[Type, Use(dependency)]
        if get_origin(param.annotation) is Annotated:
            annotated_args = get_args(param.annotation)
            for metadata in annotated_args[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        # Case 2: param_name=Use(dependency)
        elif isinstance(param.default, Use):
            return param.default.dependency
        return None

    def _analyze_signature(self, call: Callable[..., Any]) -> dict[str, Any]:
        if call in self._signature_cache:
            return self._signature_cache[call]

        func_signature = signature(call)
        dependencies = {
            param_name: dep_func
            for param_name, param in func_signature.parameters.items()
            if (dep_func := self._extract_dependency_from_parameter(param))
        }

        result = {"dependencies": dependencies}
        self._signature_cache[call] = result
        return result

    def resolve(self, call: Callable[..., Any], scope: Scope) -> Any:
        original_call = call

        if call in self._dependency_overrides:
            call = self._dependency_overrides[call]

        # Check cache for the current scope and higher scopes
        if original_call in self._instance_cache[scope]:
            return self._instance_cache[scope][original_call]
        if scope == Scope.SUITE and original_call in self._instance_cache[Scope.SESSION]:
            return self._instance_cache[Scope.SESSION][original_call]
        if scope == Scope.FUNCTION and original_call in self._instance_cache[Scope.SUITE]:
            return self._instance_cache[Scope.SUITE][original_call]
        if scope == Scope.FUNCTION and original_call in self._instance_cache[Scope.SESSION]:
            return self._instance_cache[Scope.SESSION][original_call]

        signature_info = self._analyze_signature(call)

        kwargs = {
            param_name: self.resolve(dependency, scope)
            for param_name, dependency in signature_info["dependencies"].items()
        }

        result = call(**kwargs)
        self._instance_cache[scope][original_call] = result
        return result
