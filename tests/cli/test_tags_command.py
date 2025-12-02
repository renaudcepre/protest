from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.cli.conftest import CLIResult


class TestTagsList:
    def test_tags_list_basic(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("tags", "list", "tagged_session:session")
        result.assert_success()
        result.assert_output_contains("unit")
        result.assert_output_contains("api")
        result.assert_output_contains("slow")

    def test_tags_list_recursive(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("tags", "list", "-r", "tagged_session:session")
        result.assert_success()
        result.assert_output_contains("test_unit")
        result.assert_output_contains("test_slow_api")


class TestTagsErrors:
    def test_tags_invalid_target_format(
        self, run_protest: Callable[..., CLIResult]
    ) -> None:
        result = run_protest("tags", "list", "invalid_target")
        result.assert_failure()

    def test_tags_module_not_found(self, run_protest: Callable[..., CLIResult]) -> None:
        result = run_protest("tags", "list", "nonexistent_module:session")
        result.assert_failure()
