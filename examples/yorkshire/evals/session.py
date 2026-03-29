"""Yorkshire Chatbot Evals — evaluate the fake Yorkshire expert chatbot.

Run with:
    protest eval examples.yorkshire.evals.session:session
    protest eval examples.yorkshire.evals.session:session -n 4
    protest eval examples.yorkshire.evals.session:session --tag safety
    protest eval examples.yorkshire.evals.session:session --last-failed
    protest history --evals --show
"""

from typing import Annotated

from examples.yorkshire.app.chatbot import yorkshire_chatbot
from examples.yorkshire.evals.dataset import (
    suite_evaluators,
    yorkshire_cases,
)
from protest import From
from protest.evals import EvalSession, ModelInfo

session = EvalSession(
    model=ModelInfo(name="yorkshire-chatbot-v1", provider="local"),
    metadata={"version": "1.0", "type": "keyword-matching"},
)


@session.eval(evaluators=suite_evaluators)
def yorkshire_eval(case: Annotated[dict, From(yorkshire_cases)]) -> str:
    return yorkshire_chatbot(case["inputs"])
