"""Adults suite - parent of workers and unemployed.

Demonstrates 3-level suite hierarchy: session → adults → workers/unemployed.
"""

from examples.yorkshire.tests.suites.adults.unemployed.suite import unemployed_suite
from examples.yorkshire.tests.suites.adults.workers import workers_suite
from protest import ProTestSuite

adults_suite = ProTestSuite("Adults")
adults_suite.add_suite(workers_suite)
adults_suite.add_suite(unemployed_suite)

__all__ = ["adults_suite"]
