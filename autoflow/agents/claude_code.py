"""
Claude Code CLI Adapter

Provides integration with Anthropic's Claude Code CLI tool.
Supports native session resume via the -r flag.

Usage:
    from autoflow.agents.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter()
    result = await adapter.execute(
        prompt="Fix the bug in app.py",
        workdir="/path/to/project",
        config=AgentConfig(command="claude")
    )
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from autoflow.agents.base import (
    AgentAdapter,
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)


class ClaudeCodeAdapter(AgentAdapter):
    """
    Adapter for Claude Code CLI.

    Wraps the 'claude' command-line tool and provides:
    - Async execution with timeout handling
    - Native session resume support
    - Output capture and status reporting

    The Claude Code CLI supports session resume via the -r flag,
    allowing continuation of previous conversations.

    Attributes:
        DEFAULT_COMMAND: Default command to invoke Claude Code
        DEFAULT_ARGS: Default arguments (--print for non-interactive mode)
        DEFAULT_TIMEOUT: Default execution timeout in seconds
    """

    DEFAULT_COMMAND: str = "claude"
    DEFAULT_ARGS: list[str] = ["--print"]
    DEFAULT_TIMEOUT: int = 300

    def __init__(
        self,
        command: str | None = None,
        default_args: list[str] | None = None,
        default_timeout: int | None = None,
    ) -> None:
        """
        Initialize the Claude Code adapter.

        Args:
            command: Override default claude command
            default_args: Override default arguments
            default_timeout: Override default timeout in seconds
        """
        self._command = command or self.DEFAULT_COMMAND
        self._default_args = default_args or list(self.DEFAULT_ARGS)
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT

    def get_resume_mode(self) -> ResumeMode:
        """
        Return how this agent handles resume.

        Claude Code has native resume support via the -r flag,
        which allows continuing a previous session.

        Returns:
            ResumeMode.NATIVE
        """
        return ResumeMode.NATIVE

    def _build_command(
        self,
        prompt: str,
        config: AgentConfig,
        session_id: str | None = None,
    ) -> list[str]:
        """
        Build the full command to execute.

        Args:
            prompt: The prompt to send to Claude
            config: Agent configuration
            session_id: Optional session ID for resume

        Returns:
            List of command-line arguments
        """
        cmd = [config.command or self._command]

        # Add default args from config or use instance defaults
        args = config.args if config.args else self._default_args
        cmd.extend(args)

        # Add resume flag if session ID provided
        if session_id:
            cmd.extend(["-r", session_id])

        # Add the prompt as the last argument
        cmd.append(prompt)

        return cmd

    async def execute(
        self,
        prompt: str,
        workdir: str | Path,
        config: AgentConfig,
    ) -> ExecutionResult:
        """
        Execute a task with Claude Code CLI.

        Starts a new Claude Code session and runs the given prompt.
        Returns an ExecutionResult with output and session info.

        Args:
            prompt: The task/prompt to execute
            workdir: Working directory for execution
            config: Agent configuration

        Returns:
            ExecutionResult with status, output, and session info

        Example:
            >>> adapter = ClaudeCodeAdapter()
            >>> result = await adapter.execute(
            ...     prompt="Fix the bug in app.py",
            ...     workdir="/path/to/project",
            ...     config=AgentConfig(command="claude")
            ... )
            >>> if result.success:
            ...     print(result.output)
        """
        result = ExecutionResult()

        # Ensure config has required values
        if not config.command:
            config.command = self._command
        if not config.args:
            config.args = list(self._default_args)

        # Build command
        cmd = self._build_command(prompt, config)

        # Get timeout
        timeout = config.timeout_seconds or self._default_timeout

        # Ensure workdir is a Path
        workdir_path = Path(workdir) if isinstance(workdir, str) else workdir

        try:
            # Run the command asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=config.env or None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                # Decode output
                output = stdout.decode("utf-8") if stdout else None
                error = stderr.decode("utf-8") if stderr else None

                # Determine status based on exit code
                if process.returncode == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.FAILURE

                result.mark_complete(
                    status=status,
                    exit_code=process.returncode,
                    output=output,
                    error=error,
                )

                # Try to extract session ID from output or metadata
                # Claude Code may output session info in a specific format
                # For now, we'll store the workdir as a session identifier
                result.session_id = str(workdir_path.resolve())

            except TimeoutError:
                # Kill the process on timeout
                process.kill()
                await process.wait()
                result.mark_complete(
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    error=f"Execution timed out after {timeout} seconds",
                )

        except FileNotFoundError:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Command not found: {config.command}. "
                f"Please ensure Claude Code CLI is installed.",
            )
        except Exception as e:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Execution failed: {str(e)}",
            )

        return result

    async def resume(
        self,
        session_id: str,
        new_prompt: str,
        config: AgentConfig | None = None,
    ) -> ExecutionResult:
        """
        Resume an existing session with a new prompt.

        Uses Claude Code's native -r flag to continue a previous session.

        Args:
            session_id: ID of the session to resume (typically the workdir path)
            new_prompt: New prompt to send
            config: Optional updated configuration

        Returns:
            ExecutionResult with status and output

        Raises:
            ValueError: If session_id is invalid or directory doesn't exist

        Example:
            >>> result = await adapter.resume(
            ...     session_id="/path/to/project",
            ...     new_prompt="Now add tests for that fix"
            ... )
        """
        result = ExecutionResult()

        # Validate session_id (should be a valid directory path)
        workdir = Path(session_id)
        if not workdir.exists():
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Session directory does not exist: {session_id}",
            )
            return result

        # Use provided config or create default
        if config is None:
            config = AgentConfig(
                command=self._command,
                args=list(self._default_args),
                timeout_seconds=self._default_timeout,
            )

        # Build command with resume flag
        cmd = self._build_command(new_prompt, config, session_id=session_id)

        timeout = config.timeout_seconds or self._default_timeout

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=config.env or None,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                output = stdout.decode("utf-8") if stdout else None
                error = stderr.decode("utf-8") if stderr else None

                if process.returncode == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.FAILURE

                result.mark_complete(
                    status=status,
                    exit_code=process.returncode,
                    output=output,
                    error=error,
                )
                result.session_id = session_id

            except TimeoutError:
                process.kill()
                await process.wait()
                result.mark_complete(
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    error=f"Execution timed out after {timeout} seconds",
                )

        except FileNotFoundError:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Command not found: {config.command}. "
                f"Please ensure Claude Code CLI is installed.",
            )
        except Exception as e:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Resume failed: {str(e)}",
            )

        return result

    async def check_health(self) -> bool:
        """
        Check if Claude Code CLI is available and healthy.

        Returns:
            True if claude command is available
        """
        return shutil.which(self._command) is not None

    def __repr__(self) -> str:
        """Return string representation of the adapter."""
        return (
            f"ClaudeCodeAdapter("
            f"command={self._command!r}, "
            f"resume_mode={self.get_resume_mode().value})"
        )
