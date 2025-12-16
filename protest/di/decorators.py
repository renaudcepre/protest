"""Free-standing decorators for function-scoped fixtures and factories."""

import functools
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from protest.di.validation import validate_no_from_params
from protest.entities import FixtureRegistration

FuncT = TypeVar("FuncT", bound=Callable[..., object])


class FixtureWrapper(Generic[FuncT]):
    """Wrapper that holds fixture metadata while remaining callable."""

    __slots__ = ("__dict__", "__wrapped__", "func", "registration")

    func: FuncT
    registration: FixtureRegistration

    def __init__(self, func: FuncT, registration: FixtureRegistration) -> None:
        self.func = func
        self.registration = registration
        functools.update_wrapper(self, func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


def unwrap_fixture(func: Callable[..., Any]) -> Callable[..., Any]:
    """Extract the original function from a FixtureWrapper if needed."""
    if isinstance(func, FixtureWrapper):
        return func.func
    return func


def fixture(
    tags: list[str] | None = None,
) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
    """Decorator for function-scoped fixtures.

    Use this for fixtures that should be fresh per test and need tags.
    For session/suite scoped fixtures, use @session.fixture() or @suite.fixture().

    Args:
        tags: Tags for filtering tests that use this fixture.

    Example:
        @fixture(tags=["database"])
        def db_session():
            yield Session()
            session.rollback()
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)
        registration = FixtureRegistration(
            func=func,
            is_factory=False,
            cache=True,
            managed=True,
            tags=set(tags) if tags else set(),
        )
        return FixtureWrapper(func, registration)

    return decorator


def factory(
    cache: bool = False,
    managed: bool = True,
    tags: list[str] | None = None,
) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
    """Decorator for function-scoped factory fixtures.

    Use this for factories that should be fresh per test.
    For session/suite scoped factories, use @session.factory() or @suite.factory().

    Args:
        cache: If True, cache instances by kwargs within the test. Default False.
        managed: If True (default), wrap in FixtureFactory. If False, return as-is
                 wrapped in SafeProxy (for custom factory classes).
        tags: Tags for filtering tests that use this factory.

    Example:
        @factory(tags=["slow"])
        def user(name: str, role: str = "guest") -> User:
            yield User.create(name=name, role=role)
            user.delete()

        # Non-managed factory class
        @factory(managed=False)
        def user_factory(db: Annotated[Session, Use(db_session)]) -> UserFactory:
            return UserFactory(db=db)
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)
        registration = FixtureRegistration(
            func=func,
            is_factory=True,
            cache=cache,
            managed=managed,
            tags=set(tags) if tags else set(),
        )
        return FixtureWrapper(func, registration)

    return decorator
