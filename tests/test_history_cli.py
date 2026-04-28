"""Tests for `protest history` CLI argument parsing.

The CLI uses sub-commands (`list`, `runs`, `show`, `compare`, `clean`).
`list` is the implicit default when no sub-command is given. Each sub-command
shares a common filter parser (`--tail`, `--model`, `--suite`, `--evals`/
`--tests`, `--path`); `--evals` and `--tests` remain mutually exclusive.

`handle_history_command(argv)` triggers `SystemExit(2)` from argparse on a
parsing error, and `SystemExit(0)` on a clean (possibly empty-history) run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from protest.cli.history import handle_history_command
from protest.history.storage import HISTORY_FILE, append_entry

if TYPE_CHECKING:
    from pathlib import Path


class TestKindMutex:
    """`--evals` and `--tests` cannot be combined within a sub-command."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["list", "--evals", "--tests"],
            ["runs", "--tests", "--evals"],
        ],
    )
    def test_mutex_violation_exits_with_error(
        self,
        argv: list[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(argv)
        assert exc_info.value.code == 2
        stderr = capsys.readouterr().err
        assert "not allowed with argument" in stderr


class TestSubcommandsAccepted:
    """Each sub-command parses cleanly with shared filters."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["list"],
            ["runs"],
            ["show"],
            ["show", "0"],
            ["compare"],
            ["clean"],
            ["list", "--evals"],
            ["list", "--tests"],
            ["runs", "--tail", "5"],
            ["show", "1", "--model", "gpt-4"],
            ["compare", "--suite", "my_suite"],
        ],
    )
    def test_subcommand_parses_with_empty_history(
        self,
        argv: list[str],
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        full_argv = [*argv, "--path", str(tmp_path)]
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(full_argv)
        # Empty history exits 0 with "No history found." (or similar).
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "not allowed with argument" not in captured.err


class TestImplicitListDefault:
    """`protest history` with no sub-command falls back to `list`."""

    def test_no_subcommand_runs_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["--path", str(tmp_path)])
        assert exc_info.value.code == 0

    def test_no_subcommand_with_only_filter_runs_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # `protest history --tail 5 --path X` should be parsed as the
        # implicit `list --tail 5 --path X`, not as a parser error.
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["--tail", "5", "--path", str(tmp_path)])
        assert exc_info.value.code == 0


class TestHelpOutput:
    """`--help` lists the sub-commands."""

    def test_help_lists_subcommands(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["--help"])
        assert exc_info.value.code == 0
        stdout = capsys.readouterr().out
        for cmd in ("list", "runs", "show", "compare", "clean"):
            assert cmd in stdout


class TestRunsOrderRecentFirst:
    """`runs` lists most-recent run first (git log convention).

    Storage returns entries oldest→newest; the CLI must reverse for display
    so #1 maps to the newest run, matching `git stash list` / `git log`.
    """

    def _seed(self, tmp_path: Path, commits: list[tuple[str, str]]) -> None:
        path = tmp_path / HISTORY_FILE
        for ts, commit in commits:
            append_entry(
                path,
                {
                    "schema_version": 1,
                    "run_id": commit,
                    "timestamp": ts,
                    "git": {"commit_short": commit},
                    "suites": {},
                },
            )

    def test_runs_displays_newest_first(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Seed in chronological order — storage preserves write order.
        self._seed(
            tmp_path,
            [
                ("2026-04-25T10:00:00", "old1234"),
                ("2026-04-25T11:00:00", "mid5678"),
                ("2026-04-25T12:00:00", "newabcd"),
            ],
        )
        handle_history_command(["runs", "--path", str(tmp_path)])
        stdout = capsys.readouterr().out
        # #1 is newest, #3 is oldest.
        assert stdout.index("#1") < stdout.index("#2") < stdout.index("#3")
        assert (
            stdout.index("newabcd") < stdout.index("mid5678") < stdout.index("old1234")
        )
        # And #1 lines up with the newest commit, not the oldest.
        newest_line = next(line for line in stdout.splitlines() if "#1" in line)
        assert "newabcd" in newest_line


class TestCompareRefusesMixedModels:
    """`compare` must not silently diff across models — would cause false regressions.

    When the two most recent runs each contain suites with several distinct
    `ModelLabel.name`s (e.g. `rules_v1` + `rules_v2` in a multi-model
    session), aplatting the cases by name conflates contexts: a case-id that
    passes under one model and fails under the other shows up as a phantom
    regression. The CLI rejects this and asks the user to disambiguate via
    `--model NAME` or `--suite NAME`.
    """

    def _seed_two_model_run(self, tmp_path: Path, run_id: str, ts: str) -> None:
        path = tmp_path / HISTORY_FILE
        append_entry(
            path,
            {
                "schema_version": 1,
                "run_id": run_id,
                "timestamp": ts,
                "git": {"commit_short": run_id},
                "suites": {
                    "helpdesk_v1": {
                        "kind": "eval",
                        "model": "rules_v1",
                        "passed": 9,
                        "total_cases": 18,
                        "cases": {"T010": {"passed": False, "case_hash": "h1"}},
                    },
                    "helpdesk_v2": {
                        "kind": "eval",
                        "model": "rules_v2",
                        "passed": 11,
                        "total_cases": 18,
                        "cases": {"T010": {"passed": True, "case_hash": "h1"}},
                    },
                },
            },
        )

    def test_compare_rejects_mixed_models_without_filter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._seed_two_model_run(tmp_path, "aaa1111", "2026-04-27T10:00:00")
        self._seed_two_model_run(tmp_path, "bbb2222", "2026-04-27T11:00:00")
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["compare", "--evals", "--path", str(tmp_path)])
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "multiple models" in out
        assert "rules_v1" in out and "rules_v2" in out
        assert "--model" in out

    def test_compare_with_model_filter_succeeds(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._seed_two_model_run(tmp_path, "aaa1111", "2026-04-27T10:00:00")
        self._seed_two_model_run(tmp_path, "bbb2222", "2026-04-27T11:00:00")
        # `--model rules_v1` prunes helpdesk_v2 out of each entry, leaving
        # a single-model comparison that should succeed (no false regression).
        handle_history_command(
            ["compare", "--evals", "--model", "rules_v1", "--path", str(tmp_path)]
        )
        out = capsys.readouterr().out
        assert "multiple models" not in out


class TestCleanDryRun:
    """`clean` is dry-run by default; `--apply` to actually modify the file."""

    def test_clean_default_is_dry_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Empty history is the simplest case — both modes should report
        # "No dirty entries to clean." without touching anything.
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["clean", "--path", str(tmp_path)])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "No dirty entries to clean." in out

    def test_clean_apply_flag_accepted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            handle_history_command(["clean", "--apply", "--path", str(tmp_path)])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "No dirty entries to clean." in out
