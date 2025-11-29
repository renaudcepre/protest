import inspect
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from inspect import signature
from types import TracebackType
from typing import Annotated, Any, get_args, get_origin

from protest.core.fixture import Fixture, FixtureCallable, get_callable_name
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
        self._registry: dict[FixtureCallable, Fixture] = {}
        self._dependencies: dict[FixtureCallable, dict[str, FixtureCallable]] = {}
        self._exit_stack: ExitStack = ExitStack()

    def register(self, func: FixtureCallable, scope: Scope) -> None:
        """Analyzes a function's dependencies and registers it as a Fixture."""
        if func in self._registry:
            raise AlreadyRegisteredError(get_callable_name(func))

        fixture = Fixture(func, scope)
        self._analyze_and_store_dependencies(fixture)
        self._registry[func] = fixture

    def resolve(self, target_func: FixtureCallable) -> Any:
        """Resolves a fixture by creating its dependencies and calling it."""
        target_fixture = self._registry[target_func]

        if target_fixture.is_cached:
            return target_fixture.cached_value

        kwargs = {
            param_name: self.resolve(dep_func)
            for param_name, dep_func in self._dependencies.get(target_func, {}).items()
        }

        if _is_generator_callable(target_fixture.func):
            context_manager = contextmanager(target_fixture.func)(**kwargs)
            result = self._exit_stack.enter_context(context_manager)
        else:
            result = target_fixture.func(**kwargs)

        target_fixture.cached_value = result
        target_fixture.is_cached = True
        return result

    def __enter__(self) -> "Resolver":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        result = self._exit_stack.__exit__(exc_type, exc_val, exc_tb)
        return result or False

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
                        get_callable_name(fixture.func),
                        get_callable_name(dependency),
                    )

                self._validate_scope(fixture, dependency)
                dependencies[param_name] = dependency
        self._dependencies[fixture.func] = dependencies

    def _validate_scope(
        self, requester: Fixture, dependency_func: FixtureCallable
    ) -> None:
        """Ensures a dependency has a wider or equal scope than its requester."""
        dependency_fixture = self._registry[dependency_func]
        if dependency_fixture.scope.value > requester.scope.value:
            raise ScopeMismatchError(
                get_callable_name(requester.func),
                requester.scope.name,
                get_callable_name(dependency_fixture.func),
                dependency_fixture.scope.name,
            )

    @staticmethod
    def _extract_dependency_from_parameter(
        param: inspect.Parameter,
    ) -> FixtureCallable | None:
        if get_origin(param.annotation) is Annotated:
            for metadata in get_args(param.annotation)[1:]:
                if isinstance(metadata, Use):
                    return metadata.dependency
        return None


def _is_generator_callable(func: FixtureCallable) -> bool:
    if inspect.isgeneratorfunction(func):
        return True
    return_annotation = signature(func).return_annotation
    origin = get_origin(return_annotation)
    return origin is not None and origin is Generator
