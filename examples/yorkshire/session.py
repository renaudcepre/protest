"""Yorkshire Terrier Unified Session - tests + evals in one session.

Run all (tests + evals):
    protest run examples.yorkshire.session:session

Run only tests:
    protest run examples.yorkshire.session:session
    (protest run filters to kind=test)

Run only evals:
    protest eval examples.yorkshire.session:session
"""

from typing import Annotated

from examples.yorkshire.app.chatbot import yorkshire_chatbot
from examples.yorkshire.evals.cases import suite_evaluators, yorkshire_cases
from examples.yorkshire.tests.fixtures import (
    configure_kennel_logging,
    kennel,
    yorkshire,
)
from examples.yorkshire.tests.plugins import BarkPlugin
from examples.yorkshire.tests.suites.adults import adults_suite
from examples.yorkshire.tests.suites.custom_factory import custom_factory_suite
from examples.yorkshire.tests.suites.legacy.suite import legacy_suite
from examples.yorkshire.tests.suites.puppies.suite import puppies_suite
from examples.yorkshire.tests.suites.rate_limited import rate_limited_suite
from examples.yorkshire.tests.suites.seniors.suite import seniors_suite
from examples.yorkshire.tests.suites.showcase.suite import showcase_suite
from protest import From, ProTestSession
from protest.evals import EvalCase, ModelLabel
from protest.evals.suite import EvalSuite

session = ProTestSession(concurrency=4, history=True)
session.use(BarkPlugin)
session.bind(configure_kennel_logging, autouse=True)
session.bind(kennel)
session.bind(yorkshire)

session.add_suite(puppies_suite)
session.add_suite(adults_suite)
session.add_suite(seniors_suite)
session.add_suite(legacy_suite)
session.add_suite(showcase_suite)
session.add_suite(rate_limited_suite)
session.add_suite(custom_factory_suite)

yorkshire_suite = EvalSuite(
    "yorkshire_eval",
    model=ModelLabel(name="yorkshire-chatbot-v1", provider="local"),
)
session.add_suite(yorkshire_suite)


@yorkshire_suite.eval(evaluators=suite_evaluators)
def yorkshire_eval(case: Annotated[EvalCase, From(yorkshire_cases)]) -> str:
    return yorkshire_chatbot(case.inputs)
