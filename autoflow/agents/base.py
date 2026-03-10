"""
Autoflow Agent Adapter Base Module

Provides the abstract base class and common types for AI agent adapters.
All agent implementations (Claude Code, Codex, OpenClaw) inherit from
AgentAdapter and implement its abstract methods.

Usage:
    from autoflow.agents.base import AgentAdapter, ExecutionResult, ResumeMode

    class MyAgentAdapter(AgentAdapter):
        async def execute(self, prompt, workdir, config):
            # Implementation
            pass
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ResumeMode(StrEnum):
    """
    How an agent handles session resumption.

    - NATIVE: Agent has built-in resume capability (e.g., Claude Code with -r flag)
    - REPROMPT: Agent needs full context re-sent on resume (e.g., Codex CLI)
    - STATELESS: Agent doesn't support resume, each execution is independent
    """

    NATIVE = "native"
    REPROMPT = "reprompt"
    STATELESS = "stateless"


class ExecutionStatus(StrEnum):
    """Status of an agent execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


class AgentConfig(BaseModel):
    """
    Configuration for an agent execution.

    Contains all settings needed to run an agent, including command,
    arguments, timeouts, and behavior options.

    Attributes:
        command: The executable command (e.g., "claude", "codex")
        args: List of command-line arguments
        workdir: Working directory for execution
        timeout_seconds: Maximum execution time
        resume_mode: How this agent handles resume
        approval_policy: Approval behavior ("never", "suggest", "always")
        env: Environment variables to set
        session_id: Optional session ID for resume
        metadata: Additional configuration metadata
    """

    command: str
    args: list[str] = Field(default_factory=list)
    workdir: str = "."
    timeout_seconds: int = 300
    resume_mode: ResumeMode = ResumeMode.REPROMPT
    approval_policy: str = "suggest"
    env: dict[str, str] = Field(default_factory=dict)
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_cmd_args(self, prompt: str | None = None) -> list[str]:
        """
        Build the full command-line arguments list.

        Args:
            prompt: Optional prompt to append (some agents take prompt as arg)

        Returns:
            List of command-line arguments including the command
        """
        cmd = [self.command] + list(self.args)
        if prompt:
            cmd.append(prompt)
        return cmd


class ExecutionResult(BaseModel):
    """
    Result of an agent execution.

    Contains the output, status, and metadata from running an agent.
    All adapters must return an ExecutionResult from execute() and resume().

    Attributes:
        status: Execution status (success, failure, timeout, etc.)
        output: Standard output from the agent
        error: Error output if any
        exit_code: Process exit code
        session_id: Session ID for potential resume
        started_at: When execution started
        completed_at: When execution completed
        duration_seconds: Total execution time
        metadata: Additional result metadata
    """

    status: ExecutionStatus
    output: str | None = None
    error: str | None = None
    exit_code: int | None = None
    session_id: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == ExecutionStatus.SUCCESS

    def mark_complete(
        self,
        status: ExecutionStatus,
        exit_code: int | None = None,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Mark the execution as complete and calculate duration.

        Args:
            status: Final execution status
            exit_code: Process exit code
            output: Captured output
            error: Error output if any
        """
        self.status = status
        self.exit_code = exit_code
        self.output = output
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()


class AgentAdapter(ABC):
    """
    Abstract base class for AI agent adapters.

    Each adapter wraps a specific AI tool (Claude Code, Codex, OpenClaw)
    and provides a unified interface for:
    - Starting execution
    - Sending prompts
    - Resuming sessions
    - Checking status

    All methods are async for non-blocking parallel execution.

    Subclasses must implement:
    - execute(): Run a new task with the agent
    - resume(): Continue an existing session
    - get_resume_mode(): Return how this agent handles resume

    Example:
        >>> class ClaudeCodeAdapter(AgentAdapter):
        ...     async def execute(self, prompt, workdir, config):
        ...         # Run claude CLI
        ...         pass
        ...
        ...     async def resume(self, session_id, new_prompt):
        ...         # Resume claude session
        ...         pass
        ...
        ...     def get_resume_mode(self):
        ...         return ResumeMode.NATIVE
    """

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        workdir: str | Path,
        config: AgentConfig,
    ) -> ExecutionResult:
        """
        Execute a task with the agent.

        Starts a new agent session and runs the given prompt.
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
        pass

    @abstractmethod
    async def resume(
        self,
        session_id: str,
        new_prompt: str,
        config: AgentConfig | None = None,
    ) -> ExecutionResult:
        """
        Resume an existing session with a new prompt.

        Continues work in an existing agent session. Behavior depends
        on the agent's resume mode:
        - NATIVE: Uses agent's built-in resume (e.g., claude -r)
        - REPROMPT: Re-sends full context with new prompt
        - STATELESS: Raises error (cannot resume)

        Args:
            session_id: ID of the session to resume
            new_prompt: New prompt to send
            config: Optional updated configuration

        Returns:
            ExecutionResult with status and output

        Raises:
            NotImplementedError: If agent doesn't support resume (STATELESS)

        Example:
            >>> result = await adapter.resume(
            ...     session_id="abc123",
            ...     new_prompt="Now add tests for that fix"
            ... )
        """
        pass

    @abstractmethod
    def get_resume_mode(self) -> ResumeMode:
        """
        Return how this agent handles resume.

        Returns:
            ResumeMode indicating resume capability:
            - NATIVE: Built-in resume support
            - REPROMPT: Needs full context re-sent
            - STATELESS: No resume support
        """
        pass

    @property
    def name(self) -> str:
        """
        Return the adapter name.

        Default implementation uses the class name without 'Adapter' suffix.
        Subclasses can override for custom naming.

        Returns:
            Adapter name string
        """
        class_name = self.__class__.__name__
        if class_name.endswith("Adapter"):
            return class_name[:-7].lower()
        return class_name.lower()

    def supports_resume(self) -> bool:
        """
        Check if this adapter supports session resume.

        Returns:
            True if resume is supported (not STATELESS)
        """
        return self.get_resume_mode() != ResumeMode.STATELESS

    async def check_health(self) -> bool:
        """
        Check if the agent is available and healthy.

        Default implementation checks if the command exists.
        Subclasses can override for more sophisticated checks.

        Returns:
            True if agent is healthy and ready to use
        """
        import shutil

        # Subclasses should set a default config or override this method
        return shutil.which("claude") is not None

    async def cleanup(self, session_id: str | None = None) -> None:
        """
        Clean up resources after execution.

        Override this method to clean up session files, temporary
        directories, or other resources.

        Args:
            session_id: Optional session to clean up
        """
        # Default: no cleanup needed
        pass

    def __repr__(self) -> str:
        """Return string representation of the adapter."""
        return f"{self.__class__.__name__}(name={self.name!r}, resume_mode={self.get_resume_mode().value})"
