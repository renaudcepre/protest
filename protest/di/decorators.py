from collections.abc import Callable
from typing import TypeVar

from protest.core.fixture import FixtureCallable
from protest.core.scope import Scope

FIXTURE_SCOPE_ATTR = "_protest_fixture_scope"

FuncT = TypeVar("FuncT", bound=Callable[..., object])


def fixture(scope: Scope = Scope.FUNCTION) -> Callable[[FuncT], FuncT]:
    def decorator(func: FuncT) -> FuncT:
        setattr(func, FIXTURE_SCOPE_ATTR, scope)
        return func

    return decorator


def get_fixture_scope(func: FixtureCallable) -> Scope | None:
    return getattr(func, FIXTURE_SCOPE_ATTR, None)


def is_fixture(func: FixtureCallable) -> bool:
    return hasattr(func, FIXTURE_SCOPE_ATTR)
