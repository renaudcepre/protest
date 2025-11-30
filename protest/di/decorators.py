from collections.abc import Callable
from typing import TypeVar

from protest.core.fixture import FixtureCallable
from protest.core.scope import Scope

FIXTURE_SCOPE_ATTR = "_protest_fixture_scope"
FIXTURE_FACTORY_ATTR = "_protest_fixture_factory"

FuncT = TypeVar("FuncT", bound=Callable[..., object])


def fixture(
    scope: Scope = Scope.FUNCTION,
    factory: bool = False,
) -> Callable[[FuncT], FuncT]:
    """Mark a function as a fixture with lifecycle scope.

    Args:
        scope: When to create/destroy the fixture instance.
            - SESSION: Once per test session (shared across all tests)
            - SUITE: Once per suite (shared within suite)
            - FUNCTION: Fresh instance per test (default)
        factory: If True, the fixture returns a callable that tests invoke
            to create instances on-demand. Errors from the returned callable
            are wrapped as FixtureError for clear error attribution.

    Generator fixtures (with yield) support setup/teardown:
        @fixture(scope=Scope.SESSION)
        async def database():
            db = await connect()
            yield db  # Tests run here
            await db.close()  # Teardown
    """

    def decorator(func: FuncT) -> FuncT:
        setattr(func, FIXTURE_SCOPE_ATTR, scope)
        setattr(func, FIXTURE_FACTORY_ATTR, factory)
        return func

    return decorator


def get_fixture_scope(func: FixtureCallable) -> Scope | None:
    return getattr(func, FIXTURE_SCOPE_ATTR, None)


def is_factory_fixture(func: FixtureCallable) -> bool:
    return getattr(func, FIXTURE_FACTORY_ATTR, False)


def is_fixture(func: FixtureCallable) -> bool:
    return hasattr(func, FIXTURE_SCOPE_ATTR)
