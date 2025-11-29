from typing import Any

from protest.core.fixture import Fixture, FixtureCallable, get_callable_name
from protest.di.resolver import Resolver, UnregisteredDependencyError


class SuiteResolver(Resolver):
    """Resolver for suites that delegates parent fixtures to session resolver."""

    def __init__(self, parent_resolver: Resolver, suite_name: str) -> None:
        super().__init__()
        self._parent_resolver = parent_resolver
        self._suite_name = suite_name

    def resolve(self, target_func: FixtureCallable) -> Any:
        if target_func in self._registry:
            return super().resolve(target_func)
        if target_func in self._parent_resolver._registry:
            return self._parent_resolver.resolve(target_func)
        raise UnregisteredDependencyError(
            get_callable_name(target_func),
            get_callable_name(target_func),
        )

    def is_visible(self, func: FixtureCallable) -> bool:
        return func in self._registry or func in self._parent_resolver._registry

    def _analyze_and_store_dependencies(self, fixture: Fixture) -> None:
        from inspect import signature

        from protest.di.markers import Use
        from protest.di.resolver import get_args, get_origin, Annotated

        func_signature = signature(fixture.func)
        dependencies: dict[str, FixtureCallable] = {}

        for param_name, param in func_signature.parameters.items():
            if dependency := self._extract_dependency_from_parameter(param):
                if not self.is_visible(dependency):
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
        from protest.di.resolver import ScopeMismatchError

        if dependency_func in self._registry:
            dependency_fixture = self._registry[dependency_func]
        else:
            dependency_fixture = self._parent_resolver._registry[dependency_func]

        if dependency_fixture.scope.value > requester.scope.value:
            raise ScopeMismatchError(
                get_callable_name(requester.func),
                requester.scope.name,
                get_callable_name(dependency_fixture.func),
                dependency_fixture.scope.name,
            )
