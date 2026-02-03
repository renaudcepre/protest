"""Rate-limited suite - demonstrates fixture max_concurrency.

This module showcases max_concurrency on fixtures to simulate:
- Rate-limited API clients
- Connection pools with limited capacity
- Shared resources requiring controlled access
"""

from examples.yorkshire.tests.suites.rate_limited.suite import rate_limited_suite

__all__ = ["rate_limited_suite"]
