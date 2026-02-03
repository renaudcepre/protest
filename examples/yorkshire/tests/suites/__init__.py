"""Yorkshire test suites."""

from examples.yorkshire.tests.suites.adults import adults_suite
from examples.yorkshire.tests.suites.custom_factory import custom_factory_suite
from examples.yorkshire.tests.suites.legacy.suite import legacy_suite
from examples.yorkshire.tests.suites.puppies.suite import puppies_suite
from examples.yorkshire.tests.suites.rate_limited import rate_limited_suite
from examples.yorkshire.tests.suites.seniors.suite import seniors_suite
from examples.yorkshire.tests.suites.showcase.suite import showcase_suite

__all__ = [
    "adults_suite",
    "custom_factory_suite",
    "legacy_suite",
    "puppies_suite",
    "rate_limited_suite",
    "seniors_suite",
    "showcase_suite",
]
