"""Legacy decorator module - kept for backward compatibility.

With tree-based scoping, fixtures are registered via:
- @session.fixture() for session scope
- @suite.fixture() for suite scope
- Plain functions for function scope (auto-registered on first use)

The @fixture(scope=...) decorator is deprecated.
"""

from collections.abc import Callable
from typing import TypeVar

from protest.core.fixture import FixtureCallable

FIXTURE_FACTORY_ATTR = "_protest_fixture_factory"

FuncT = TypeVar("FuncT", bound=Callable[..., object])


def is_factory_fixture(func: FixtureCallable) -> bool:
    return getattr(func, FIXTURE_FACTORY_ATTR, False)
