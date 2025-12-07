from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.core.suite import ProTestSuite
    from protest.entities.events import TestCounts, TestResult
    from protest.events.types import Event

from protest.utils import get_callable_name

FixtureCallable: TypeAlias = "Callable[..., Any]"


@dataclass(slots=True)
class TestRegistration:
    """Registration info for a test function."""

    func: Callable[..., Any]
    tags: set[str] = field(default_factory=set)
    skip_reason: str | None = None
    xfail_reason: str | None = None
    timeout: float | None = None


@dataclass(slots=True)
class FixtureRegistration:
    """Registration info for a fixture before it's added to the resolver."""

    func: FixtureCallable
    is_factory: bool = False
    cache: bool = True
    managed: bool = True
    tags: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Fixture:
    func: FixtureCallable
    is_factory: bool = False
    cache: bool = True
    managed: bool = True
    tags: set[str] = field(default_factory=set)
    cached_value: Any = field(default=None, repr=False)
    is_cached: bool = False

    def clear_cache(self) -> None:
        self.cached_value = None
        self.is_cached = False


@dataclass(slots=True)
class TestItem:
    func: Callable[..., Any]
    suite: ProTestSuite | None
    tags: set[str] = field(default_factory=set)
    case_kwargs: dict[str, Any] = field(default_factory=dict)
    case_ids: list[str] = field(default_factory=list)
    skip_reason: str | None = None
    xfail_reason: str | None = None
    timeout: float | None = None

    @property
    def test_name(self) -> str:
        return get_callable_name(self.func)

    @property
    def module_path(self) -> str:
        return getattr(self.func, "__module__", "<unknown>")

    @property
    def suite_path(self) -> str | None:
        return self.suite.full_path if self.suite else None

    @property
    def node_id(self) -> str:
        if self.suite_path:
            base = f"{self.module_path}::{self.suite_path}::{self.test_name}"
        else:
            base = f"{self.module_path}::{self.test_name}"
        if self.case_ids:
            return f"{base}[{'-'.join(self.case_ids)}]"
        return base


@dataclass(slots=True)
class TestOutcome:
    result: TestResult
    counts: TestCounts
    event: Event
