"""Tests for the Shell helper."""

import asyncio
import os
import tempfile

import pytest

from protest.shell import CommandResult, Shell


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_true_when_exit_code_zero(self) -> None:
        result = CommandResult(stdout="", stderr="", exit_code=0, command="test")
        assert result.success is True

    def test_success_false_when_exit_code_nonzero(self) -> None:
        result = CommandResult(stdout="", stderr="", exit_code=1, command="test")
        assert result.success is False

    def test_output_combines_stdout_and_stderr(self) -> None:
        result = CommandResult(stdout="out", stderr="err", exit_code=0, command="test")
        assert result.output == "out\nerr"

    def test_output_only_stdout(self) -> None:
        result = CommandResult(stdout="out", stderr="", exit_code=0, command="test")
        assert result.output == "out"

    def test_output_only_stderr(self) -> None:
        result = CommandResult(stdout="", stderr="err", exit_code=0, command="test")
        assert result.output == "err"

    def test_output_empty(self) -> None:
        result = CommandResult(stdout="", stderr="", exit_code=0, command="test")
        assert result.output == ""


class TestShellRun:
    """Tests for Shell.run()."""

    @pytest.mark.asyncio
    async def test_run_string_command(self) -> None:
        result = await Shell.run("echo hello", print_output=False)

        assert result.success
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_run_list_command(self) -> None:
        result = await Shell.run(["echo", "hello"], print_output=False)

        assert result.success
        assert result.stdout.strip() == "hello"

    @pytest.mark.asyncio
    async def test_captures_stdout(self) -> None:
        result = await Shell.run("echo stdout_test", print_output=False)

        assert "stdout_test" in result.stdout

    @pytest.mark.asyncio
    async def test_captures_stderr(self) -> None:
        result = await Shell.run("echo stderr_test >&2", shell=True, print_output=False)

        assert "stderr_test" in result.stderr

    @pytest.mark.asyncio
    async def test_captures_exit_code(self) -> None:
        result = await Shell.run("exit 42", shell=True, print_output=False)

        assert result.exit_code == 42
        assert not result.success

    @pytest.mark.asyncio
    async def test_command_stored_in_result(self) -> None:
        result = await Shell.run(["echo", "test"], print_output=False)

        assert result.command == "echo test"


class TestShellMode:
    """Tests for shell=True vs shell=False behavior."""

    @pytest.mark.asyncio
    async def test_shell_true_enables_pipes(self) -> None:
        result = await Shell.run("echo hello | cat", shell=True, print_output=False)

        assert result.success
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_shell_true_enables_chaining(self) -> None:
        result = await Shell.run(
            "echo first && echo second", shell=True, print_output=False
        )

        assert result.success
        assert "first" in result.stdout
        assert "second" in result.stdout

    @pytest.mark.asyncio
    async def test_shell_false_no_metachar_interpretation(self) -> None:
        # With shell=False, && is passed as literal argument, not interpreted
        result = await Shell.run(["echo", "a && b"], print_output=False)

        assert result.success
        # The && should appear literally in output, not be interpreted
        assert "&&" in result.stdout


class TestShellOptions:
    """Tests for Shell.run() options."""

    @pytest.mark.asyncio
    async def test_timeout_raises_on_slow_command(self) -> None:
        with pytest.raises(asyncio.TimeoutError):
            await Shell.run("sleep 10", timeout=0.1, print_output=False)

    @pytest.mark.asyncio
    async def test_timeout_allows_fast_command(self) -> None:
        result = await Shell.run("echo fast", timeout=5.0, print_output=False)

        assert result.success

    @pytest.mark.asyncio
    async def test_cwd_changes_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use Python to print cwd - works on all platforms
            result = await Shell.run(
                ["python", "-c", "import os; print(os.getcwd())"],
                cwd=tmpdir,
                print_output=False,
            )

            # Resolve symlinks for macOS /var -> /private/var
            # and normalize case for Windows
            expected = os.path.normcase(os.path.realpath(tmpdir))  # noqa: ASYNC240
            actual = os.path.normcase(os.path.realpath(result.stdout.strip()))  # noqa: ASYNC240
            assert actual == expected

    @pytest.mark.asyncio
    async def test_env_sets_environment_variables(self) -> None:
        # Use Python to print env var - works on all platforms
        result = await Shell.run(
            ["python", "-c", "import os; print(os.environ.get('MY_TEST_VAR', ''))"],
            env={"MY_TEST_VAR": "test_value", "PATH": os.environ.get("PATH", "")},
            print_output=False,
        )

        assert "test_value" in result.stdout

    @pytest.mark.asyncio
    async def test_env_replaces_environment(self) -> None:
        # When env is set, it replaces the environment entirely
        # Use Python to check that HOME is not set
        result = await Shell.run(
            ["python", "-c", "import os; print(os.environ.get('HOME', 'NOT_SET'))"],
            env={"PATH": os.environ.get("PATH", "")},  # No HOME
            print_output=False,
        )

        # HOME should not be set
        assert result.stdout.strip() == "NOT_SET"

    @pytest.mark.asyncio
    async def test_print_output_false_suppresses_print(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await Shell.run("echo should_not_print", print_output=False)

        captured = capsys.readouterr()
        assert "should_not_print" not in captured.out

    @pytest.mark.asyncio
    async def test_print_output_true_prints_stdout(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await Shell.run("echo should_print", print_output=True)

        captured = capsys.readouterr()
        assert "should_print" in captured.out

    @pytest.mark.asyncio
    async def test_print_output_true_prints_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await Shell.run("echo should_print_err >&2", shell=True, print_output=True)

        captured = capsys.readouterr()
        assert "should_print_err" in captured.err


class TestShellEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_command_not_found_raises_with_shell_false(self) -> None:
        # Without shell, missing binary raises FileNotFoundError
        with pytest.raises(FileNotFoundError):
            await Shell.run("nonexistent_command_12345", print_output=False)

    @pytest.mark.asyncio
    async def test_command_not_found_returns_error_with_shell_true(self) -> None:
        # With shell, the shell handles the error and returns non-zero exit
        result = await Shell.run(
            "nonexistent_command_12345", shell=True, print_output=False
        )

        assert not result.success
        assert result.exit_code != 0

    @pytest.mark.asyncio
    async def test_empty_output(self) -> None:
        result = await Shell.run("true", print_output=False)

        assert result.success
        assert result.stdout == ""
        assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_unicode_output(self) -> None:
        result = await Shell.run(["echo", "héllo wörld"], print_output=False)

        assert "héllo wörld" in result.stdout

    @pytest.mark.asyncio
    async def test_multiline_output(self) -> None:
        # Use Python for cross-platform multiline output
        result = await Shell.run(
            ["python", "-c", "print('line1'); print('line2')"],
            print_output=False,
        )

        lines = result.stdout.strip().splitlines()
        assert len(lines) == 2
        assert lines[0] == "line1"
        assert lines[1] == "line2"

    @pytest.mark.asyncio
    async def test_quotes_in_args(self) -> None:
        result = await Shell.run(["echo", "hello 'world'"], print_output=False)

        assert "'world'" in result.stdout

    @pytest.mark.asyncio
    async def test_spaces_in_args(self) -> None:
        result = await Shell.run(["echo", "hello   world"], print_output=False)

        assert "hello   world" in result.stdout
