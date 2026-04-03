"""EvalSession — session dédiée aux evals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from protest.core.session import ProTestSession
from protest.entities import SuiteKind
from protest.evals.history import EvalHistoryPlugin
from protest.evals.results_writer import EvalResultsWriter
from protest.evals.suite import EvalSuite
from protest.evals.types import JudgeInfo

if TYPE_CHECKING:
    from pathlib import Path

    from protest.core.suite import ProTestSuite
    from protest.evals.types import Judge, ModelInfo
    from protest.plugin import PluginContext


class EvalSession(ProTestSession):
    """Session dédiée aux evals.

    Usage::

        session = EvalSession(model=ModelInfo(name="qwen-2.5"))

        chatbot = EvalSuite("chatbot")
        session.add_suite(chatbot)

        @chatbot.eval(evaluators=[contains_facts])
        async def chatbot(case: Annotated[dict, From(cases)]) -> str:
            return await ask(case["q"])
    """

    def __init__(
        self,
        *,
        model: ModelInfo | None = None,
        judge: Judge | None = None,
        concurrency: int = 1,
        history: bool = True,
        history_dir: Path | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            concurrency=concurrency,
            history=history,
            history_dir=history_dir,
            metadata=metadata,
        )
        self._eval_model = model
        self._eval_judge_instance: Judge | None = judge
        self._eval_judge: JudgeInfo | None = (
            JudgeInfo(name=judge.name, provider=judge.provider)
            if judge is not None
            else None
        )

    def add_suite(self, suite: ProTestSuite) -> None:
        """Add a suite, propagating session-level model/judge as defaults."""
        if isinstance(suite, EvalSuite):
            if suite.judge is None and self._eval_judge_instance is not None:
                suite._judge = self._eval_judge_instance
            if self._eval_model and "model" not in suite.suite_metadata:
                suite._metadata["model"] = self._eval_model.name
                suite._metadata["provider"] = self._eval_model.provider
        super().add_suite(suite)

    def activate_plugins(self, ctx: PluginContext) -> None:
        """Activate plugins, then wire eval support if needed."""
        super().activate_plugins(ctx)
        if any(s.kind == SuiteKind.EVAL for s in self._suites):
            self._wire_eval_support()

    def _wire_eval_support(self) -> None:
        """Wire eval history + results writer plugins."""
        judge_dict = None
        if self._eval_judge:
            judge_dict = {
                "name": self._eval_judge.name,
                "provider": self._eval_judge.provider,
                "evaluators": list(self._eval_judge.evaluators),
            }

        history = EvalHistoryPlugin(
            history_dir=self._history_dir,
            model=self._eval_model,
            judge=judge_dict,
            metadata=self._metadata,
        )
        self.register_plugin(history)

        writer = EvalResultsWriter(history_dir=self._history_dir)
        self.register_plugin(writer)
