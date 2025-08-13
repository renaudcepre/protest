from collections.abc import Callable
from typing import Any


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
