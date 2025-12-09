from collections.abc import Generator

from tests.di.utils import call_counts, teardown_counts


def session_dependency() -> str:
    call_counts["session"] += 1
    return "session_data"


def function_dependency() -> str:
    call_counts["function"] += 1
    return "function_data"


def generator_session_fixture() -> Generator[str, None, None]:
    call_counts["generator_session"] += 1
    try:
        yield "generator_session_data"
    finally:
        teardown_counts["generator_session"] += 1


def generator_function_fixture() -> Generator[str, None, None]:
    call_counts["generator_function"] += 1
    try:
        yield "generator_function_data"
    finally:
        teardown_counts["generator_function"] += 1


def generator_without_try_finally() -> Generator[str, None, None]:
    call_counts["no_try_finally"] += 1
    yield "no_try_finally_data"
    teardown_counts["no_try_finally"] += 1
