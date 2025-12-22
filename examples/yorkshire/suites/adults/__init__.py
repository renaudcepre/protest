"""Adults suite - parent of workers and unemployed.

Demonstrates 3-level suite hierarchy: session → adults → workers/unemployed.
"""

from examples.yorkshire.suites.adults.unemployed import unemployed_suite
from examples.yorkshire.suites.adults.workers import workers_suite
from protest import ProTestSuite

adults_suite = ProTestSuite("Adults")
adults_suite.add_suite(workers_suite)
adults_suite.add_suite(unemployed_suite)

__all__ = ["adults_suite"]
