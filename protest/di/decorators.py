"""Standalone decorators for fixtures and factories (Scope at Binding pattern).

These decorators mark functions with intrinsic metadata (is_factory, cache,
managed, tags). Scope and autouse are determined at binding time via
session.fixture() or suite.fixture(). Unbound fixtures default to TEST scope.
"""

import functools
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from protest.di.validation import validate_no_from_params
from protest.entities import FixtureMarker, FixtureRegistration

FuncT = TypeVar("FuncT", bound=Callable[..., object])

# Attribute name for the marker attached to decorated functions
FIXTURE_MARKER_ATTR = "_protest_fixture"


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
        return func.func  # type: ignore[no-any-return]
    return func


def fixture(
    tags: list[str] | None = None,
) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
    """Decorator to mark a function as a fixture.

    Scope is determined at binding time:
    - session.fixture(fn) → SESSION scope
    - suite.fixture(fn) → SUITE scope
    - No binding → TEST scope (default)

    Args:
        tags: Tags for filtering tests that use this fixture.

    Example:
        @fixture(tags=["database"])
        async def database():
            db = await connect()
            yield db
            await db.close()

        session.fixture(database)  # SESSION scope

        @fixture()
        def request_id():
            return str(uuid4())
        # No binding → TEST scope (fresh per test)
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)

        # Create marker with intrinsic properties only
        marker = FixtureMarker(
            is_factory=False,
            cache=True,
            managed=True,
            tags=frozenset(tags) if tags else frozenset(),
        )
        # Attach marker to original function for discovery
        setattr(func, FIXTURE_MARKER_ATTR, marker)

        # Create registration for backwards compatibility with FixtureWrapper
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
    """Decorator to mark a function as a factory fixture.

    Scope is determined at binding time:
    - session.fixture(fn) → SESSION scope
    - suite.fixture(fn) → SUITE scope
    - No binding → TEST scope (default)

    Args:
        cache: If True, cache instances by kwargs within scope. Default False.
        managed: If True (default), wrap in FixtureFactory. If False, return as-is
                 (for custom factory classes).
        tags: Tags for filtering tests that use this factory.

    Example:
        @factory()
        async def user(name: str, role: str = "guest") -> User:
            user = await User.create(name=name, role=role)
            yield user
            await user.delete()

        session.fixture(user)  # SESSION scope

        @factory(cache=True)
        def payload(data: dict | None = None) -> dict:
            return {"default": True, **(data or {})}
        # No binding → TEST scope

        # Non-managed factory class
        @factory(managed=False)
        def user_factory(db: Annotated[Session, Use(db_session)]) -> UserFactory:
            return UserFactory(db=db)
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)

        # Create marker with intrinsic properties only
        marker = FixtureMarker(
            is_factory=True,
            cache=cache,
            managed=managed,
            tags=frozenset(tags) if tags else frozenset(),
        )
        # Attach marker to original function for discovery
        setattr(func, FIXTURE_MARKER_ATTR, marker)

        # Create registration for backwards compatibility with FixtureWrapper
        registration = FixtureRegistration(
            func=func,
            is_factory=True,
            cache=cache,
            managed=managed,
            tags=set(tags) if tags else set(),
        )
        return FixtureWrapper(func, registration)

    return decorator


def get_fixture_marker(func: Callable[..., Any]) -> FixtureMarker | None:
    """Get the FixtureMarker from a decorated function, if present."""
    # Check the wrapper first
    if isinstance(func, FixtureWrapper):
        return getattr(func.func, FIXTURE_MARKER_ATTR, None)
    # Check the function directly
    return getattr(func, FIXTURE_MARKER_ATTR, None)
