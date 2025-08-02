# A collection of simple functions to be used as dependencies in tests.

# Counter to track how many times a function is called.
from collections import defaultdict

call_counts = defaultdict(int)


def reset_call_counts():
    call_counts.clear()


# --- Simple Dependencies ---


def dependency_d():
    call_counts["d"] += 1
    return "d"


def dependency_c(d: str = None):
    call_counts["c"] += 1
    return f"c(d={d})"


def dependency_b(d: str = None):
    call_counts["b"] += 1
    return f"b(d={d})"


def dependency_a(b: str = None, c: str = None):
    call_counts["a"] += 1
    return f"a(b={b}, c={c})"


# --- Scoped Dependencies ---


def session_dependency():
    call_counts["session"] += 1
    return "session_data"


def function_dependency():
    call_counts["function"] += 1
    return "function_data"


# --- Invalid Scope Dependencies ---


def session_needs_function(f=None):
    return f"session_using_{f}"
