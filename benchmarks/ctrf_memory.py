"""Benchmark CTRF reporter memory consumption."""

import gc
import tempfile
import tracemalloc
from pathlib import Path

from protest import ProTestSession as Session
from protest import ProTestSuite as Suite
from protest.api import run_session
from protest.entities import TestRegistration
from protest.reporting.ctrf import CTRFReporter


def generate_suite(n: int, fail_rate: float, output_size: int) -> Suite:
    """Generate n tests with configurable failure rate and output size."""
    suite = Suite("benchmark")
    fail_count = int(n * fail_rate)

    for i in range(n):
        should_fail = i < fail_count

        if should_fail:

            async def failing_test(*, _size=output_size) -> None:
                if _size > 0:
                    print("x" * _size)  # noqa: T201
                raise ValueError("Simulated failure " + "x" * 1000)

            failing_test.__name__ = f"test_{i}"
            suite._tests.append(
                TestRegistration(
                    func=failing_test,
                    tags=set(),
                    skip=None,
                    xfail=None,
                    timeout=None,
                    retry=None,
                )
            )
        else:

            async def passing_test(*, _size=output_size) -> None:
                if _size > 0:
                    print("x" * _size)  # noqa: T201

            passing_test.__name__ = f"test_{i}"
            suite._tests.append(
                TestRegistration(
                    func=passing_test,
                    tags=set(),
                    skip=None,
                    xfail=None,
                    timeout=None,
                    retry=None,
                )
            )

    return suite


def run_benchmark(
    n_tests: int, fail_rate: float, output_per_test: int
) -> dict[str, float]:
    suite = generate_suite(n_tests, fail_rate, output_per_test)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        ctrf_path = Path(f.name)

    gc.collect()
    tracemalloc.start()

    session = Session()
    session.add_suite(suite)
    session.register_plugin(CTRFReporter(ctrf_path))
    run_session(session, capture=True, log_file=False, force_no_color=True)

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    file_size = ctrf_path.stat().st_size
    ctrf_path.unlink()

    return {
        "tests": n_tests,
        "fail_rate": fail_rate,
        "output_per_test": output_per_test,
        "peak_memory_mb": peak / 1024 / 1024,
        "current_memory_mb": current / 1024 / 1024,
        "report_size_mb": file_size / 1024 / 1024,
    }


def main() -> None:
    scenarios = [
        (1000, 0.0, 0),  # 1k passing, no output
        (1000, 0.1, 0),  # 1k with 10% failures
        (1000, 0.1, 1000),  # 1k with failures + 1KB output each
        (10000, 0.0, 0),  # 10k passing
        (10000, 0.1, 0),  # 10k with failures
        (10000, 0.1, 1000),  # 10k with failures + output
    ]

    print("CTRF Memory Benchmark")  # noqa: T201
    print("=" * 80)  # noqa: T201
    print(  # noqa: T201
        f"{'Tests':>7} | {'Fail%':>5} | {'Output':>7} | "
        f"{'Peak RAM':>10} | {'Report':>10} | {'RAM/test':>10}"
    )
    print("-" * 80)  # noqa: T201

    for n, fail_rate, output in scenarios:
        result = run_benchmark(n, fail_rate, output)
        ram_per_test = result["peak_memory_mb"] * 1024 / n  # KB per test
        print(  # noqa: T201
            f"{n:>7} | {fail_rate * 100:>4.0f}% | {output:>6}B | "
            f"{result['peak_memory_mb']:>8.2f}MB | "
            f"{result['report_size_mb']:>8.2f}MB | "
            f"{ram_per_test:>8.2f}KB"
        )


if __name__ == "__main__":
    main()
