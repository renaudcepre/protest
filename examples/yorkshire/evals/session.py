"""Yorkshire Chatbot Evals — evaluate the fake Yorkshire expert chatbot.

Run with:
    protest eval examples.yorkshire.evals.session:session
    protest eval examples.yorkshire.evals.session:session -n 4
    protest eval examples.yorkshire.evals.session:session --tag safety
    protest eval examples.yorkshire.evals.session:session --last-failed
"""

from typing import Annotated

from examples.yorkshire.app.chatbot import yorkshire_chatbot
from examples.yorkshire.evals.cases import (
    suite_evaluators,
    yorkshire_cases,
)
from protest import From, ProTestSession
from protest.evals import EvalCase, ModelLabel
from protest.evals.suite import EvalSuite

session = ProTestSession(
    metadata={"version": "1.0", "type": "keyword-matching"},
)

yorkshire_suite = EvalSuite(
    "yorkshire_eval",
    model=ModelLabel(name="yorkshire-chatbot-v1", provider="local"),
)
session.add_suite(yorkshire_suite)


@yorkshire_suite.eval(evaluators=suite_evaluators)
def yorkshire_eval(case: Annotated[EvalCase, From(yorkshire_cases)]) -> str:
    return yorkshire_chatbot(case.inputs)
