"""Shell helper for running subprocesses in tests.

Provides isolated, async-safe subprocess execution with captured output.
Use this for CLI/integration tests where you need to capture subprocess output.

Example:
    @suite.test()
    async def test_cli():
        result = await Shell.run("my-app --version")
        assert result.exit_code == 0
        assert "1.0.0" in result.stdout
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of a shell command execution."""

    stdout: str
    stderr: str
    exit_code: int
    command: str

    @property
    def success(self) -> bool:
        """True if exit code is 0."""
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(self.stderr)
        return "\n".join(parts)


class Shell:
    """Async shell command runner with isolated output capture.

    Uses asyncio.create_subprocess_exec with dedicated pipes,
    ensuring thread-safe capture even in concurrent tests.

    Example:
        result = await Shell.run("echo hello")
        assert result.stdout == "hello\\n"

        # With args as list
        result = await Shell.run(["ls", "-la"])

        # Check success
        result = await Shell.run("false")
        assert not result.success

        # Timeout
        result = await Shell.run("sleep 10", timeout=1.0)  # Raises TimeoutError
    """

    @staticmethod
    async def run(
        command: str | list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        print_output: bool = True,
        shell: bool = False,
    ) -> CommandResult:
        """Run a shell command and return the result.

        Args:
            command: Command string or list of args.
            timeout: Optional timeout in seconds.
            cwd: Working directory for the command.
            env: Environment variables (replaces current env if set).
            print_output: If True, print stdout/stderr for test capture.
            shell: If True, run through shell (supports pipes, &&, etc).

        Returns:
            CommandResult with stdout, stderr, exit_code.

        Raises:
            asyncio.TimeoutError: If timeout is exceeded.
        """
        if shell:
            if isinstance(command, list):
                command_str = shlex.join(command)
            else:
                command_str = command
            process = await asyncio.create_subprocess_shell(
                command_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        else:
            if isinstance(command, str):
                args = shlex.split(command)
            else:
                args = list(command)
            command_str = shlex.join(args)
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = process.returncode or 0

        # Print output so it gets captured by ProTest's TaskAwareStream
        if print_output:
            if stdout:
                print(stdout, end="")
            if stderr:
                import sys

                print(stderr, end="", file=sys.stderr)

        return CommandResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            command=command_str,
        )

    @staticmethod
    async def run_ok(
        command: str | list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        print_output: bool = True,
        shell: bool = False,
    ) -> CommandResult:
        """Run a command and assert it succeeds (exit code 0).

        Same as run() but raises AssertionError if exit code != 0.
        """
        result = await Shell.run(
            command,
            timeout=timeout,
            cwd=cwd,
            env=env,
            print_output=print_output,
            shell=shell,
        )
        if not result.success:
            raise AssertionError(
                f"Command failed with exit code {result.exit_code}: {result.command}\n"
                f"stderr: {result.stderr}"
            )
        return result
