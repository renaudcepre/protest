"""EvalSession — session dédiée aux evals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from protest.core.session import ProTestSession

if TYPE_CHECKING:
    from pathlib import Path

    from protest.evals.types import Judge, ModelInfo


class EvalSession(ProTestSession):
    """Session dédiée aux evals.

    Usage::

        session = EvalSession(model=ModelInfo(name="qwen-2.5"))

        @session.eval(evaluators=[contains_facts])
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
        if judge is not None:
            from protest.evals.types import JudgeInfo

            self._eval_judge = JudgeInfo.from_instance(judge)
        else:
            self._eval_judge = None
