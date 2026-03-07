"""
OpenClaw Session Adapter

Provides integration with OpenClaw's sessions_spawn API for multi-agent
coordination. Supports spawning isolated sub-agents and ACP runtime agents.

Usage:
    from autoflow.agents.openclaw import OpenClawAdapter

    adapter = OpenClawAdapter()
    result = await adapter.execute(
        prompt="Fix the bug in app.py",
        workdir="/path/to/project",
        config=AgentConfig(command="openclaw")
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


class OpenClawRuntime(str, Enum):
    """Runtime types for OpenClaw session spawning."""

    CLAUDE = "claude"  # Default Claude runtime
    ACP = "acp"  # ACP runtime for external agents (Codex, etc.)


@dataclass
class SpawnResult:
    """
    Result from spawning an OpenClaw sub-agent.

    Attributes:
        session_id: Child session key for the spawned session
        run_id: Run ID for the execution
        status: Status of the spawn operation
    """

    session_id: str
    run_id: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


class OpenClawAdapter(AgentAdapter):
    """
    Adapter for OpenClaw sessions_spawn integration.

    Provides multi-agent coordination via OpenClaw's session spawning API.
    Supports:
    - Spawning isolated sub-agents with lower token cost
    - ACP runtime for external agents (Codex, etc.)
    - Native session resume via session keys
    - Result announcement back to requester's channel

    The sessions_spawn API allows spawning isolated sub-agents that can
    work in parallel, with results announced back to the parent session.

    Attributes:
        DEFAULT_COMMAND: Default command to invoke OpenClaw
        DEFAULT_ARGS: Default arguments
        DEFAULT_TIMEOUT: Default execution timeout in seconds
        DEFAULT_GATEWAY_URL: Default OpenClaw gateway URL
    """

    DEFAULT_COMMAND: str = "openclaw"
    DEFAULT_ARGS: list[str] = ["session", "run"]
    DEFAULT_TIMEOUT: int = 300
    DEFAULT_GATEWAY_URL: str = "http://localhost:3000"

    def __init__(
        self,
        command: Optional[str] = None,
        default_args: Optional[list[str]] = None,
        default_timeout: Optional[int] = None,
        gateway_url: Optional[str] = None,
    ) -> None:
        """
        Initialize the OpenClaw adapter.

        Args:
            command: Override default openclaw command
            default_args: Override default arguments
            default_timeout: Override default timeout in seconds
            gateway_url: Override default gateway URL
        """
        self._command = command or self.DEFAULT_COMMAND
        self._default_args = default_args or list(self.DEFAULT_ARGS)
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._gateway_url = gateway_url or self.DEFAULT_GATEWAY_URL
        self._active_sessions: dict[str, dict[str, Any]] = {}

    def get_resume_mode(self) -> ResumeMode:
        """
        Return how this agent handles resume.

        OpenClaw has native session resume support via session keys,
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
            prompt: The prompt to send to OpenClaw
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

        # Add gateway URL if specified
        gateway = config.metadata.get("gateway_url", self._gateway_url)
        if gateway:
            cmd.extend(["--gateway", gateway])

        # Add timeout
        timeout = config.timeout_seconds or self._default_timeout
        cmd.extend(["--timeout", str(timeout)])

        # Add the prompt as the last argument
        cmd.append(prompt)

        return cmd

    async def _call_openclaw_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        config: AgentConfig,
    ) -> dict[str, Any]:
        """
        Call an OpenClaw gateway tool.

        This is a placeholder for direct gateway API calls.
        In practice, this would use HTTP requests to the OpenClaw gateway.

        Args:
            tool_name: Name of the OpenClaw tool to call
            payload: Payload for the tool call
            config: Agent configuration

        Returns:
            Result from the OpenClaw gateway
        """
        # For now, this simulates the API call
        # In a real implementation, this would use aiohttp or similar
        gateway_url = config.metadata.get("gateway_url", self._gateway_url)

        # Build command to call OpenClaw CLI with tool payload
        cmd = [
            config.command or self._command,
            "tool",
            "call",
            "--tool", tool_name,
            "--payload", json.dumps(payload),
            "--gateway", gateway_url,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(
                f"OpenClaw tool call failed: {stderr.decode('utf-8')}"
            )

        return json.loads(stdout.decode("utf-8"))

    async def spawn_subagent(
        self,
        task: str,
        label: str,
        agent_id: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 300,
        workdir: Optional[Union[str, Path]] = None,
        config: Optional[AgentConfig] = None,
    ) -> SpawnResult:
        """
        Spawn an isolated sub-agent session via OpenClaw.

        This allows spawning isolated sub-agents with their own context,
        useful for parallel work with lower token cost than CLI-based
        orchestration.

        Args:
            task: The task description for the sub-agent
            label: A label for logging and UI purposes
            agent_id: Optional agent ID to spawn under
            model: Optional model override
            timeout_seconds: Timeout for the sub-agent run
            workdir: Working directory for the sub-agent
            config: Agent configuration

        Returns:
            SpawnResult with session_id, run_id, and status

        Example:
            >>> adapter = OpenClawAdapter()
            >>> result = await adapter.spawn_subagent(
            ...     task="Implement the login feature",
            ...     label="login-impl",
            ...     timeout_seconds=600
            ... )
            >>> print(result.session_id)
        """
        if config is None:
            config = AgentConfig(
                command=self._command,
                args=list(self._default_args),
                timeout_seconds=timeout_seconds,
            )

        payload = {
            "task": task,
            "label": label,
            "runTimeoutSeconds": timeout_seconds,
            "cleanup": "keep",  # Keep session for result retrieval
            "sandbox": "inherit",
        }

        if agent_id:
            payload["agentId"] = agent_id
        if model:
            payload["model"] = model
        if workdir:
            payload["workdir"] = str(workdir)

        result = await self._call_openclaw_tool("sessions_spawn", payload, config)

        spawn_result = SpawnResult(
            session_id=result.get("childSessionKey", ""),
            run_id=result.get("runId", ""),
            status=result.get("status", "unknown"),
            metadata=result,
        )

        # Track active session
        self._active_sessions[spawn_result.session_id] = {
            "label": label,
            "task": task,
            "run_id": spawn_result.run_id,
            "status": spawn_result.status,
        }

        return spawn_result

    async def spawn_acp_agent(
        self,
        task: str,
        agent_id: str,
        thread: bool = True,
        config: Optional[AgentConfig] = None,
    ) -> SpawnResult:
        """
        Spawn an ACP runtime agent (e.g., Codex) via OpenClaw.

        This allows spawning external agents like Codex CLI through
        OpenClaw's ACP runtime path.

        Args:
            task: The task description for the agent
            agent_id: Agent ID for the ACP agent
            thread: Whether to thread the session
            config: Agent configuration

        Returns:
            SpawnResult with session_id, run_id, and status

        Example:
            >>> adapter = OpenClawAdapter()
            >>> result = await adapter.spawn_acp_agent(
            ...     task="Review the code changes",
            ...     agent_id="codex-reviewer"
            ... )
        """
        if config is None:
            config = AgentConfig(
                command=self._command,
                args=list(self._default_args),
                timeout_seconds=self._default_timeout,
            )

        payload = {
            "task": task,
            "runtime": OpenClawRuntime.ACP.value,
            "agentId": agent_id,
            "thread": thread,
            "mode": "session",
        }

        result = await self._call_openclaw_tool("sessions_spawn", payload, config)

        spawn_result = SpawnResult(
            session_id=result.get("childSessionKey", ""),
            run_id=result.get("runId", ""),
            status=result.get("status", "unknown"),
            metadata=result,
        )

        # Track active session
        self._active_sessions[spawn_result.session_id] = {
            "agent_id": agent_id,
            "task": task,
            "runtime": "acp",
            "run_id": spawn_result.run_id,
            "status": spawn_result.status,
        }

        return spawn_result

    async def execute(
        self,
        prompt: str,
        workdir: Union[str, Path],
        config: AgentConfig,
    ) -> ExecutionResult:
        """
        Execute a task with OpenClaw.

        Starts a new OpenClaw session and runs the given prompt.
        Returns an ExecutionResult with output and session info.

        Args:
            prompt: The task/prompt to execute
            workdir: Working directory for execution
            config: Agent configuration

        Returns:
            ExecutionResult with status, output, and session info

        Example:
            >>> adapter = OpenClawAdapter()
            >>> result = await adapter.execute(
            ...     prompt="Fix the bug in app.py",
            ...     workdir="/path/to/project",
            ...     config=AgentConfig(command="openclaw")
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
                f"Please ensure OpenClaw CLI is installed.",
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

        Uses OpenClaw's native session resume capability.

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
                f"Please ensure OpenClaw CLI is installed.",
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
        Extract session ID from OpenClaw output.

        Args:
            output: Raw output from OpenClaw

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
                return parsed.get("session_id") or parsed.get("sessionKey")
        except json.JSONDecodeError:
            pass

        return None

    def _parse_output(self, output: Optional[str]) -> dict[str, Any]:
        """
        Parse output from OpenClaw.

        Args:
            output: Raw output string from OpenClaw

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
        Check if OpenClaw CLI is available and healthy.

        Returns:
            True if openclaw command is available
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
            f"OpenClawAdapter("
            f"command={self._command!r}, "
            f"gateway_url={self._gateway_url!r}, "
            f"resume_mode={self.get_resume_mode().value})"
        )
