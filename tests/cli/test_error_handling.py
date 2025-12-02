from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.cli.conftest import CLIResult


class TestInvalidTarget:
    def test_invalid_target_format_missing_colon(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("run", "invalid_target_no_colon")
        result.assert_failure()

    def test_module_not_found(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "nonexistent_module:session")
        result.assert_failure()

    def test_session_not_found(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("run", "simple_session:nonexistent_session")
        result.assert_failure()


class TestUnknownCommand:
    def test_unknown_command(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("unknown_command")
        result.assert_failure()

    def test_no_command_shows_usage(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest()
        assert result.exit_code in (0, 1)
