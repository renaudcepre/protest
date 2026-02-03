class ProTestError(Exception):
    """Base exception for all errors raised by the ProTest framework."""


class FixtureError(ProTestError):
    """Raised when a factory fixture fails during test execution."""

    def __init__(self, fixture_name: str, original: Exception):
        self.fixture_name = fixture_name
        self.original = original
        super().__init__(f"Factory '{fixture_name}' failed: {original}")


class ScopeMismatchError(ProTestError):
    def __init__(
        self,
        requester_name: str,
        requester_scope: str,
        dependency_name: str,
        dependency_scope: str,
    ):
        super().__init__(
            f"Fixture '{requester_name}' at scope '{requester_scope}' "
            f"cannot depend on '{dependency_name}' at scope '{dependency_scope}'."
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


class FixtureNotFoundError(ProTestError):
    def __init__(self, fixture_name: str):
        super().__init__(f"Fixture '{fixture_name}' is not registered.")


class ParameterizedFixtureError(ProTestError):
    def __init__(self, fixture_name: str, param_names: list[str]):
        params = ", ".join(param_names)
        super().__init__(
            f"Fixture '{fixture_name}' uses From() on parameters: {params}. "
            f"From() is only allowed in tests, not fixtures. "
            f"Use a factory instead and let the test control parameterization."
        )


class PlainFunctionError(ProTestError):
    def __init__(self, func_name: str):
        super().__init__(
            f"Function '{func_name}' must be decorated with @fixture() or @factory(). "
            f"Plain functions are not allowed as fixtures."
        )


class CircularDependencyError(ProTestError):
    def __init__(self, cycle_path: list[str]):
        cycle_str = " -> ".join(cycle_path)
        super().__init__(f"Circular dependency detected: {cycle_str}")


class ConcurrencyMismatchError(ProTestError):
    """Raised when a child suite has higher max_concurrency than its parent."""

    def __init__(
        self,
        child_name: str,
        child_max_concurrency: int,
        parent_name: str,
        parent_effective_concurrency: int,
    ):
        super().__init__(
            f"Suite '{child_name}' has max_concurrency={child_max_concurrency} "
            f"which exceeds parent '{parent_name}' "
            f"(effective max_concurrency={parent_effective_concurrency})."
        )


class InvalidMaxConcurrencyError(ProTestError):
    """Raised when max_concurrency has an invalid value."""

    def __init__(self, value: int):
        super().__init__(
            f"max_concurrency must be >= 1, got {value}. "
            f"Use None for unlimited concurrency."
        )
