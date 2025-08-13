# A collection of simple functions to be used as dependencies in tests.

from collections import defaultdict

# Counter to track how many times a function is called.
call_counts: dict[str, int] = defaultdict(int)


def reset_call_counts() -> None:
    call_counts.clear()


# --- Simple Dependencies ---


def dependency_d() -> str:
    call_counts["d"] += 1
    return "d"


def dependency_c(d: str | None = None) -> str:
    call_counts["c"] += 1
    return f"c(d={d})"


def dependency_b(d: str | None = None) -> str:
    call_counts["b"] += 1
    return f"b(d={d})"


def dependency_a(b: str | None = None, c: str | None = None) -> str:
    call_counts["a"] += 1
    return f"a(b={b}, c={c})"


# --- Scoped Dependencies ---


def session_dependency() -> str:
    call_counts["session"] += 1
    return "session_data"


def function_dependency() -> str:
    call_counts["function"] += 1
    return "function_data"


# --- Invalid Scope Dependencies ---


def session_needs_function(f: str | None = None) -> str:
    return f"session_using_{f}"
