"""Standalone decorators for fixtures and factories (Scope at Binding pattern).

These decorators mark functions with intrinsic metadata (is_factory, cache,
managed, tags). Scope and autouse are determined at binding time via
session.bind() or suite.bind(). Unbound fixtures default to TEST scope.
"""

import functools
from collections.abc import Callable
from typing import Any, Generic, TypeVar

from protest.di.validation import validate_no_from_params
from protest.entities import FixtureMarker, FixtureRegistration
from protest.exceptions import InvalidMaxConcurrencyError

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
    max_concurrency: int | None = None,
) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
    """Decorator to mark a function as a fixture.

    Scope is determined at binding time:
    - session.bind(fn) → SESSION scope
    - suite.bind(fn) → SUITE scope
    - No binding → TEST scope (default)

    Args:
        tags: Tags for filtering tests that use this fixture.
        max_concurrency: Maximum number of tests that can use this fixture
            simultaneously. None means unlimited. Useful for rate-limited
            resources like API clients or connection pools.

    Example:
        @fixture(tags=["database"])
        async def database():
            db = await connect()
            yield db
            await db.close()

        session.bind(database)  # SESSION scope

        @fixture(max_concurrency=2)
        async def api_client():
            # Only 2 tests can use this fixture at once
            yield ApiClient()
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)

        if max_concurrency is not None and max_concurrency < 1:
            raise InvalidMaxConcurrencyError(max_concurrency)

        # Create marker with intrinsic properties only
        marker = FixtureMarker(
            is_factory=False,
            cache=True,
            managed=True,
            tags=frozenset(tags) if tags else frozenset(),
            max_concurrency=max_concurrency,
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
            max_concurrency=max_concurrency,
        )
        return FixtureWrapper(func, registration)

    return decorator


def factory(
    cache: bool = False,
    managed: bool = True,
    tags: list[str] | None = None,
    max_concurrency: int | None = None,
) -> Callable[[FuncT], FixtureWrapper[FuncT]]:
    """Decorator to mark a function as a factory fixture.

    Scope is determined at binding time:
    - session.bind(fn) → SESSION scope
    - suite.bind(fn) → SUITE scope
    - No binding → TEST scope (default)

    Args:
        cache: If True, cache instances by kwargs within scope. Default False.
        managed: If True (default), wrap in FixtureFactory. If False, return as-is
                 (for custom factory classes).
        tags: Tags for filtering tests that use this factory.
        max_concurrency: Maximum number of tests that can use this factory
            simultaneously. None means unlimited.

    Example:
        @factory()
        async def user(name: str, role: str = "guest") -> User:
            user = await User.create(name=name, role=role)
            yield user
            await user.delete()

        session.bind(user)  # SESSION scope

        @factory(cache=True, max_concurrency=5)
        async def api_client(endpoint: str) -> ApiClient:
            # Max 5 tests can use this factory at once
            yield await ApiClient.connect(endpoint)
    """

    def decorator(func: FuncT) -> FixtureWrapper[FuncT]:
        validate_no_from_params(func)

        if max_concurrency is not None and max_concurrency < 1:
            raise InvalidMaxConcurrencyError(max_concurrency)

        # Create marker with intrinsic properties only
        marker = FixtureMarker(
            is_factory=True,
            cache=cache,
            managed=managed,
            tags=frozenset(tags) if tags else frozenset(),
            max_concurrency=max_concurrency,
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
            max_concurrency=max_concurrency,
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
