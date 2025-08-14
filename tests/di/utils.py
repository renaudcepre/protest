from collections import defaultdict

# Counter to track how many times a function is called.
call_counts: dict[str, int] = defaultdict(int)


def reset_call_counts() -> None:
    call_counts.clear()
