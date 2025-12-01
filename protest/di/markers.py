from collections.abc import Callable, Iterator, Sequence
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class Use:
    """A marker used with `typing.Annotated` to specify a dependency provider.

    This allows the dependency injection system to identify which function parameters
    (for tests or fixtures) need to be resolved and injected by calling the specified
    provider function.

    Example:
        from typing import Annotated

        def get_user_service():
            return UserService()

        def my_test(service: Annotated[UserService, Use(get_user_service)]):
            # The DI resolver will call get_user_service() and inject the result.
            ...
    """

    def __init__(self, dependency: Callable[..., Any]):
        self.dependency = dependency


class ForEach(Generic[T]):
    """Container for parameterized test cases.

    Example:
        from typing import Annotated

        scenarios = ForEach([
            UserScenario("alice", 200),
            UserScenario("bob", 403),
        ], ids=lambda s: s.name)

        @session.test()
        def test_permissions(scenario: Annotated[UserScenario, From(scenarios)]):
            ...
    """

    def __init__(
        self,
        cases: Sequence[T],
        ids: Callable[[T], str] | None = None,
    ):
        if not cases:
            raise ValueError("ForEach requires at least one case")
        self._cases = list(cases)
        self._ids = ids

    def __iter__(self) -> Iterator[T]:
        return iter(self._cases)

    def __len__(self) -> int:
        return len(self._cases)

    def get_id(self, case: T) -> str:
        if self._ids:
            return self._ids(case)
        return repr(case)


class From:
    """Marker to inject a value from a ForEach source.

    Example:
        codes = ForEach([200, 201, 204])

        @session.test()
        def test_success(code: Annotated[int, From(codes)]):
            assert is_success(code)
    """

    def __init__(self, source: ForEach[Any]):
        self.source = source
