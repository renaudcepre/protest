"""Shell helper for running subprocesses in tests.

Provides isolated, async-safe subprocess execution with captured output.
Use this for CLI/integration tests where you need to capture subprocess output.

Security: When using shell=True, only literal strings are accepted to prevent
command injection. Dynamic strings (f-strings with variables) will be rejected
by type checkers.

Example:
    @suite.test()
    async def test_cli():
        result = await Shell.run("my-app --version")
        assert result.exit_code == 0
        assert "1.0.0" in result.stdout

    # Shell features (pipes, &&) require shell=True
    result = await Shell.run("echo hello && echo world", shell=True)
"""

from __future__ import annotations

import asyncio
import shlex
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, overload

if TYPE_CHECKING:
    from protest.compat import LiteralString


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

    Security:
        When shell=True, only literal strings are accepted to prevent injection.
        Type checkers (mypy, pyright) will reject dynamic strings like f-strings.

    Example:
        # Safe: list of args (no shell interpretation)
        result = await Shell.run(["ls", "-la"])

        # Safe: literal string without shell
        result = await Shell.run("echo hello")

        # Safe: literal string WITH shell (for pipes, &&, etc)
        result = await Shell.run("echo hello && echo world", shell=True)

        # UNSAFE - Type checker will reject this:
        user_input = get_user_input()
        result = await Shell.run(f"echo {user_input}", shell=True)  # Error!
    """

    # Overload 1: list[str] command - always safe, shell param ignored
    @overload
    @staticmethod
    async def run(
        command: list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        print_output: bool = True,
        shell: bool = False,
    ) -> CommandResult: ...

    # Overload 2: str command without shell - safe
    @overload
    @staticmethod
    async def run(
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        print_output: bool = True,
        shell: Literal[False] = False,
    ) -> CommandResult: ...

    # Overload 3: str command WITH shell - must be LiteralString
    @overload
    @staticmethod
    async def run(
        command: LiteralString,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        print_output: bool = True,
        shell: Literal[True],
    ) -> CommandResult: ...

    @staticmethod
    async def run(  # noqa: PLR0913
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
                   When True, command must be a literal string for security.

        Returns:
            CommandResult with stdout, stderr, exit_code.

        Raises:
            asyncio.TimeoutError: If timeout is exceeded.

        Security:
            When shell=True, only literal strings (not f-strings with variables)
            are accepted. This prevents command injection attacks. Type checkers
            will reject dynamic strings at development time.
        """
        if shell:
            command_str = shlex.join(command) if isinstance(command, list) else command
            process = await asyncio.create_subprocess_shell(
                command_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        else:
            args = shlex.split(command) if isinstance(command, str) else list(command)
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
                print(stdout, end="")  # noqa: T201
            if stderr:
                print(stderr, end="", file=sys.stderr)  # noqa: T201

        return CommandResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            command=command_str,
        )
