import inspect

from protest.entities import Fixture, FixtureCallable
from protest.utils import get_callable_name

__all__ = ["Fixture", "FixtureCallable", "get_fixture_name", "is_generator_like"]


def get_fixture_name(func: FixtureCallable) -> str:
    return get_callable_name(func, fallback=repr(func))


def is_generator_like(func: FixtureCallable) -> bool:
    return inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)
