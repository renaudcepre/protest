from tests.di.utils import call_counts


def session_dependency() -> str:
    call_counts["session"] += 1
    return "session_data"


def function_dependency() -> str:
    call_counts["function"] += 1
    return "function_data"
