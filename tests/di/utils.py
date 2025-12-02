"""Utilities for tracking fixture calls and teardowns in DI tests."""

from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass, field


@dataclass
class FixtureCounters:
    """Container for tracking fixture setup and teardown calls."""

    calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    teardowns: dict[str, int] = field(default_factory=lambda: defaultdict(int))


call_counts: dict[str, int] = defaultdict(int)
teardown_counts: dict[str, int] = defaultdict(int)


def reset_call_counts() -> None:
    call_counts.clear()
    teardown_counts.clear()


def generator_fixture_factory(name: str) -> Generator[str, None, None]:
    call_counts[name] += 1
    yield f"{name}_value"
    teardown_counts[name] += 1
