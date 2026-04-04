"""EvalSuite — eval-dedicated suite with judge and model support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from protest.core.suite import ProTestSuite
from protest.entities import SuiteKind
from protest.evals.wrapper import make_eval_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable

    from protest.evals.types import Judge, ModelInfo

FuncT = TypeVar("FuncT", bound="Callable[..., object]")


class EvalSuite(ProTestSuite):
    """Eval-dedicated suite that forces kind=EVAL and carries judge/model config.

    Usage::

        chatbot = EvalSuite("chatbot")
        session.add_suite(chatbot)

        @chatbot.eval(evaluators=[contains_facts])
        async def chatbot(case: Annotated[EvalCase, From(cases)]) -> str:
            return await ask(case.inputs)
    """

    def __init__(
        self,
        name: str,
        *,
        model: ModelInfo | None = None,
        judge: Judge | None = None,
        tags: list[str] | None = None,
        max_concurrency: int | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        suite_meta: dict[str, Any] = dict(metadata) if metadata else {}
        if model is not None:
            suite_meta["model"] = model.name
            suite_meta["provider"] = model.provider
        super().__init__(
            name=name,
            kind=SuiteKind.EVAL,
            tags=tags,
            max_concurrency=max_concurrency,
            description=description,
            metadata=suite_meta,
        )
        self._judge: Judge | None = judge
        self._model = model

    @property
    def judge(self) -> Judge | None:
        return self._judge

    @property
    def model(self) -> ModelInfo | None:
        return self._model

    def eval(
        self,
        evaluators: list[Any] | None = None,
        tags: list[str] | None = None,
        timeout: float | None = None,
        judge: Any = None,
    ) -> Callable[[FuncT], FuncT]:
        """Register a scored eval test on this suite."""

        def decorator(func: FuncT) -> FuncT:
            resolved_judge = judge or self._judge
            wrapper = make_eval_wrapper(
                func,
                evaluators or [],
                judge=resolved_judge,
            )
            self.test(tags=tags, timeout=timeout, is_eval=True)(wrapper)
            return func

        return decorator
