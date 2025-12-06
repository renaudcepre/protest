from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.cli.conftest import CLIResult


class TestRunBasic:
    def test_run_passing_session(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "simple_session:session")
        result.assert_success()
        result.assert_output_contains("passed")

    def test_run_failing_session(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "failing_session:session")
        result.assert_failure()
        result.assert_output_contains("failed")

    def test_run_collect_only(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "simple_session:session", "--collect-only")
        result.assert_success()
        result.assert_output_contains("test_passing")
        result.assert_output_contains("test_also_passing")


class TestRunConcurrency:
    def test_run_with_concurrency(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "parallel_session:session", "-n", "3")
        result.assert_success()
        assert "3/3 passed" in result.stdout


class TestRunExitFirst:
    def test_exitfirst_stops_on_first_failure(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("run", "multi_fail_session:session", "-x")
        result.assert_failure()
        assert "0/1" in result.stdout, (
            f"Expected only 1 test run with -x, got: {result.stdout}"
        )


class TestRunTagFiltering:
    def test_run_with_include_tag(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "tagged_session:session", "-t", "unit")
        result.assert_success()
        assert "2/2 passed" in result.stdout

    def test_run_with_exclude_tag(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "tagged_session:session", "--no-tag", "slow")
        result.assert_success()
        assert "3/3 passed" in result.stdout

    def test_run_with_multiple_include_tags(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("run", "tagged_session:session", "-t", "unit", "-t", "api")
        result.assert_success()
        assert "4/4 passed" in result.stdout


class TestRunLastFailed:
    def test_last_failed_reruns_only_failures(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        first_run = run_protest("run", "failing_session:session")
        first_run.assert_failure()

        second_run = run_protest("run", "failing_session:session", "--lf")
        second_run.assert_failure()
        assert "test_failing" in second_run.stdout

    def test_cache_clear_runs_all(self, run_protest: Callable[..., CLIResult]) -> None:
        run_protest("run", "failing_session:session")

        result = run_protest("run", "failing_session:session", "--cache-clear")
        result.assert_failure()
        result.assert_output_contains("test_passing")
        result.assert_output_contains("test_failing")


class TestRunCapture:
    def test_no_capture_shows_print_output(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("run", "print_session:session", "-s")
        result.assert_success()
        result.assert_output_contains("VISIBLE_OUTPUT_FROM_TEST")

    def test_capture_hides_print_output(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("run", "print_session:session")
        result.assert_success()
        assert "VISIBLE_OUTPUT_FROM_TEST" not in result.stdout


class TestRunFilterCombinations:
    """Tests combining --lf, -x, and tag filters via CLI."""

    def test_lf_with_tag_cli(self, run_protest: Callable[..., CLIResult]) -> None:
        """--lf --tag: intersection of failed and tagged tests."""
        first_run = run_protest("run", "tagged_failing_session:session")
        first_run.assert_failure()

        second_run = run_protest(
            "run", "tagged_failing_session:session", "--lf", "-t", "fast"
        )
        second_run.assert_failure()
        assert "test_fast_fail" in second_run.stdout
        assert "test_slow_fail" not in second_run.stdout

    def test_lf_with_exclude_tag_cli(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        """--lf --exclude-tag: failed tests without excluded tag."""
        first_run = run_protest("run", "tagged_failing_session:session")
        first_run.assert_failure()

        second_run = run_protest(
            "run", "tagged_failing_session:session", "--lf", "--no-tag", "slow"
        )
        second_run.assert_failure()
        assert "test_fast_fail" in second_run.stdout
        assert "test_slow_fail" not in second_run.stdout

    def test_lf_exitfirst_cli(self, run_protest: Callable[..., CLIResult]) -> None:
        """--lf -x: stop on first failure among last-failed tests."""
        first_run = run_protest("run", "tagged_failing_session:session")
        first_run.assert_failure()

        second_run = run_protest("run", "tagged_failing_session:session", "--lf", "-x")
        second_run.assert_failure()
        assert "0/1" in second_run.stdout

    def test_tag_exitfirst_cli(self, run_protest: Callable[..., CLIResult]) -> None:
        """--tag -x: stop on first failure among tagged tests."""
        result = run_protest(
            "run", "tagged_failing_session:session", "-t", "slow", "-x"
        )
        result.assert_failure()
        assert "0/1" in result.stdout

    def test_all_three_combined_cli(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        """--lf --tag -x: failed + tagged + stop on first failure."""
        first_run = run_protest("run", "tagged_failing_session:session")
        first_run.assert_failure()

        second_run = run_protest(
            "run", "tagged_failing_session:session", "--lf", "-t", "slow", "-x"
        )
        second_run.assert_failure()
        assert "0/1" in second_run.stdout
