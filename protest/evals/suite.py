"""EvalSuite - eval-dedicated suite with judge and model support."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from protest.core.suite import ProTestSuite
from protest.entities import SuiteKind
from protest.evals.wrapper import make_eval_wrapper

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from protest.evals.evaluator import Evaluator, ShortCircuit
    from protest.evals.types import Judge, ModelLabel

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
        model: ModelLabel | None = None,
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
    def model(self) -> ModelLabel | None:
        return self._model

    def eval(
        self,
        evaluators: Sequence[Evaluator | ShortCircuit] | None = None,
        tags: list[str] | None = None,
        timeout: float | None = None,
        judge: Judge | None = None,
    ) -> Callable[[FuncT], FuncT]:
        """Register a scored eval test on this suite.

        Args:
            evaluators: Per-eval evaluators, appended to suite-level ones.
            tags: Tags forwarded to the underlying `@suite.test`.
            timeout: Per-eval timeout in seconds.
            judge: Override the suite-level judge for this eval only.
                Useful when one eval needs a stronger model than the rest
                of the suite. Falls back to `self.judge` when omitted.
        """

        def decorator(func: FuncT) -> FuncT:
            resolved_judge = judge or self._judge
            evals_list: list[Evaluator | ShortCircuit] = (
                list(evaluators) if evaluators else []
            )
            wrapper = make_eval_wrapper(
                func,
                evals_list,
                judge=resolved_judge,
            )
            self.test(tags=tags, timeout=timeout, is_eval=True)(wrapper)
            return func

        return decorator
