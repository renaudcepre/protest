"""Tests for the Judge protocol and ctx.judge() integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

import pytest

from protest import ForEach, From
from protest.core.runner import TestRunner
from protest.evals import (
    EvalContext,
    EvalSession,
    Judge,
    JudgeResponse,
    TaskResult,
    Verdict,
    evaluator,
)
from protest.plugin import PluginBase

# ---------------------------------------------------------------------------
# Fake judge for testing
# ---------------------------------------------------------------------------


class FakeJudge:
    """Minimal Judge implementation for tests."""

    name: str = "fake-judge"
    provider: str | None = "test"

    async def judge(self, prompt: str, output_type: type) -> JudgeResponse:
        if output_type is bool:
            return JudgeResponse(
                output="pass" in prompt.lower(),
                input_tokens=10,
                output_tokens=5,
                cost=0.001,
            )
        if output_type is str:
            return JudgeResponse(output=f"judged: {prompt[:20]}")
        # For dataclass types, try to construct with defaults
        return JudgeResponse(output=output_type())


class BareJudge:
    """Minimal Judge with required name/provider."""

    name: str = "bare-judge"
    provider: str | None = None

    async def judge(self, prompt: str, output_type: type) -> JudgeResponse:
        return JudgeResponse(output=True)


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestJudgeProtocol:
    def test_fake_judge_satisfies_protocol(self) -> None:
        assert isinstance(FakeJudge(), Judge)

    def test_bare_judge_satisfies_protocol(self) -> None:
        assert isinstance(BareJudge(), Judge)

    def test_non_judge_rejected(self) -> None:
        class NotAJudge:
            def evaluate(self, prompt: str) -> str:
                return "nope"

        assert not isinstance(NotAJudge(), Judge)


# ---------------------------------------------------------------------------
# EvalContext.judge()
# ---------------------------------------------------------------------------


class TestEvalContextJudge:
    @pytest.mark.asyncio
    async def test_judge_happy_path(self) -> None:
        judge = FakeJudge()
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        result = await ctx.judge("pass this", bool)
        assert result is True

    @pytest.mark.asyncio
    async def test_judge_str_output(self) -> None:
        judge = FakeJudge()
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        result = await ctx.judge("hello world", str)
        assert result == "judged: hello world"

    @pytest.mark.asyncio
    async def test_judge_raises_without_judge(self) -> None:
        ctx = EvalContext(
            name="my_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
        )
        with pytest.raises(RuntimeError, match="no judge is configured"):
            await ctx.judge("test", bool)

    @pytest.mark.asyncio
    async def test_judge_error_mentions_case_name(self) -> None:
        ctx = EvalContext(
            name="chatbot_eval",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
        )
        with pytest.raises(RuntimeError, match="chatbot_eval"):
            await ctx.judge("test", bool)

    @pytest.mark.asyncio
    async def test_judge_call_count(self) -> None:
        judge = FakeJudge()
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        assert ctx.judge_call_count == 0
        await ctx.judge("pass 1", bool)
        assert ctx.judge_call_count == 1
        await ctx.judge("pass 2", bool)
        await ctx.judge("pass 3", bool)
        assert ctx.judge_call_count == 3

    @pytest.mark.asyncio
    async def test_judge_tokens_accumulated(self) -> None:
        judge = FakeJudge()  # returns input_tokens=10, output_tokens=5 for bool
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        await ctx.judge("pass 1", bool)
        await ctx.judge("pass 2", bool)
        assert ctx.judge_input_tokens == 20
        assert ctx.judge_output_tokens == 10

    @pytest.mark.asyncio
    async def test_judge_cost_accumulated(self) -> None:
        judge = FakeJudge()  # returns cost=0.001 for bool
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        await ctx.judge("pass 1", bool)
        await ctx.judge("pass 2", bool)
        assert ctx.judge_cost == pytest.approx(0.002)

    @pytest.mark.asyncio
    async def test_judge_none_tokens_not_accumulated(self) -> None:
        """JudgeResponse with tokens=None doesn't affect accumulation."""
        judge = FakeJudge()
        ctx = EvalContext(
            name="test_case",
            inputs="q",
            output="a",
            expected_output=None,
            metadata=None,
            duration=0.1,
            _judge=judge,
        )
        await ctx.judge("hello", str)  # FakeJudge returns no tokens for str
        assert ctx.judge_input_tokens == 0
        assert ctx.judge_output_tokens == 0
        assert ctx.judge_cost == 0.0


# ---------------------------------------------------------------------------
# E2E: EvalSession with judge
# ---------------------------------------------------------------------------

single_case = ForEach(
    [{"inputs": "hello", "expected": "hello", "name": "case_1"}],
    ids=lambda c: c["name"],
)


class TestJudgeE2E:
    def test_judge_available_in_evaluator(self) -> None:
        """Full run: evaluator calls ctx.judge(), result is pass."""

        @evaluator
        async def judge_evaluator(ctx: EvalContext) -> bool:
            return await ctx.judge("pass this", bool)

        session = EvalSession(judge=FakeJudge())

        @session.eval(evaluators=[judge_evaluator])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> str:
            return case["inputs"]

        runner = TestRunner(session)
        result = runner.run()
        assert result.success is True

    def test_no_judge_is_fixture_error(self) -> None:
        """Evaluator calls ctx.judge() without judge configured → infra error."""

        @evaluator
        async def needs_judge(ctx: EvalContext) -> bool:
            return await ctx.judge("test", bool)

        session = EvalSession()  # no judge

        @session.eval(evaluators=[needs_judge])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> str:
            return case["inputs"]

        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_fail(self, result: Any) -> None:
                results.append(result)

        session.register_plugin(Collector())
        runner = TestRunner(session)
        result = runner.run()
        assert result.success is False
        assert len(results) == 1
        assert results[0].is_fixture_error is True

    def test_judge_call_count_in_payload(self) -> None:
        """judge_call_count flows through to EvalPayload."""

        @evaluator
        async def double_judge(ctx: EvalContext) -> bool:
            r1 = await ctx.judge("pass first", bool)
            r2 = await ctx.judge("pass second", bool)
            return r1 and r2

        session = EvalSession(judge=FakeJudge())

        @session.eval(evaluators=[double_judge])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> str:
            return case["inputs"]

        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                results.append(result)

        session.register_plugin(Collector())
        runner = TestRunner(session)
        runner.run()
        assert len(results) == 1
        payload = results[0].eval_payload
        assert payload is not None
        assert payload.judge_call_count == 2
        assert payload.judge_input_tokens == 20  # 10 per call x 2
        assert payload.judge_output_tokens == 10  # 5 per call x 2
        assert payload.judge_cost == pytest.approx(0.002)  # 0.001 per call x 2

    def test_judge_info_derived_from_instance(self) -> None:
        """EvalSession derives JudgeInfo from Judge instance."""
        session = EvalSession(judge=FakeJudge())
        assert session._eval_judge is not None
        assert session._eval_judge.name == "fake-judge"
        assert session._eval_judge.provider == "test"

    def test_no_judge_no_judge_info(self) -> None:
        """EvalSession without judge has no JudgeInfo."""
        session = EvalSession()
        assert session._eval_judge is None

    def test_judge_with_structured_output(self) -> None:
        """Judge returns structured dataclass via output_type."""

        @dataclass
        class JudgeVerdict:
            ok: Annotated[bool, Verdict]

        class StructuredJudge:
            name: str = "structured"
            provider: str | None = None

            async def judge(self, prompt: str, output_type: type) -> JudgeResponse:
                return JudgeResponse(output=output_type(ok=True))

        @evaluator
        async def struct_evaluator(ctx: EvalContext) -> JudgeVerdict:
            return await ctx.judge("evaluate this", JudgeVerdict)

        session = EvalSession(judge=StructuredJudge())

        @session.eval(evaluators=[struct_evaluator])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> str:
            return case["inputs"]

        runner = TestRunner(session)
        result = runner.run()
        assert result.success is True


# ---------------------------------------------------------------------------
# TaskResult: SUT usage tracking
# ---------------------------------------------------------------------------


class TestTaskResult:
    def test_task_result_unwrapped_for_evaluators(self) -> None:
        """TaskResult is unwrapped — evaluators see the plain output."""

        @evaluator
        def check_output(ctx: EvalContext) -> bool:
            return ctx.output == "hello"  # sees str, not TaskResult

        session = EvalSession()

        @session.eval(evaluators=[check_output])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> TaskResult[str]:
            return TaskResult(
                output=case["inputs"],
                input_tokens=100,
                output_tokens=50,
                cost=0.01,
            )

        runner = TestRunner(session)
        result = runner.run()
        assert result.success is True

    def test_task_usage_in_payload(self) -> None:
        """TaskResult tokens/cost flow through to EvalPayload."""

        @evaluator
        def always_pass(ctx: EvalContext) -> bool:
            return True

        session = EvalSession()

        @session.eval(evaluators=[always_pass])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> TaskResult[str]:
            return TaskResult(
                output=case["inputs"],
                input_tokens=200,
                output_tokens=80,
                cost=0.005,
            )

        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                results.append(result)

        session.register_plugin(Collector())
        runner = TestRunner(session)
        runner.run()
        assert len(results) == 1
        payload = results[0].eval_payload
        assert payload is not None
        assert payload.task_input_tokens == 200
        assert payload.task_output_tokens == 80
        assert payload.task_cost == pytest.approx(0.005)

    def test_plain_return_has_zero_task_usage(self) -> None:
        """Plain return (no TaskResult) has zero task usage."""

        @evaluator
        def always_pass(ctx: EvalContext) -> bool:
            return True

        session = EvalSession()

        @session.eval(evaluators=[always_pass])
        def eval_echo(case: Annotated[dict, From(single_case)]) -> str:
            return case["inputs"]

        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                results.append(result)

        session.register_plugin(Collector())
        runner = TestRunner(session)
        runner.run()
        payload = results[0].eval_payload
        assert payload.task_input_tokens == 0
        assert payload.task_output_tokens == 0
        assert payload.task_cost == 0.0
