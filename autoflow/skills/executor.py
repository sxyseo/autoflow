"""
Autoflow Skill Executor Module

Provides skill execution capabilities by combining skill definitions
with agent adapters. The executor coordinates running skills with
appropriate agents and tracking execution state.

Usage:
    from autoflow.skills.executor import SkillExecutor
    from autoflow.skills.registry import SkillRegistry
    from autoflow.agents.claude_code import ClaudeCodeAdapter

    registry = SkillRegistry()
    registry.load_skills()

    executor = SkillExecutor(registry=registry)
    executor.register_adapter("claude-code", ClaudeCodeAdapter())

    result = await executor.execute_skill(
        skill_name="IMPLEMENTER",
        task="Fix the bug in app.py",
        workdir="/path/to/project"
    )
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
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
from autoflow.skills.registry import SkillDefinition, SkillRegistry


class SkillExecutionStatus(str, Enum):
    """Status of a skill execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class SkillExecutionContext:
    """
    Context for a skill execution.

    Contains all information needed to execute a skill including
    the task, workdir, agent selection, and any additional context.

    Attributes:
        task: The task description to execute
        workdir: Working directory for execution
        agent_type: Agent type to use (e.g., "claude-code")
        agent_config: Optional agent configuration overrides
        context_files: Additional files to include as context
        context_text: Additional context text to prepend
        session_id: Optional session ID for resume
        timeout_seconds: Optional timeout override
        metadata: Additional execution metadata
    """

    task: str
    workdir: Union[str, Path]
    agent_type: str = "claude-code"
    agent_config: Optional[AgentConfig] = None
    context_files: list[Path] = field(default_factory=list)
    context_text: Optional[str] = None
    session_id: Optional[str] = None
    timeout_seconds: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillExecutionResult:
    """
    Result of a skill execution.

    Contains the execution status, output, and metadata from running
    a skill with an agent.

    Attributes:
        execution_id: Unique identifier for this execution
        skill_name: Name of the skill that was executed
        status: Execution status
        agent_result: Result from the agent adapter
        started_at: When execution started
        completed_at: When execution completed
        duration_seconds: Total execution time
        error: Error message if execution failed
        metadata: Additional result metadata
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    skill_name: str = ""
    status: SkillExecutionStatus = SkillExecutionStatus.PENDING
    agent_result: Optional[ExecutionResult] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == SkillExecutionStatus.SUCCESS

    @property
    def output(self) -> Optional[str]:
        """Get output from agent result."""
        return self.agent_result.output if self.agent_result else None

    @property
    def session_id(self) -> Optional[str]:
        """Get session ID from agent result."""
        return self.agent_result.session_id if self.agent_result else None

    def mark_complete(
        self,
        status: SkillExecutionStatus,
        agent_result: Optional[ExecutionResult] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Mark the execution as complete.

        Args:
            status: Final execution status
            agent_result: Result from the agent
            error: Error message if any
        """
        self.status = status
        self.agent_result = agent_result
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SkillExecutionResult(execution_id={self.execution_id!r}, "
            f"skill_name={self.skill_name!r}, status={self.status.value})"
        )


class SkillExecutorError(Exception):
    """Exception raised for skill executor errors."""

    pass


class SkillExecutor:
    """
    Executor for running skills with AI agents.

    The SkillExecutor coordinates skill execution by:
    1. Loading skill definitions from the registry
    2. Building prompts from skill content + task context
    3. Selecting appropriate agent adapters
    4. Executing the skill with the agent
    5. Tracking execution results

    The executor supports multiple agent types and can route skills
    to the appropriate agent based on skill metadata.

    Example:
        >>> from autoflow.skills.registry import SkillRegistry
        >>> from autoflow.skills.executor import SkillExecutor
        >>> from autoflow.agents.claude_code import ClaudeCodeAdapter
        >>>
        >>> registry = SkillRegistry()
        >>> registry.load_skills()
        >>>
        >>> executor = SkillExecutor(registry=registry)
        >>> executor.register_adapter("claude-code", ClaudeCodeAdapter())
        >>>
        >>> result = await executor.execute_skill(
        ...     skill_name="IMPLEMENTER",
        ...     task="Fix the bug in app.py",
        ...     workdir="/path/to/project"
        ... )

    Attributes:
        registry: SkillRegistry instance for loading skills
        adapters: Dictionary of registered agent adapters by type
        default_agent_type: Default agent type to use
        default_timeout: Default execution timeout in seconds
    """

    DEFAULT_AGENT_TYPE = "claude-code"
    DEFAULT_TIMEOUT = 300

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        adapters: Optional[dict[str, AgentAdapter]] = None,
        default_agent_type: Optional[str] = None,
        default_timeout: Optional[int] = None,
    ):
        """
        Initialize the skill executor.

        Args:
            registry: Optional SkillRegistry instance
            adapters: Optional dict of pre-registered adapters
            default_agent_type: Default agent type to use
            default_timeout: Default timeout in seconds
        """
        self._registry = registry
        self._adapters: dict[str, AgentAdapter] = {}
        self._default_agent_type = default_agent_type or self.DEFAULT_AGENT_TYPE
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._active_executions: dict[str, SkillExecutionResult] = {}

        if adapters:
            for agent_type, adapter in adapters.items():
                self.register_adapter(agent_type, adapter)

    @property
    def registry(self) -> SkillRegistry:
        """
        Get the skill registry, creating one if needed.

        Returns:
            SkillRegistry instance
        """
        if self._registry is None:
            self._registry = SkillRegistry(auto_load=True)
        return self._registry

    @registry.setter
    def registry(self, value: SkillRegistry) -> None:
        """Set the skill registry."""
        self._registry = value

    def register_adapter(
        self,
        agent_type: str,
        adapter: AgentAdapter,
    ) -> None:
        """
        Register an agent adapter for a specific type.

        Args:
            agent_type: Agent type identifier (e.g., "claude-code")
            adapter: AgentAdapter instance
        """
        self._adapters[agent_type] = adapter

    def get_adapter(self, agent_type: str) -> Optional[AgentAdapter]:
        """
        Get the adapter for an agent type.

        Args:
            agent_type: Agent type to look up

        Returns:
            AgentAdapter if registered, None otherwise
        """
        return self._adapters.get(agent_type)

    def has_adapter(self, agent_type: str) -> bool:
        """
        Check if an adapter is registered for a type.

        Args:
            agent_type: Agent type to check

        Returns:
            True if adapter is registered
        """
        return agent_type in self._adapters

    def list_adapters(self) -> list[str]:
        """
        List all registered adapter types.

        Returns:
            List of agent type identifiers
        """
        return list(self._adapters.keys())

    def _build_prompt(
        self,
        skill: SkillDefinition,
        context: SkillExecutionContext,
    ) -> str:
        """
        Build the full prompt for skill execution.

        Combines skill content with task and additional context.

        Args:
            skill: Skill definition to execute
            context: Execution context with task and options

        Returns:
            Complete prompt string
        """
        parts: list[str] = []

        # Add skill content (role, workflow, rules)
        parts.append(skill.content)

        # Add separator
        parts.append("\n---\n")

        # Add context text if provided
        if context.context_text:
            parts.append(f"## Context\n\n{context.context_text}\n")

        # Add task
        parts.append(f"## Task\n\n{context.task}")

        # Add file context if provided
        if context.context_files:
            parts.append("\n## Context Files\n")
            for file_path in context.context_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"\n### {file_path.name}\n\n```\n{content}\n```")
                except Exception as e:
                    parts.append(f"\n### {file_path.name}\n\nError reading file: {e}")

        return "\n".join(parts)

    def _select_agent_type(
        self,
        skill: SkillDefinition,
        preferred_type: Optional[str],
    ) -> str:
        """
        Select the appropriate agent type for a skill.

        Args:
            skill: Skill definition
            preferred_type: Preferred agent type if specified

        Returns:
            Selected agent type

        Raises:
            SkillExecutorError: If no compatible agent is available
        """
        # Use preferred type if specified and compatible
        if preferred_type:
            if preferred_type in skill.metadata.agents:
                if preferred_type in self._adapters:
                    return preferred_type
                raise SkillExecutorError(
                    f"No adapter registered for preferred agent type: {preferred_type}"
                )
            raise SkillExecutorError(
                f"Agent type '{preferred_type}' not compatible with skill '{skill.name}'. "
                f"Compatible agents: {skill.metadata.agents}"
            )

        # Try default agent type
        if (
            self._default_agent_type in skill.metadata.agents
            and self._default_agent_type in self._adapters
        ):
            return self._default_agent_type

        # Find first compatible agent with registered adapter
        for agent_type in skill.metadata.agents:
            if agent_type in self._adapters:
                return agent_type

        # No compatible adapter found
        available = list(self._adapters.keys())
        raise SkillExecutorError(
            f"No compatible adapter found for skill '{skill.name}'. "
            f"Skill agents: {skill.metadata.agents}, "
            f"Available adapters: {available}"
        )

    async def execute_skill(
        self,
        skill_name: str,
        task: str,
        workdir: Union[str, Path],
        agent_type: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        context_files: Optional[list[Path]] = None,
        context_text: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SkillExecutionResult:
        """
        Execute a skill with an agent.

        This is the main entry point for skill execution. It loads the skill,
        builds the prompt, selects an agent, and executes the task.

        Args:
            skill_name: Name of the skill to execute
            task: Task description
            workdir: Working directory for execution
            agent_type: Optional preferred agent type
            agent_config: Optional agent configuration overrides
            context_files: Optional files to include as context
            context_text: Optional additional context text
            session_id: Optional session ID for resume
            timeout_seconds: Optional timeout override
            metadata: Optional execution metadata

        Returns:
            SkillExecutionResult with status and output

        Raises:
            SkillExecutorError: If skill not found or execution fails

        Example:
            >>> result = await executor.execute_skill(
            ...     skill_name="IMPLEMENTER",
            ...     task="Fix the bug in app.py",
            ...     workdir="/path/to/project"
            ... )
            >>> if result.success:
            ...     print(result.output)
        """
        # Create execution context
        context = SkillExecutionContext(
            task=task,
            workdir=workdir,
            agent_type=agent_type or self._default_agent_type,
            agent_config=agent_config,
            context_files=context_files or [],
            context_text=context_text,
            session_id=session_id,
            timeout_seconds=timeout_seconds or self._default_timeout,
            metadata=metadata or {},
        )

        # Create result object
        result = SkillExecutionResult(skill_name=skill_name)
        result.status = SkillExecutionStatus.RUNNING

        # Track active execution
        self._active_executions[result.execution_id] = result

        try:
            # Load skill
            skill = self.registry.get_skill(skill_name)
            if skill is None:
                raise SkillExecutorError(f"Skill not found: {skill_name}")

            if not skill.is_valid:
                raise SkillExecutorError(
                    f"Skill '{skill_name}' is invalid: {', '.join(skill.errors)}"
                )

            # Select agent type
            selected_agent_type = self._select_agent_type(skill, agent_type)

            # Get adapter
            adapter = self._adapters.get(selected_agent_type)
            if adapter is None:
                raise SkillExecutorError(
                    f"No adapter registered for agent type: {selected_agent_type}"
                )

            # Build prompt
            prompt = self._build_prompt(skill, context)

            # Build agent config
            config = agent_config or AgentConfig(
                command=selected_agent_type,
                timeout_seconds=context.timeout_seconds,
            )
            if config.timeout_seconds is None:
                config.timeout_seconds = context.timeout_seconds

            # Execute with agent
            agent_result: ExecutionResult

            if session_id and adapter.supports_resume():
                # Resume existing session
                agent_result = await adapter.resume(
                    session_id=session_id,
                    new_prompt=prompt,
                    config=config,
                )
            else:
                # Start new execution
                agent_result = await adapter.execute(
                    prompt=prompt,
                    workdir=workdir,
                    config=config,
                )

            # Map agent status to skill execution status
            status_map = {
                ExecutionStatus.SUCCESS: SkillExecutionStatus.SUCCESS,
                ExecutionStatus.FAILURE: SkillExecutionStatus.FAILURE,
                ExecutionStatus.TIMEOUT: SkillExecutionStatus.TIMEOUT,
                ExecutionStatus.CANCELLED: SkillExecutionStatus.CANCELLED,
                ExecutionStatus.ERROR: SkillExecutionStatus.ERROR,
            }

            result.mark_complete(
                status=status_map.get(
                    agent_result.status,
                    SkillExecutionStatus.ERROR
                ),
                agent_result=agent_result,
                error=agent_result.error,
            )

        except SkillExecutorError:
            raise
        except asyncio.CancelledError:
            result.mark_complete(
                status=SkillExecutionStatus.CANCELLED,
                error="Execution was cancelled",
            )
            raise
        except Exception as e:
            result.mark_complete(
                status=SkillExecutionStatus.ERROR,
                error=f"Execution failed: {str(e)}",
            )
            raise SkillExecutorError(f"Skill execution failed: {e}") from e
        finally:
            # Remove from active executions
            self._active_executions.pop(result.execution_id, None)

        return result

    async def execute_skill_sync(
        self,
        skill_name: str,
        task: str,
        workdir: Union[str, Path],
        **kwargs: Any,
    ) -> SkillExecutionResult:
        """
        Synchronous wrapper for execute_skill.

        Creates a new event loop and runs execute_skill synchronously.
        Useful for non-async contexts.

        Args:
            skill_name: Name of the skill to execute
            task: Task description
            workdir: Working directory
            **kwargs: Additional arguments passed to execute_skill

        Returns:
            SkillExecutionResult with status and output
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return await self.execute_skill(
            skill_name=skill_name,
            task=task,
            workdir=workdir,
            **kwargs,
        )

    def run_skill(
        self,
        skill_name: str,
        task: str,
        workdir: Union[str, Path],
        **kwargs: Any,
    ) -> SkillExecutionResult:
        """
        Blocking wrapper for execute_skill.

        Runs execute_skill in a synchronous context. This is the
        simplest way to execute a skill from non-async code.

        Args:
            skill_name: Name of the skill to execute
            task: Task description
            workdir: Working directory
            **kwargs: Additional arguments passed to execute_skill

        Returns:
            SkillExecutionResult with status and output
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Already in async context, create new loop
                loop = asyncio.new_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.execute_skill(
                skill_name=skill_name,
                task=task,
                workdir=workdir,
                **kwargs,
            )
        )

    async def resume_skill(
        self,
        session_id: str,
        skill_name: str,
        new_task: str,
        workdir: Union[str, Path],
        agent_type: Optional[str] = None,
        **kwargs: Any,
    ) -> SkillExecutionResult:
        """
        Resume a skill execution with a new task.

        Continues work in an existing session with a new task.
        The agent type must support session resume.

        Args:
            session_id: Session ID to resume
            skill_name: Name of the skill
            new_task: New task to execute
            workdir: Working directory
            agent_type: Optional preferred agent type
            **kwargs: Additional arguments

        Returns:
            SkillExecutionResult with status and output

        Raises:
            SkillExecutorError: If agent doesn't support resume
        """
        return await self.execute_skill(
            skill_name=skill_name,
            task=new_task,
            workdir=workdir,
            agent_type=agent_type,
            session_id=session_id,
            **kwargs,
        )

    def get_active_executions(self) -> list[SkillExecutionResult]:
        """
        Get all currently active executions.

        Returns:
            List of active SkillExecutionResult objects
        """
        return list(self._active_executions.values())

    def get_execution(self, execution_id: str) -> Optional[SkillExecutionResult]:
        """
        Get an execution by ID.

        Args:
            execution_id: Execution ID to look up

        Returns:
            SkillExecutionResult if found, None otherwise
        """
        return self._active_executions.get(execution_id)

    async def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel an active execution.

        Args:
            execution_id: Execution ID to cancel

        Returns:
            True if execution was cancelled, False if not found
        """
        result = self._active_executions.get(execution_id)
        if result is None:
            return False

        result.mark_complete(
            status=SkillExecutionStatus.CANCELLED,
            error="Execution cancelled by user",
        )
        return True

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SkillExecutor(registry={self.registry!r}, "
            f"adapters={list(self._adapters.keys())}, "
            f"active={len(self._active_executions)})"
        )


def create_executor(
    registry: Optional[SkillRegistry] = None,
    load_skills: bool = True,
    adapters: Optional[dict[str, AgentAdapter]] = None,
) -> SkillExecutor:
    """
    Factory function to create a configured skill executor.

    Args:
        registry: Optional SkillRegistry instance
        load_skills: Whether to auto-load skills
        adapters: Optional dict of pre-registered adapters

    Returns:
        Configured SkillExecutor instance

    Example:
        >>> from autoflow.agents.claude_code import ClaudeCodeAdapter
        >>> executor = create_executor(
        ...     load_skills=True,
        ...     adapters={"claude-code": ClaudeCodeAdapter()}
        ... )
        >>> result = executor.run_skill(
        ...     skill_name="IMPLEMENTER",
        ...     task="Fix the bug",
        ...     workdir="/path/to/project"
        ... )
    """
    if registry is None:
        registry = SkillRegistry(auto_load=load_skills)

    return SkillExecutor(registry=registry, adapters=adapters)
