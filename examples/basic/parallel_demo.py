"""Demo: sync tests running in parallel with -n concurrency.

Run with:
    uv run protest examples.basic.parallel_demo:session -n 1   # ~6s (sequential)
    uv run protest examples.basic.parallel_demo:session -n 4   # ~2s (parallel)
"""

import time

from protest import ProTestSession, ProTestSuite

session = ProTestSession()
suite = ProTestSuite("ParallelDemo")
session.add_suite(suite)


@suite.test()
def test_task_a():
    time.sleep(2)
    assert True


@suite.test()
def test_task_b():
    time.sleep(2)
    assert True


@suite.test()
def test_task_c():
    time.sleep(2)
    assert True


@suite.test()
def test_task_d():
    time.sleep(1)
    assert True


@suite.test()
def test_task_e():
    time.sleep(1)
    assert True


@suite.test()
def test_task_f():
    time.sleep(0.5)
    assert True
