"""End-to-end tests for ProTest evals integration.

These tests define the PUBLIC API contract. They test what the user sees:
- Session setup (ProTestSession, EvalSuite + @suite.eval with ForEach/From)
- CLI behavior (protest run vs protest eval)
- Output format (scores table, trends, failure messages)
- History (JSONL format, stats, significance, clean-dirty)
- Built-in evaluators

Implementation can change freely as long as these tests pass.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 — used at runtime (pytest tmp_path)
from typing import Annotated, Any

import pytest

from protest import ForEach, From, ProTestSession, Use, fixture
from protest.api import run_session
from protest.core.collector import Collector
from protest.core.runner import TestRunner
from protest.core.suite import ProTestSuite
from protest.entities import SuiteKind
from protest.evals import (
    EvalCase,
    EvalContext,
    Metric,
    ModelLabel,
    ShortCircuit,
    Verdict,
    evaluator,
)
from protest.evals.evaluators import (
    contains_expected,
    contains_keywords,
    does_not_contain,
    json_valid,
    matches_regex,
    max_length,
    min_length,
    not_empty,
    word_overlap,
)
from protest.evals.hashing import compute_case_hash, compute_eval_hash
from protest.evals.results_writer import EvalResultsWriter
from protest.evals.suite import EvalSuite
from protest.evals.types import EvalSuiteReport  # noqa: TC001 — used at runtime
from protest.filters.kind import KindFilterPlugin
from protest.history.storage import append_entry, clean_dirty
from protest.plugin import PluginBase, PluginContext

# ---------------------------------------------------------------------------
# Fixtures: deterministic evaluators + task
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FakeAccuracyResult:
    """Structured result for fake accuracy evaluator."""

    accuracy: Annotated[float, Metric]
    matches_expected: Annotated[bool, Verdict]


@evaluator
def fake_accuracy(ctx: EvalContext) -> FakeAccuracyResult:
    if ctx.expected_output and ctx.expected_output.lower() in ctx.output.lower():
        return FakeAccuracyResult(accuracy=1.0, matches_expected=True)
    return FakeAccuracyResult(accuracy=0.0, matches_expected=False)


@evaluator
async def async_fake_accuracy(ctx: EvalContext) -> FakeAccuracyResult:
    """Async evaluator — simulates LLMJudge which calls an async LLM API."""
    # Simulate async I/O (e.g. LLM call) without actually blocking
    if ctx.expected_output and ctx.expected_output.lower() in ctx.output.lower():
        return FakeAccuracyResult(accuracy=1.0, matches_expected=True)
    return FakeAccuracyResult(accuracy=0.0, matches_expected=False)


def echo_task(text: str) -> str:
    return f"Echo: {text}"


async def async_echo_task(text: str) -> str:
    return f"Async: {text}"


basic_cases = ForEach(
    [
        EvalCase(inputs="hello world", expected="hello", name="case_pass"),
        EvalCase(inputs="xyz", expected="notfound", name="case_fail"),
    ],
    ids=lambda c: c.name,
)


# ---------------------------------------------------------------------------
# Session setup
# ---------------------------------------------------------------------------


class TestEvalSetup:
    """Eval setup: ProTestSession + EvalSuite with model=, @suite.eval."""

    def test_add_eval_creates_eval_kind(self) -> None:
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        # The session should have a suite with kind=eval
        assert len(session._suites) > 0
        assert any(s.kind == "eval" for s in session._suites)

    def test_model_set_via_suite(self) -> None:
        suite = EvalSuite("eval_echo", model=ModelLabel(name="test-model"))
        assert suite._model is not None
        assert suite._model.name == "test-model"

    def test_metadata_on_constructor(self) -> None:
        session = ProTestSession(metadata={"env": "test"})
        assert session.metadata["env"] == "test"

    def test_eval_with_bool_verdict(self) -> None:
        """Evaluator with bool field: case_fail has matches_expected=False -> fail."""
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()
        # case_pass returns matches_expected=True -> pass
        # case_fail returns matches_expected=False -> fail
        assert result.success is False

    def test_async_task_works(self) -> None:
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        async def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return await async_echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

    def test_async_evaluator_does_not_crash(self) -> None:
        """Regression: async evaluator called via evaluate_sync raised 'event loop already running'."""
        single_case = ForEach(
            [
                EvalCase(inputs="hello world", expected="hello", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[async_fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(single_case)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()
        assert result.success is True


# ---------------------------------------------------------------------------
# Kind filtering (protest run vs protest eval)
# ---------------------------------------------------------------------------


class TestKindFiltering:
    """Suites have kind, filtering works."""

    def test_test_suite_has_kind_test(self) -> None:
        suite = ProTestSuite("my_tests")
        assert suite.kind == "test"

    def test_eval_suite_has_kind_eval(self) -> None:
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        assert any(s.kind == "eval" for s in session._suites)

    def test_kind_filter_keeps_only_matching(self) -> None:
        test_suite = ProTestSuite("tests")
        eval_suite = ProTestSuite("evals", kind=SuiteKind.EVAL)

        session = ProTestSession()

        @test_suite.test()
        def test_one() -> None:
            pass

        @eval_suite.test(is_eval=True)
        def eval_one() -> None:
            pass

        session.add_suite(test_suite)
        session.add_suite(eval_suite)

        items = Collector().collect(session)
        assert len(items) == 2

        # Filter to eval only
        plugin = KindFilterPlugin(kind=SuiteKind.EVAL)
        filtered = plugin.on_collection_finish(items)
        assert len(filtered) == 1
        assert filtered[0].suite.kind == "eval"

    def test_unified_session_runs_tests_only(self) -> None:
        """protest run behavior: only kind=test suites."""
        session = ProTestSession()

        test_suite = ProTestSuite("unit")
        results: list[str] = []

        @test_suite.test()
        def test_a() -> None:
            results.append("test")

        session.add_suite(test_suite)

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        ctx = PluginContext(args={"kind_filter": "test"})
        run_session(session, ctx=ctx)

        assert "test" in results

    def test_unified_session_runs_evals_only(self) -> None:
        """protest eval behavior: only kind=eval suites."""
        session = ProTestSession()

        test_suite = ProTestSuite("unit")
        test_ran = []

        @test_suite.test()
        def test_a() -> None:
            test_ran.append(True)

        session.add_suite(test_suite)

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        ctx = PluginContext(args={"kind_filter": "eval"})
        run_session(session, ctx=ctx)

        assert len(test_ran) == 0  # test suite was filtered out


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


class TestEvalOutput:
    """What the user sees in the terminal.

    These tests verify output by reading the EvalPlugin report directly,
    since ProTest captures stdout during test runs.
    """

    def test_report_contains_score_stats(self) -> None:
        reports: list[EvalSuiteReport] = []

        class ReportCapture(PluginBase):
            name = "report-capture"
            description = "Captures eval reports"

            def on_eval_suite_end(self, report: Any) -> None:
                reports.append(report)

        session = ProTestSession()
        session.register_plugin(ReportCapture())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        assert len(reports) == 1
        stats = reports[0].all_score_stats()
        assert len(stats) > 0
        assert any(s.name == "fake_accuracy.accuracy" for s in stats)

    def test_report_has_pass_count(self) -> None:
        reports: list[EvalSuiteReport] = []

        class ReportCapture(PluginBase):
            name = "report-capture"
            description = "Captures eval reports"

            def on_eval_suite_end(self, report: Any) -> None:
                reports.append(report)

        session = ProTestSession()
        session.register_plugin(ReportCapture())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        assert len(reports) == 1
        assert reports[0].total_count == 2

    def test_failed_eval_has_error_with_score_details(self) -> None:
        """When an eval case fails, the error message includes score details."""
        errors: list[Any] = []

        class ErrorCollector(PluginBase):
            name = "error-collector"

            def on_test_fail(self, result: Any) -> None:
                if result.error:
                    errors.append(str(result.error))

        session = ProTestSession()
        session.register_plugin(ErrorCollector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        run_session(session)

        # case_fail has matches_expected=False
        assert any("matches_expected=" in e for e in errors)


# ---------------------------------------------------------------------------
# EvalPayload flow
# ---------------------------------------------------------------------------


class TestEvalPayloadFlow:
    """EvalPayload flows through the framework correctly."""

    def test_test_result_has_eval_payload(self) -> None:
        collected: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                collected.append(result)

            def on_test_fail(self, result: Any) -> None:
                collected.append(result)

        session = ProTestSession()
        session.register_plugin(Collector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        assert len(collected) == 2
        for result in collected:
            assert result.is_eval is True
            assert result.eval_payload is not None
            assert result.eval_payload.case_name in ("case_pass", "case_fail")
            assert "fake_accuracy.accuracy" in result.eval_payload.scores
            assert "fake_accuracy.matches_expected" in result.eval_payload.scores

    def test_lifecycle_events_have_case_id_in_node_id(self) -> None:
        """setup_done/teardown_start events carry node_id with [case_id]."""
        setup_ids: list[str] = []
        teardown_ids: list[str] = []

        class LifecycleCollector(PluginBase):
            name = "lifecycle-collector"

            def on_test_setup_done(self, info: Any) -> None:
                setup_ids.append(info.node_id)

            def on_test_teardown_start(self, info: Any) -> None:
                teardown_ids.append(info.node_id)

        session = ProTestSession()
        session.register_plugin(LifecycleCollector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        assert len(setup_ids) == 2
        for node_id in setup_ids:
            assert "[" in node_id, f"node_id missing case id: {node_id}"
        for node_id in teardown_ids:
            assert "[" in node_id, f"node_id missing case id: {node_id}"

    def test_evaluator_exception_is_error_not_fail(self) -> None:
        """An evaluator that raises is treated as error (infra), not test fail."""
        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_fail(self, result: Any) -> None:
                results.append(result)

        @evaluator
        def crashing_evaluator(ctx: EvalContext) -> bool:
            raise RuntimeError("LLM judge timeout")

        single_case = ForEach(
            [
                EvalCase(inputs="hello", expected="hello", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()
        session.register_plugin(Collector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[crashing_evaluator])
        def eval_echo(case: Annotated[EvalCase, From(single_case)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        assert len(results) == 1
        assert results[0].is_fixture_error is True
        assert "LLM judge timeout" in str(results[0].error)

    def test_non_eval_test_has_no_payload(self) -> None:
        collected: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                collected.append(result)

        session = ProTestSession()
        session.register_plugin(Collector())

        @session.test()
        def regular_test() -> None:
            assert True

        runner = TestRunner(session)
        runner.run()

        assert len(collected) == 1
        assert collected[0].is_eval is False
        assert collected[0].eval_payload is None


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistory:
    """JSONL history format and querying."""

    def _run_eval(self, tmp_path: Path) -> None:
        session = ProTestSession(history_dir=tmp_path)

        eval_echo_suite = EvalSuite("eval_echo", model=ModelLabel(name="test-model"))
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        run_session(session)

    def test_history_file_created(self, tmp_path: Path) -> None:
        self._run_eval(tmp_path)
        assert (tmp_path / "history.jsonl").exists()

    def test_history_entry_format(self, tmp_path: Path) -> None:
        self._run_eval(tmp_path)
        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        entry = json.loads(lines[0])

        # Required top-level keys
        assert "run_id" in entry
        assert "timestamp" in entry
        assert "git" in entry
        assert "environment" in entry
        assert "metadata" in entry
        assert "evals" in entry
        assert "suites" in entry

        # Evals block
        assert entry["evals"] is not None
        assert entry["evals"]["model"] == "test-model"

        # Suites with kind
        suites = entry["suites"]
        assert len(suites) == 1
        suite_name = next(iter(suites))
        suite = suites[suite_name]
        assert suite["kind"] == "eval"
        assert "total_cases" in suite
        assert "passed" in suite
        assert "cases" in suite

    def test_history_test_run_has_null_evals(self, tmp_path: Path) -> None:
        session = ProTestSession(history=True, history_dir=tmp_path)

        @session.test()
        def test_simple() -> None:
            pass

        run_session(session)

        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["evals"] is None

    def test_history_multiple_runs_append(self, tmp_path: Path) -> None:
        self._run_eval(tmp_path)
        self._run_eval(tmp_path)
        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_history_metadata_included(self, tmp_path: Path) -> None:
        session = ProTestSession(
            history_dir=tmp_path,
            metadata={"env": "test", "version": "1.0"},
        )

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        run_session(session)

        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        entry = json.loads(lines[0])
        assert entry["metadata"]["env"] == "test"


# ---------------------------------------------------------------------------
# History: clean-dirty
# ---------------------------------------------------------------------------


class TestCleanDirty:
    """clean_dirty() storage behavior (removes dirty-tree entries at HEAD)."""

    def test_clean_dirty_removes_current_head_only(self, tmp_path: Path) -> None:
        # Entry with current HEAD + dirty
        try:
            current_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return  # skip if not in a git repo

        path = tmp_path / "history.jsonl"

        # Dirty entry on current HEAD -> should be removed
        append_entry(
            path, {"git": {"commit": current_commit, "dirty": True}, "suites": {}}
        )
        # Dirty entry on old commit -> should be preserved
        append_entry(path, {"git": {"commit": "old123", "dirty": True}, "suites": {}})
        # Clean entry on current HEAD -> should be preserved
        append_entry(
            path, {"git": {"commit": current_commit, "dirty": False}, "suites": {}}
        )

        removed = clean_dirty(history_dir=tmp_path)
        assert removed == 1

        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# Case hashing
# ---------------------------------------------------------------------------


class TestCaseHashing:
    """Content hashing for eval integrity."""

    def test_case_hash_stored_in_history(self, tmp_path: Path) -> None:
        """History entries include case_hash and eval_hash per case."""
        session = ProTestSession(history_dir=tmp_path)

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        run_session(session)

        lines = (tmp_path / "history.jsonl").read_text().strip().splitlines()
        entry = json.loads(lines[0])
        suites = entry["suites"]
        suite = next(iter(suites.values()))
        case = next(iter(suite["cases"].values()))
        assert "case_hash" in case
        assert "eval_hash" in case
        assert len(case["case_hash"]) > 0
        assert len(case["eval_hash"]) > 0

    def test_case_hash_changes_on_input_change(self) -> None:
        """Different inputs -> different case_hash."""
        h1 = compute_case_hash("hello world", "expected")
        h2 = compute_case_hash("hello world modified", "expected")
        assert h1 != h2

    def test_case_hash_stable_for_same_input(self) -> None:
        """Same inputs -> same case_hash (deterministic)."""
        h1 = compute_case_hash("hello world", "expected")
        h2 = compute_case_hash("hello world", "expected")
        assert h1 == h2

    def test_eval_hash_changes_on_evaluator_change(self) -> None:
        """Different evaluators -> different eval_hash."""
        e1 = contains_keywords(keywords=["hello"])
        e2 = contains_keywords(keywords=["hello", "world"])
        h1 = compute_eval_hash([e1])
        h2 = compute_eval_hash([e2])
        assert h1 != h2


# ---------------------------------------------------------------------------
# Built-in evaluators
# ---------------------------------------------------------------------------


class TestBuiltinEvaluators:
    """All built-in evaluators work correctly through protest-native API."""

    def _make_ctx(self, output: str, expected: str | None = None) -> EvalContext:
        """Minimal EvalContext for evaluator testing."""
        return EvalContext(
            name="test",
            inputs="",
            output=output,
            expected_output=expected,
            metadata=None,
            duration=0.0,
        )

    def test_contains_keywords(self) -> None:
        e = contains_keywords(keywords=["hello", "world"])
        result = e.run(self._make_ctx("Hello World"))
        assert result.recall == 1.0
        assert result.all_present is True

    def test_contains_keywords_default_requires_all(self) -> None:
        """Default `min_recall=1.0` means strict: missing one → verdict False."""
        e = contains_keywords(keywords=["hello", "world"])
        result = e.run(self._make_ctx("Only hello here"))
        assert result.recall == 0.5
        assert result.all_present is False

    def test_contains_keywords_threshold_continuity_at_zero(self) -> None:
        """Regression: `min_recall=0.0` must always pass (no discontinuity at 0).

        Earlier behavior: `min_recall=0.0` flipped to strict mode (all required),
        while `min_recall=0.0001` was permissive — surprising at the boundary.
        Now `recall >= min_recall` applies uniformly.
        """
        e = contains_keywords(keywords=["alpha", "beta"], min_recall=0.0)
        result = e.run(self._make_ctx("nothing matches"))
        assert result.recall == 0.0
        assert result.all_present is True

    def test_contains_keywords_threshold_at_exact_value(self) -> None:
        """Verdict passes when recall equals the threshold exactly."""
        e = contains_keywords(keywords=["alpha", "beta"], min_recall=0.5)
        result = e.run(self._make_ctx("only alpha here"))
        assert result.recall == 0.5
        assert result.all_present is True

    def test_contains_keywords_threshold_just_below(self) -> None:
        """Verdict fails when recall is below the threshold."""
        e = contains_keywords(keywords=["alpha", "beta", "gamma"], min_recall=0.5)
        result = e.run(self._make_ctx("only alpha"))
        assert abs(result.recall - 1 / 3) < 1e-9
        assert result.all_present is False

    def test_contains_expected(self) -> None:
        e = contains_expected
        assert e.run(self._make_ctx("Hello World", "world")) is True
        assert e.run(self._make_ctx("Hello", "world")) is False

    def test_does_not_contain(self) -> None:
        e = does_not_contain(forbidden=["cat", "dog"])
        assert e.run(self._make_ctx("Yorkshire")).ok is True
        assert e.run(self._make_ctx("I like cats")).ok is False

    def test_not_empty(self) -> None:
        assert not_empty.run(self._make_ctx("hello")) is True
        assert not_empty.run(self._make_ctx("")) is False
        assert not_empty.run(self._make_ctx("   ")) is False

    def test_not_empty_handles_sized_containers(self) -> None:
        """Sized containers: empty -> False, non-empty -> True.

        Earlier behavior fell through to `return True` for any non-string,
        so `not_empty([])` reported True — misleading for tasks that return
        lists/dicts (e.g. tool calls, retrieved chunks).
        """
        # Helper accepts Any at runtime; type hint is just a default.
        ctx_empty_list: Any = self._make_ctx("")
        ctx_empty_list.output = []
        assert not_empty.run(ctx_empty_list) is False

        ctx_nonempty_list: Any = self._make_ctx("")
        ctx_nonempty_list.output = [1, 2]
        assert not_empty.run(ctx_nonempty_list) is True

        ctx_empty_dict: Any = self._make_ctx("")
        ctx_empty_dict.output = {}
        assert not_empty.run(ctx_empty_dict) is False

        ctx_nonempty_dict: Any = self._make_ctx("")
        ctx_nonempty_dict.output = {"a": 1}
        assert not_empty.run(ctx_nonempty_dict) is True

        ctx_empty_set: Any = self._make_ctx("")
        ctx_empty_set.output = set()
        assert not_empty.run(ctx_empty_set) is False

    def test_not_empty_unsized_objects_still_pass(self) -> None:
        """Non-Sized values (int, float, dataclass): always True (kept as-is)."""
        ctx_int: Any = self._make_ctx("")
        ctx_int.output = 42
        assert not_empty.run(ctx_int) is True

        ctx_zero: Any = self._make_ctx("")
        ctx_zero.output = 0  # 0 is not None, not Sized — still passes.
        assert not_empty.run(ctx_zero) is True

    def test_max_length(self) -> None:
        e = max_length(max_chars=5)
        result = e.run(self._make_ctx("hi"))
        assert result.within_limit is True
        result = e.run(self._make_ctx("this is too long"))
        assert result.within_limit is False

    def test_min_length(self) -> None:
        assert min_length(min_chars=3).run(self._make_ctx("hello")) is True
        assert min_length(min_chars=10).run(self._make_ctx("hi")) is False

    def test_matches_regex(self) -> None:
        e = matches_regex(pattern=r"\d{3}-\d{4}")
        assert e.run(self._make_ctx("Call 555-1234")) is True
        assert e.run(self._make_ctx("no numbers")) is False

    def test_json_valid(self) -> None:
        e = json_valid(required_keys=["name"])
        result = e.run(self._make_ctx('{"name": "Rex"}'))
        assert result.valid is True
        assert result.has_required_keys is True
        result = e.run(self._make_ctx("not json"))
        assert result.valid is False

    def test_word_overlap(self) -> None:
        e = word_overlap
        assert e.run(self._make_ctx("hello world", "hello world")).overlap == 1.0
        assert e.run(self._make_ctx("hello there", "hello world")).overlap == 0.5
        assert e.run(self._make_ctx("foo", "hello world")).overlap == 0.0


# ---------------------------------------------------------------------------
# Scoring v2: bool verdict, tracking-only metrics
# ---------------------------------------------------------------------------


class TestScoringV2:
    """Scoring v2: evaluators return bool or dataclass."""

    def test_bool_evaluator_pass(self) -> None:
        """Evaluator returning True -> case passes."""
        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                results.append(result)

            def on_test_fail(self, result: Any) -> None:
                results.append(result)

        single_case = ForEach(
            [
                EvalCase(inputs="hello world", expected="hello", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()
        session.register_plugin(Collector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[not_empty])
        def eval_echo(case: Annotated[EvalCase, From(single_case)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        assert len(results) == 1
        assert results[0].eval_payload.scores["not_empty"].value is True

    def test_dataclass_without_bool_is_tracking_only(self) -> None:
        """Dataclass with only float fields -> tracking-only, always passes."""
        results: list[Any] = []

        class Collector(PluginBase):
            name = "collector"

            def on_test_pass(self, result: Any) -> None:
                results.append(result)

            def on_test_fail(self, result: Any) -> None:
                results.append(result)

        single_case = ForEach(
            [
                EvalCase(inputs="foo", expected="bar baz", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()
        session.register_plugin(Collector())

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[word_overlap])
        def eval_echo(case: Annotated[EvalCase, From(single_case)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()

        # word_overlap returns only float -> tracking-only, always passes
        assert result.success is True

    def test_float_return_annotation_raises_at_decoration(self) -> None:
        """`-> float` is rejected by @evaluator itself — the return annotation
        is the score contract and must be bool or a dataclass."""
        with pytest.raises(TypeError, match="bool or a dataclass"):

            @evaluator
            def bad_evaluator(ctx: EvalContext) -> float:
                return 0.5

    def test_missing_return_annotation_raises_at_decoration(self) -> None:
        with pytest.raises(TypeError, match="bool or a dataclass"):

            @evaluator
            def unannotated(ctx: EvalContext):
                return True

    def test_optional_return_annotation_raises_at_decoration(self) -> None:
        with pytest.raises(TypeError, match="bool or a dataclass"):

            @evaluator
            def maybe(ctx: EvalContext) -> FakeAccuracyResult | None:
                return None

    def test_unresolvable_return_annotation_raises_at_decoration(self) -> None:
        """A function-local dataclass can't be resolved by get_type_hints —
        the placeholder keys would silently diverge from the real run."""

        @dataclass
        class LocalShape:
            ok: Annotated[bool, Verdict]

        with pytest.raises(TypeError, match="cannot be resolved"):

            @evaluator
            def local_shape(ctx: EvalContext) -> LocalShape:
                return LocalShape(ok=True)


class TestShortCircuit:
    """ShortCircuit: skip expensive evaluators when cheap ones fail."""

    def test_short_circuit_skips_on_fail(self) -> None:
        call_log: list[str] = []

        @evaluator
        def cheap(ctx: EvalContext) -> bool:
            call_log.append("cheap")
            return "hello" in ctx.output.lower()

        @evaluator
        def expensive(ctx: EvalContext) -> bool:
            call_log.append("expensive")
            return True

        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[ShortCircuit([cheap, expensive])])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()

        # case_pass: cheap ✓ → expensive ✓ (both called)
        # case_fail: cheap ✗ → expensive SKIPPED
        assert call_log.count("cheap") == 2
        assert call_log.count("expensive") == 1

    def test_short_circuit_all_pass(self) -> None:
        call_log: list[str] = []

        @evaluator
        def check_a(ctx: EvalContext) -> bool:
            call_log.append("a")
            return True

        @evaluator
        def check_b(ctx: EvalContext) -> bool:
            call_log.append("b")
            return True

        single = ForEach(
            [EvalCase(inputs="x", expected="x", name="c1")], ids=lambda c: c.name
        )
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[ShortCircuit([check_a, check_b])])
        def eval_echo(case: Annotated[EvalCase, From(single)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()

        assert result.success is True
        assert call_log == ["a", "b"]


# ---------------------------------------------------------------------------
# Results files per run
# ---------------------------------------------------------------------------


class TestResultsFiles:
    """Per-case markdown files written to .protest/results/<suite>_<ts>/."""

    def _run_eval(self, tmp_path: Path) -> Path:
        results_dir = tmp_path / "results"
        session = ProTestSession()
        writer = EvalResultsWriter(history_dir=tmp_path)
        session.register_plugin(writer)

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        runner.run()
        return results_dir

    def test_results_dir_created(self, tmp_path: Path) -> None:
        results_dir = self._run_eval(tmp_path)
        assert results_dir.exists()

    def test_one_file_per_case(self, tmp_path: Path) -> None:
        results_dir = self._run_eval(tmp_path)
        run_dirs = list(results_dir.iterdir())
        assert len(run_dirs) == 1
        case_files = list(run_dirs[0].iterdir())
        assert len(case_files) == 2  # case_pass + case_fail

    def test_case_file_contains_output(self, tmp_path: Path) -> None:
        results_dir = self._run_eval(tmp_path)
        run_dir = next(results_dir.iterdir())
        pass_file = next(f for f in run_dir.iterdir() if "pass" in f.name)
        content = pass_file.read_text()
        assert "Echo:" in content  # task output
        assert "PASS" in content

    def test_case_file_contains_scores(self, tmp_path: Path) -> None:
        results_dir = self._run_eval(tmp_path)
        run_dir = next(results_dir.iterdir())
        pass_file = next(f for f in run_dir.iterdir() if "pass" in f.name)
        content = pass_file.read_text()
        assert "accuracy" in content

    def test_case_file_contains_inputs(self, tmp_path: Path) -> None:
        results_dir = self._run_eval(tmp_path)
        run_dir = next(results_dir.iterdir())
        pass_file = next(f for f in run_dir.iterdir() if "pass" in f.name)
        content = pass_file.read_text()
        assert "hello world" in content  # from case inputs


# ---------------------------------------------------------------------------
# Multi-dataset history (regression: all suites were merged under one name)
# ---------------------------------------------------------------------------


class TestMultiDatasetHistory:
    """Multiple EvalSuite + @suite.eval calls produce distinct suites in history."""

    def _run_multi(self, tmp_path: Path) -> dict[str, Any]:
        pipeline_cases = ForEach(
            [
                EvalCase(inputs="hello", expected="hello", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        ingest_cases = ForEach(
            [
                EvalCase(inputs="world", expected="world", name="c2"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession(history_dir=tmp_path)

        pipeline_suite = EvalSuite("pipeline")
        session.add_suite(pipeline_suite)

        @pipeline_suite.eval(evaluators=[fake_accuracy])
        def pipeline(case: Annotated[EvalCase, From(pipeline_cases)]) -> str:
            return echo_task(case.inputs)

        ingest_suite = EvalSuite("ingest")
        session.add_suite(ingest_suite)

        @ingest_suite.eval(evaluators=[fake_accuracy])
        def ingest(case: Annotated[EvalCase, From(ingest_cases)]) -> str:
            return echo_task(case.inputs)

        run_session(session)

        history = (tmp_path / "history.jsonl").read_text().splitlines()
        return json.loads(history[-1])

    def test_two_datasets_produce_two_suites_in_history(self, tmp_path: Path) -> None:
        entry = self._run_multi(tmp_path)
        assert "pipeline" in entry["suites"]
        assert "ingest" in entry["suites"]

    def test_each_suite_has_its_own_cases(self, tmp_path: Path) -> None:
        entry = self._run_multi(tmp_path)
        assert "c1" in entry["suites"]["pipeline"]["cases"]
        assert "c2" in entry["suites"]["ingest"]["cases"]


# ---------------------------------------------------------------------------
# DI fixture injection dans les taches eval
# ---------------------------------------------------------------------------


class TestEvalTaskFixtures:
    """EvalSuite + @suite.eval() peut utiliser des fixtures protest via Use()."""

    def test_task_without_fixtures_still_works(self) -> None:
        # basic_cases has one match (case_pass) and one mismatch (case_fail)
        # fake_accuracy returns matches_expected=False for case_fail -> fail
        session = ProTestSession()

        eval_echo_suite = EvalSuite("eval_echo")
        session.add_suite(eval_echo_suite)

        @eval_echo_suite.eval(evaluators=[fake_accuracy])
        def eval_echo(case: Annotated[EvalCase, From(basic_cases)]) -> str:
            return echo_task(case.inputs)

        runner = TestRunner(session)
        result = runner.run()
        assert result.success is False  # case_fail has matches_expected=False

    def test_task_with_session_fixture_is_injected(self) -> None:
        """Une fixture session-scoped est injectee dans task via Use()."""

        @fixture()
        def prefix_service() -> str:
            return "PREFIX"

        single_case = ForEach(
            [
                EvalCase(inputs="hello", expected="PREFIX:hello", name="c1"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()
        session.bind(prefix_service)

        eval_prefixed_suite = EvalSuite("eval_prefixed")
        session.add_suite(eval_prefixed_suite)

        @eval_prefixed_suite.eval(evaluators=[fake_accuracy])
        async def eval_prefixed(
            case: Annotated[EvalCase, From(single_case)],
            svc: Annotated[str, Use(prefix_service)],
        ) -> str:
            return f"{svc}:{case.inputs}"

        runner = TestRunner(session)
        result = runner.run()

        # fake_accuracy retourne 1.0 (output contient expected) -> passe
        assert result.success is True

    def test_session_fixture_resolved_once_for_all_cases(self) -> None:
        """Une session fixture ne doit etre appelee qu'une fois meme avec N cas."""
        call_count = 0

        @fixture()
        def expensive_resource() -> str:
            nonlocal call_count
            call_count += 1
            return "resource"

        multi_cases = ForEach(
            [
                EvalCase(inputs="a", expected="resource:a", name="c1"),
                EvalCase(inputs="b", expected="resource:b", name="c2"),
                EvalCase(inputs="c", expected="resource:c", name="c3"),
            ],
            ids=lambda c: c.name,
        )

        session = ProTestSession()
        session.bind(expensive_resource)

        eval_resource_suite = EvalSuite("eval_resource")
        session.add_suite(eval_resource_suite)

        @eval_resource_suite.eval(evaluators=[fake_accuracy])
        async def eval_resource(
            case: Annotated[EvalCase, From(multi_cases)],
            res: Annotated[str, Use(expensive_resource)],
        ) -> str:
            return f"{res}:{case.inputs}"

        runner = TestRunner(session)
        runner.run()

        assert call_count == 1  # fixture resolue une seule fois
