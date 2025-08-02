import dataclasses


@dataclasses.dataclass(frozen=True)
class Use:
    """
    A marker used with `typing.Annotated` to signal a dependency injection request.

    This allows the dependency injection system to identify which function parameters
    (for tests or fixtures) need to be resolved and injected.

    Example:
        from typing import Annotated

        def my_test(service: Annotated[MyService, Use()]):
            # The DI resolver will provide an instance of MyService.
            ...
    """
    pass
