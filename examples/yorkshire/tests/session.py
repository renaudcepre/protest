"""Yorkshire Terrier Test Session - Entry Point.

Run with: protest run examples.yorkshire.tests.session:session

Structure:
- Puppies suite (basic tests)
- Adults suite → Workers + Unemployed (hierarchy demo)
- Seniors suite (timeout, xfail, skip, retry)
- Legacy suite (sync-only, sequential)
- Showcase suite (ForEach, mocker, caplog, raises, Retry)
"""

from examples.yorkshire.tests.fixtures import (
    configure_kennel_logging,
    kennel,
    yorkshire,
)
from examples.yorkshire.tests.suites.adults import adults_suite
from examples.yorkshire.tests.suites.legacy.suite import legacy_suite
from examples.yorkshire.tests.suites.puppies.suite import puppies_suite
from examples.yorkshire.tests.suites.seniors.suite import seniors_suite
from examples.yorkshire.tests.suites.showcase.suite import showcase_suite
from protest import ProTestSession

session = ProTestSession(concurrency=4)

# Bind session fixtures
session.bind(configure_kennel_logging, autouse=True)
session.bind(kennel)
session.bind(yorkshire)

# Assemble the session
session.add_suite(puppies_suite)
session.add_suite(adults_suite)  # Contains: workers → detectives/chefs, unemployed
session.add_suite(seniors_suite)
session.add_suite(legacy_suite)
session.add_suite(showcase_suite)
