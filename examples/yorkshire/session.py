"""Yorkshire Terrier Test Session - Entry Point.

Run with: protest run examples.yorkshire.session:session

Structure:
- Puppies suite (basic tests)
- Adults suite → Workers + Unemployed (hierarchy demo)
- Seniors suite (timeout, xfail, skip, retry)
- Legacy suite (sync-only, sequential)
- Showcase suite (ForEach, mocker, caplog, raises, Retry)
"""

from examples.yorkshire.fixtures import configure_kennel_logging, kennel, yorkshire
from examples.yorkshire.suites.adults import adults_suite
from examples.yorkshire.suites.legacy import legacy_suite
from examples.yorkshire.suites.puppies import puppies_suite
from examples.yorkshire.suites.seniors import seniors_suite
from examples.yorkshire.suites.showcase import showcase_suite
from protest import ProTestSession

session = ProTestSession(concurrency=4)

# Bind session fixtures
session.fixture(configure_kennel_logging, autouse=True)
session.fixture(kennel)
session.fixture(yorkshire)

# Assemble the session
session.add_suite(puppies_suite)
session.add_suite(adults_suite)  # Contains: workers → detectives/chefs, unemployed
session.add_suite(seniors_suite)
session.add_suite(legacy_suite)
session.add_suite(showcase_suite)
