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
