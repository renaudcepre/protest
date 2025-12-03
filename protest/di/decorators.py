"""Free-standing decorators for function-scoped fixtures and factories."""

from collections.abc import Callable
from typing import TypeVar

from protest.core.collector import validate_no_from_params
from protest.entities import FixtureRegistration

FuncT = TypeVar("FuncT", bound=Callable[..., object])

METADATA_ATTR = "_protest_registration"


def fixture(
    tags: list[str] | None = None,
) -> Callable[[FuncT], FuncT]:
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

    def decorator(func: FuncT) -> FuncT:
        validate_no_from_params(func)
        func._protest_registration = FixtureRegistration(  # type: ignore[attr-defined]
            func=func,
            is_factory=False,
            cache=True,
            managed=True,
            tags=set(tags) if tags else set(),
        )
        return func

    return decorator


def factory(
    cache: bool = True,
    managed: bool = True,
    tags: list[str] | None = None,
) -> Callable[[FuncT], FuncT]:
    """Decorator for function-scoped factory fixtures.

    Use this for factories that should be fresh per test.
    For session/suite scoped factories, use @session.factory() or @suite.factory().

    Args:
        cache: If True (default), cache instances by kwargs within the test.
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

    def decorator(func: FuncT) -> FuncT:
        validate_no_from_params(func)
        func._protest_registration = FixtureRegistration(  # type: ignore[attr-defined]
            func=func,
            is_factory=True,
            cache=cache,
            managed=managed,
            tags=set(tags) if tags else set(),
        )
        return func

    return decorator
