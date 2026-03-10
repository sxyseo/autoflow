"""
Codex CLI Adapter

Provides integration with OpenAI's Codex CLI tool.
Uses reprompt mode for session resumption (re-sends full context).

Usage:
    from autoflow.agents.codex import CodexAdapter

    adapter = CodexAdapter()
    result = await adapter.execute(
        prompt="Fix the bug in app.py",
        workdir="/path/to/project",
        config=AgentConfig(command="codex")
    )
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from autoflow.agents.base import (
    AgentAdapter,
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)


class CodexAdapter(AgentAdapter):
    """
    Adapter for OpenAI Codex CLI.

    Wraps the 'codex' command-line tool and provides:
    - Async execution with timeout handling
    - Reprompt-based session resume (re-sends full context)
    - JSON output parsing support
    - Output capture and status reporting

    The Codex CLI does not support native session resume, so it uses
    REPROMPT mode which requires re-sending the full context when
    resuming a session.

    Attributes:
        DEFAULT_COMMAND: Default command to invoke Codex
        DEFAULT_ARGS: Default arguments (exec with JSON output)
        DEFAULT_TIMEOUT: Default execution timeout in seconds
        DEFAULT_APPROVAL_POLICY: Default approval policy for automation
        DEFAULT_SANDBOX_MODE: Default sandbox mode for file access
    """

    DEFAULT_COMMAND: str = "codex"
    DEFAULT_ARGS: list[str] = ["exec", "--json"]
    DEFAULT_TIMEOUT: int = 300
    DEFAULT_APPROVAL_POLICY: str = "never"
    DEFAULT_SANDBOX_MODE: str = "full-access"

    def __init__(
        self,
        command: str | None = None,
        default_args: list[str] | None = None,
        default_timeout: int | None = None,
        approval_policy: str | None = None,
        sandbox_mode: str | None = None,
    ) -> None:
        """
        Initialize the Codex adapter.

        Args:
            command: Override default codex command
            default_args: Override default arguments
            default_timeout: Override default timeout in seconds
            approval_policy: Override default approval policy
            sandbox_mode: Override default sandbox mode
        """
        self._command = command or self.DEFAULT_COMMAND
        self._default_args = default_args or list(self.DEFAULT_ARGS)
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._approval_policy = approval_policy or self.DEFAULT_APPROVAL_POLICY
        self._sandbox_mode = sandbox_mode or self.DEFAULT_SANDBOX_MODE
        self._session_context: dict[str, dict[str, Any]] = {}

    def get_resume_mode(self) -> ResumeMode:
        """
        Return how this agent handles resume.

        Codex CLI does not have native session resume support, so it
        uses REPROMPT mode which requires re-sending the full context.

        Returns:
            ResumeMode.REPROMPT
        """
        return ResumeMode.REPROMPT

    def _build_command(
        self,
        prompt: str,
        config: AgentConfig,
    ) -> list[str]:
        """
        Build the full command to execute.

        Args:
            prompt: The prompt to send to Codex
            config: Agent configuration

        Returns:
            List of command-line arguments
        """
        cmd = [config.command or self._command]

        # Add default args from config or use instance defaults
        args = config.args if config.args else self._default_args
        cmd.extend(args)

        # Add approval policy
        approval = config.metadata.get("approval_policy", self._approval_policy)
        if approval:
            cmd.extend(["--approval-policy", approval])

        # Add sandbox mode
        sandbox = config.metadata.get("sandbox_mode", self._sandbox_mode)
        if sandbox:
            cmd.extend(["--sandbox", sandbox])

        # Add the prompt as the last argument
        cmd.append(prompt)

        return cmd

    def _parse_json_output(self, output: str | None) -> dict[str, Any]:
        """
        Parse JSON output from Codex CLI.

        Args:
            output: Raw output string from Codex

        Returns:
            Parsed JSON dictionary, or empty dict if parsing fails
        """
        if not output:
            return {}

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            # Output may not be JSON if --json flag wasn't used
            return {"raw_output": output}

    async def execute(
        self,
        prompt: str,
        workdir: str | Path,
        config: AgentConfig,
    ) -> ExecutionResult:
        """
        Execute a task with Codex CLI.

        Starts a new Codex session and runs the given prompt.
        Returns an ExecutionResult with output and session info.

        Args:
            prompt: The task/prompt to execute
            workdir: Working directory for execution
            config: Agent configuration

        Returns:
            ExecutionResult with status, output, and session info

        Example:
            >>> adapter = CodexAdapter()
            >>> result = await adapter.execute(
            ...     prompt="Fix the bug in app.py",
            ...     workdir="/path/to/project",
            ...     config=AgentConfig(command="codex")
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

        # Generate a session ID based on workdir for context tracking
        session_id = str(workdir_path.resolve())

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

                # Store session context for reprompt resume
                result.session_id = session_id
                self._session_context[session_id] = {
                    "prompt": prompt,
                    "workdir": str(workdir_path),
                    "config": config.model_dump(),
                }

                # Try to parse JSON output and add to metadata
                parsed = self._parse_json_output(output)
                if parsed:
                    result.metadata["parsed_output"] = parsed

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
                f"Please ensure Codex CLI is installed.",
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

        Since Codex CLI doesn't support native resume, this method
        re-sends the full context (original prompt + new prompt).

        Args:
            session_id: ID of the session to resume (workdir path)
            new_prompt: New prompt to send
            config: Optional updated configuration

        Returns:
            ExecutionResult with status and output

        Raises:
            ValueError: If session_id is invalid or session not found

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

        # Get stored context or create new
        context = self._session_context.get(session_id, {})
        original_prompt = context.get("prompt", "")

        # Build combined prompt with context
        combined_prompt = new_prompt
        if original_prompt:
            combined_prompt = (
                f"Context from previous session:\n"
                f"Original task: {original_prompt}\n\n"
                f"New task: {new_prompt}"
            )

        # Use provided config or create from stored context
        if config is None:
            stored_config = context.get("config", {})
            config = AgentConfig(
                command=stored_config.get("command", self._command),
                args=stored_config.get("args", list(self._default_args)),
                timeout_seconds=stored_config.get(
                    "timeout_seconds", self._default_timeout
                ),
            )

        # Build command with combined prompt
        cmd = self._build_command(combined_prompt, config)

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

                # Update stored context
                self._session_context[session_id] = {
                    "prompt": combined_prompt,
                    "workdir": str(workdir),
                    "config": config.model_dump(),
                }

                # Try to parse JSON output
                parsed = self._parse_json_output(output)
                if parsed:
                    result.metadata["parsed_output"] = parsed

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
                f"Please ensure Codex CLI is installed.",
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
        Check if Codex CLI is available and healthy.

        Returns:
            True if codex command is available
        """
        return shutil.which(self._command) is not None

    async def cleanup(self, session_id: str | None = None) -> None:
        """
        Clean up resources after execution.

        Removes stored session context for the given session.

        Args:
            session_id: Session to clean up, or None to clean all
        """
        if session_id:
            self._session_context.pop(session_id, None)
        else:
            self._session_context.clear()

    def __repr__(self) -> str:
        """Return string representation of the adapter."""
        return (
            f"CodexAdapter("
            f"command={self._command!r}, "
            f"resume_mode={self.get_resume_mode().value})"
        )
