"""
Symphony Agent Adapter

Provides integration with Symphony's multi-agent orchestration framework.
Supports agent spawning, session management, and result coordination.

Usage:
    from autoflow.agents.symphony import SymphonyAdapter

    adapter = SymphonyAdapter()
    result = await adapter.execute(
        prompt="Fix the bug in app.py",
        workdir="/path/to/project",
        config=AgentConfig(command="symphony")
    )
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from autoflow.agents.base import (
    AgentAdapter,
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)


class SymphonyRuntime(str, Enum):
    """Runtime types for Symphony agent execution."""

    CLAUDE = "claude"  # Default Claude runtime
    GENERIC = "generic"  # Generic agent runtime


@dataclass
class SymphonySession:
    """
    Session information for a Symphony agent.

    Attributes:
        session_id: Unique session identifier
        agent_id: Agent ID for the session
        status: Current status of the session
        metadata: Additional session metadata
    """

    session_id: str
    agent_id: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


class SymphonyAdapter(AgentAdapter):
    """
    Adapter for Symphony multi-agent orchestration framework.

    Provides multi-agent coordination via Symphony's agent management API.
    Supports:
    - Spawning and managing isolated agent sessions
    - Native session resume via session IDs
    - Result coordination across multiple agents
    - Flexible runtime configuration

    The Symphony framework allows orchestrating multiple AI agents that can
    work independently or collaboratively on complex tasks.

    Attributes:
        DEFAULT_COMMAND: Default command to invoke Symphony
        DEFAULT_ARGS: Default arguments
        DEFAULT_TIMEOUT: Default execution timeout in seconds
        DEFAULT_API_URL: Default Symphony API URL
    """

    DEFAULT_COMMAND: str = "symphony"
    DEFAULT_ARGS: list[str] = ["agent", "run"]
    DEFAULT_TIMEOUT: int = 300
    DEFAULT_API_URL: str = "http://localhost:8080"

    def __init__(
        self,
        command: Optional[str] = None,
        default_args: Optional[list[str]] = None,
        default_timeout: Optional[int] = None,
        api_url: Optional[str] = None,
    ) -> None:
        """
        Initialize the Symphony adapter.

        Args:
            command: Override default symphony command
            default_args: Override default arguments
            default_timeout: Override default timeout in seconds
            api_url: Override default API URL
        """
        self._command = command or self.DEFAULT_COMMAND
        self._default_args = default_args or list(self.DEFAULT_ARGS)
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._api_url = api_url or self.DEFAULT_API_URL
        self._active_sessions: dict[str, dict[str, Any]] = {}

    def get_resume_mode(self) -> ResumeMode:
        """
        Return how this agent handles resume.

        Symphony has native session resume support via session IDs,
        allowing continuation of previous sessions.

        Returns:
            ResumeMode.NATIVE
        """
        return ResumeMode.NATIVE

    def _build_command(
        self,
        prompt: str,
        config: AgentConfig,
        session_id: Optional[str] = None,
    ) -> list[str]:
        """
        Build the full command to execute.

        Args:
            prompt: The prompt to send to Symphony
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
            cmd.extend(["--session", session_id])

        # Add API URL if specified
        api_url = config.metadata.get("api_url", self._api_url)
        if api_url:
            cmd.extend(["--api-url", api_url])

        # Add timeout
        timeout = config.timeout_seconds or self._default_timeout
        cmd.extend(["--timeout", str(timeout)])

        # Add the prompt as the last argument
        cmd.append(prompt)

        return cmd

    async def execute(
        self,
        prompt: str,
        workdir: Union[str, Path],
        config: AgentConfig,
    ) -> ExecutionResult:
        """
        Execute a task with Symphony.

        Starts a new Symphony session and runs the given prompt.
        Returns an ExecutionResult with output and session info.

        Args:
            prompt: The task/prompt to execute
            workdir: Working directory for execution
            config: Agent configuration

        Returns:
            ExecutionResult with status, output, and session info

        Example:
            >>> adapter = SymphonyAdapter()
            >>> result = await adapter.execute(
            ...     prompt="Fix the bug in app.py",
            ...     workdir="/path/to/project",
            ...     config=AgentConfig(command="symphony")
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

                # Try to extract session ID from output
                session_id = self._extract_session_id(output)
                if session_id:
                    result.session_id = session_id
                    self._active_sessions[session_id] = {
                        "prompt": prompt,
                        "workdir": str(workdir_path),
                    }
                else:
                    result.session_id = str(workdir_path.resolve())

                # Try to parse JSON output
                parsed = self._parse_output(output)
                if parsed:
                    result.metadata["parsed_output"] = parsed

            except asyncio.TimeoutError:
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
                f"Please ensure Symphony CLI is installed.",
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
        config: Optional[AgentConfig] = None,
    ) -> ExecutionResult:
        """
        Resume an existing session with a new prompt.

        Uses Symphony's native session resume capability.

        Args:
            session_id: ID of the session to resume
            new_prompt: New prompt to send
            config: Optional updated configuration

        Returns:
            ExecutionResult with status and output

        Example:
            >>> result = await adapter.resume(
            ...     session_id="abc123",
            ...     new_prompt="Now add tests for that fix"
            ... )
        """
        result = ExecutionResult()

        # Get stored session info
        session_info = self._active_sessions.get(session_id, {})
        workdir = session_info.get("workdir", ".")

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
                cwd=workdir,
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

                # Update session info
                self._active_sessions[session_id]["prompt"] = new_prompt

                # Try to parse output
                parsed = self._parse_output(output)
                if parsed:
                    result.metadata["parsed_output"] = parsed

            except asyncio.TimeoutError:
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
                f"Please ensure Symphony CLI is installed.",
            )
        except Exception as e:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                exit_code=-1,
                error=f"Resume failed: {str(e)}",
            )

        return result

    def _extract_session_id(self, output: Optional[str]) -> Optional[str]:
        """
        Extract session ID from Symphony output.

        Args:
            output: Raw output from Symphony

        Returns:
            Session ID if found, None otherwise
        """
        if not output:
            return None

        # Try to find session ID in various formats
        # Format 1: "Session: <id>"
        for line in output.split("\n"):
            if line.startswith("Session:"):
                return line.split(":", 1)[1].strip()
            if line.startswith("session_id:"):
                return line.split(":", 1)[1].strip()

        # Format 2: JSON output with session field
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                return parsed.get("session_id") or parsed.get("sessionId")
        except json.JSONDecodeError:
            pass

        return None

    def _parse_output(self, output: Optional[str]) -> dict[str, Any]:
        """
        Parse output from Symphony.

        Args:
            output: Raw output string from Symphony

        Returns:
            Parsed dictionary, or empty dict if parsing fails
        """
        if not output:
            return {}

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {"raw_output": output}

    async def check_health(self) -> bool:
        """
        Check if Symphony CLI is available and healthy.

        Returns:
            True if symphony command is available
        """
        return shutil.which(self._command) is not None

    async def cleanup(self, session_id: Optional[str] = None) -> None:
        """
        Clean up resources after execution.

        Removes stored session info for the given session.

        Args:
            session_id: Session to clean up, or None to clean all
        """
        if session_id:
            self._active_sessions.pop(session_id, None)
        else:
            self._active_sessions.clear()

    def get_active_sessions(self) -> dict[str, dict[str, Any]]:
        """
        Get all active sessions.

        Returns:
            Dictionary of session_id -> session info
        """
        return dict(self._active_sessions)

    def __repr__(self) -> str:
        """Return string representation of the adapter."""
        return (
            f"SymphonyAdapter("
            f"command={self._command!r}, "
            f"api_url={self._api_url!r}, "
            f"resume_mode={self.get_resume_mode().value})"
        )
