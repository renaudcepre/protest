from collections import defaultdict
from collections.abc import Generator

call_counts: dict[str, int] = defaultdict(int)
teardown_counts: dict[str, int] = defaultdict(int)


def reset_call_counts() -> None:
    call_counts.clear()
    teardown_counts.clear()


def generator_fixture_factory(name: str) -> Generator[str, None, None]:
    call_counts[name] += 1
    yield f"{name}_value"
    teardown_counts[name] += 1
