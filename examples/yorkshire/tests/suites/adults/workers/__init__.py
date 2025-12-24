"""Workers suite - demonstrates nested fixtures with scope at binding.

This module showcases:
- Suite fixtures depending on session fixtures
- Child suite fixtures depending on parent suite fixtures
- Autouse fixtures via suite.bind(fn, autouse=True)
- Unbound fixtures defaulting to TEST scope
- Factory fixtures bound to suites
"""

from examples.yorkshire.tests.suites.adults.workers.suite import workers_suite

__all__ = ["workers_suite"]
