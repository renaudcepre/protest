"""Symmetry tests between RichReporter and AsciiReporter.

Goal: catch divergences between the two reporters before they ship as silent
asymmetries. A user who swaps `--no-color` should get the same *semantic*
output (same fields, same filters) — only the visual style differs.

Three axes are enforced:

1. Structural  — both reporters expose the same public hooks (`on_*` handlers).
2. CLI         — both reporters react to the same shared flags (`--show-output`,
                 `--show-logs`). Reporter-specific flags (`--no-color`) are allowed.
3. Behavioral  — parametrized scenarios drive the same input through both
                 reporters and assert the same *semantic* markers appear
                 (score names for eval pass, eval detail on fail, summary omits
                 eval failures, etc.).
"""

from __future__ import annotations

import argparse
import inspect
import logging
from typing import Any

import pytest

from protest.entities import (
    EvalPayload,
    EvalScoreEntry,
    SessionResult,
    TestResult,
)
from protest.plugin import PluginBase, PluginContext
from protest.reporting.ascii import AsciiReporter
from protest.reporting.rich_reporter import RichReporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPORTER_CLASSES = [RichReporter, AsciiReporter]

# CLI flags that are handled by the shared run-parser (not by either reporter's
# add_cli_options). Both reporters must still read them via their activate().
_SHARED_CLI_FLAGS = {"show_output", "show_logs"}


def _public_handlers(cls: type[PluginBase]) -> set[str]:
    """Return the set of `on_*` handlers defined or overridden on cls.

    Only include methods that are *actually overridden* (not inherited from
    PluginBase as no-ops). That's what makes the reporter visible to the bus.
    """
    handlers: set[str] = set()
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if not name.startswith("on_"):
            continue
        # Skip no-op base implementations that a subclass didn't override.
        base_member = getattr(PluginBase, name, None)
        if base_member is not None and member is base_member:
            continue
        handlers.add(name)
    return handlers


def _cli_flag_dests(cls: type[PluginBase]) -> set[str]:
    """Return the argparse `dest` names registered by cls.add_cli_options."""
    parser = argparse.ArgumentParser()
    cls.add_cli_options(parser)
    dests: set[str] = set()
    for action in parser._actions:
        if action.dest and action.dest != "help":
            dests.add(action.dest)
    return dests


def _make_reporter(cls: type[PluginBase], **kwargs: Any) -> PluginBase:
    """Activate a reporter via its own activate() path to exercise wiring."""
    ctx_args = {"no_color": cls is AsciiReporter, "verbosity": 1, **kwargs}
    ctx = PluginContext(args=ctx_args)
    instance = cls.activate(ctx)
    assert instance is not None, f"{cls.__name__}.activate returned None"
    return instance


def _capture_output(capsys: pytest.CaptureFixture[str]) -> str:
    """Capture everything captured so far on stdout+stderr.

    Rich writes via `self.console` (stdout by default), Ascii uses `print`.
    Capsys grabs both uniformly.
    """
    captured = capsys.readouterr()
    return captured.out + captured.err


@pytest.fixture
def eval_result_pass() -> TestResult:
    """A passing eval TestResult with two scores (one bool, one float)."""
    return TestResult(
        name="case_alpha",
        node_id="mod::chatbot::case_alpha",
        duration=0.05,
        is_eval=True,
        eval_payload=EvalPayload(
            case_name="case_alpha",
            passed=True,
            task_duration=0.05,
            inputs="hello",
            output="world",
            expected_output="world",
            scores={
                "contains_world": EvalScoreEntry(value=True, passed=True),
                "similarity": EvalScoreEntry(value=0.92, passed=True),
            },
        ),
    )


@pytest.fixture
def eval_result_fail() -> TestResult:
    """A failing eval TestResult (one score fails)."""
    return TestResult(
        name="case_beta",
        node_id="mod::chatbot::case_beta",
        duration=0.04,
        error=AssertionError("score contains_hi failed"),
        is_eval=True,
        eval_payload=EvalPayload(
            case_name="case_beta",
            passed=False,
            task_duration=0.04,
            inputs="goodbye",
            output="farewell",
            expected_output="hi",
            scores={
                "contains_hi": EvalScoreEntry(value=False, passed=False),
            },
        ),
    )


@pytest.fixture
def plain_failing_test() -> TestResult:
    return TestResult(
        name="test_plain_fail",
        node_id="mod::test_plain_fail",
        duration=0.01,
        error=AssertionError("plain failure"),
    )


# ---------------------------------------------------------------------------
# 1. Structural symmetry
# ---------------------------------------------------------------------------


class TestStructuralSymmetry:
    """Ensure the two reporters expose the same public handler surface."""

    def test_reporters_override_same_handlers(self) -> None:
        """Both reporters override the same set of on_* methods.

        If one reporter starts overriding a hook that the other ignores, an
        event will be invisible in the "other" reporter — that's the bug we
        want to catch at test time, not in production.
        """
        rich_handlers = _public_handlers(RichReporter)
        ascii_handlers = _public_handlers(AsciiReporter)

        only_in_rich = rich_handlers - ascii_handlers
        only_in_ascii = ascii_handlers - rich_handlers
        assert not only_in_rich, (
            f"Rich handles events that Ascii doesn't: {sorted(only_in_rich)}"
        )
        assert not only_in_ascii, (
            f"Ascii handles events that Rich doesn't: {sorted(only_in_ascii)}"
        )


# ---------------------------------------------------------------------------
# 2. CLI symmetry
# ---------------------------------------------------------------------------


class TestCliSymmetry:
    """Ensure the two reporters consume the same shared flags.

    Reporter-specific flags are allowed (e.g. `--no-color` makes sense only on
    the Ascii side) — they're expected to appear in either one but not both.
    The rule is: anything in `_SHARED_CLI_FLAGS` must be *activatable* on both
    reporters (read from PluginContext via activate()).
    """

    @pytest.mark.parametrize(
        "flag,value,attr",
        [
            pytest.param("show_output", True, "_show_output", id="show_output"),
            pytest.param("show_logs", "INFO", "_show_logs", id="show_logs"),
        ],
    )
    def test_shared_flags_reach_both_reporters(
        self, flag: str, value: Any, attr: str
    ) -> None:
        """Given a shared run-parser flag, both reporters pick it up via activate()."""
        for cls in REPORTER_CLASSES:
            reporter = _make_reporter(cls, **{flag: value})
            assert getattr(reporter, attr) == value, (
                f"{cls.__name__} didn't wire flag '{flag}' into attr '{attr}'"
            )

    def test_reporters_dont_redeclare_shared_flags(self) -> None:
        """Shared flags live on the run-parser, not on reporter add_cli_options.

        If either reporter redeclares them via add_cli_options, argparse will
        raise at runtime when both get wired (cli/main.py iterates plugin
        classes and calls add_cli_options on each).
        """
        for cls in REPORTER_CLASSES:
            dests = _cli_flag_dests(cls)
            redeclared = dests & _SHARED_CLI_FLAGS
            assert not redeclared, (
                f"{cls.__name__}.add_cli_options redeclares shared flags: "
                f"{sorted(redeclared)} — move them to cli._create_run_parser"
            )


# ---------------------------------------------------------------------------
# 3. Behavioral symmetry
# ---------------------------------------------------------------------------


class TestBehavioralSymmetry:
    """Drive the same events through both reporters; assert same semantics.

    We deliberately avoid asserting on *exact* characters: the visual prefix
    differs (`✓` vs `OK`, colors vs plain). What must be identical is which
    pieces of information are rendered.
    """

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_eval_pass_shows_score_names_inline(
        self,
        reporter_cls: type[PluginBase],
        eval_result_pass: TestResult,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given a passing eval, both reporters surface each score's name inline."""
        reporter = _make_reporter(reporter_cls, verbosity=1)
        reporter.on_test_pass(eval_result_pass)
        output = _capture_output(capsys)
        assert "contains_world" in output, (
            f"{reporter_cls.__name__}: missing score name"
        )
        assert "similarity" in output, f"{reporter_cls.__name__}: missing float score"

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_eval_fail_shows_detail_inline(
        self,
        reporter_cls: type[PluginBase],
        eval_result_fail: TestResult,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given a failing eval, both reporters dump inputs/output/expected.

        This must happen regardless of --show-output — the user can't debug
        a failed assertion without seeing what the task actually produced.
        """
        reporter = _make_reporter(reporter_cls)
        reporter.on_test_fail(eval_result_fail)
        output = _capture_output(capsys)
        assert "goodbye" in output, f"{reporter_cls.__name__}: missing inputs"
        assert "farewell" in output, f"{reporter_cls.__name__}: missing output"
        assert "hi" in output, f"{reporter_cls.__name__}: missing expected"

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_show_output_true_prints_eval_detail_on_pass(
        self,
        reporter_cls: type[PluginBase],
        eval_result_pass: TestResult,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given --show-output, both reporters print eval detail even on pass."""
        reporter = _make_reporter(reporter_cls, verbosity=1, show_output=True)
        reporter.on_test_pass(eval_result_pass)
        output = _capture_output(capsys)
        assert "hello" in output, f"{reporter_cls.__name__}: missing inputs on pass"
        assert "world" in output, f"{reporter_cls.__name__}: missing output on pass"

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_show_output_false_omits_eval_detail_on_pass(
        self,
        reporter_cls: type[PluginBase],
        eval_result_pass: TestResult,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given default --show-output, eval detail is hidden on pass."""
        reporter = _make_reporter(reporter_cls, verbosity=1, show_output=False)
        reporter.on_test_pass(eval_result_pass)
        output = _capture_output(capsys)
        # "hello" and "world" appear in the score name ("contains_world");
        # assert on a unique substring that only appears if the detail block runs.
        assert "inputs:" not in output, (
            f"{reporter_cls.__name__}: leaked eval detail without --show-output"
        )

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_failure_summary_omits_eval_failures(
        self,
        reporter_cls: type[PluginBase],
        eval_result_fail: TestResult,
        plain_failing_test: TestResult,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """End-of-session summary must not re-list eval failures.

        Eval cases are already displayed inline via on_test_fail. Re-listing
        them in the summary duplicates noise — the pattern agreed on is
        "non_eval_failures only".
        """
        reporter = _make_reporter(reporter_cls)
        reporter.on_test_fail(eval_result_fail)
        reporter.on_test_fail(plain_failing_test)
        capsys.readouterr()  # drop inline fail output

        reporter.on_session_complete(
            SessionResult(passed=0, failed=2, errors=0, duration=1.0)
        )
        summary = _capture_output(capsys)

        assert "test_plain_fail" in summary, (
            f"{reporter_cls.__name__}: summary lost the plain failure"
        )
        # The eval case name should NOT appear in the failure-summary block.
        # It may appear in the inline tally above; we only captured summary here.
        assert "case_beta" not in summary, (
            f"{reporter_cls.__name__}: summary re-lists eval failure (should be inline only)"
        )

    @pytest.mark.parametrize("reporter_cls", REPORTER_CLASSES)
    def test_show_logs_prints_captured_records(
        self,
        reporter_cls: type[PluginBase],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Given --show-logs INFO, both reporters emit the captured log records."""
        record = logging.LogRecord(
            name="mylib.module",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="captured thing",
            args=(),
            exc_info=None,
        )
        result = TestResult(
            name="test_foo",
            node_id="mod::test_foo",
            duration=0.01,
            log_records=(record,),
        )
        reporter = _make_reporter(reporter_cls, verbosity=1, show_logs="INFO")
        reporter.on_test_pass(result)
        output = _capture_output(capsys)
        assert "captured thing" in output, (
            f"{reporter_cls.__name__}: --show-logs didn't render the record"
        )
        assert "mylib.module" in output, (
            f"{reporter_cls.__name__}: --show-logs didn't render the logger name"
        )
