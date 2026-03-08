"""
Autoflow Symphony Bridge Module

Provides integration layer between Symphony workflows and Autoflow skills.
The bridge enables bidirectional execution: Symphony workflows can be
invoked as Autoflow skills, and Autoflow skills can be executed within
Symphony workflows with proper context translation and state synchronization.

Usage:
    from autoflow.skills.symphony_bridge import SymphonyBridge
    from autoflow.skills.registry import SkillRegistry
    from autoflow.agents.symphony import SymphonyAdapter

    registry = SkillRegistry()
    registry.load_skills()

    bridge = SymphonyBridge(registry=registry)
    bridge.register_adapter("symphony", SymphonyAdapter())

    # Execute Symphony workflow as a skill
    result = await bridge.execute_workflow_as_skill(
        workflow_name="multi-agent-analysis",
        task="Analyze the codebase",
        workdir="/path/to/project"
    )

    # Execute Autoflow skill within Symphony workflow
    result = await bridge.execute_skill_in_workflow(
        skill_name="IMPLEMENTER",
        workflow_session_id="symphony-session-123",
        task="Implement the feature",
        workdir="/path/to/project"
    )
"""

from __future__ import annotations

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
)
from autoflow.skills.executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutionStatus,
    SkillExecutor,
)
from autoflow.skills.registry import SkillDefinition, SkillRegistry


class SymphonyBridgeStatus(str, Enum):
    """Status of a Symphony bridge operation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class SymphonyWorkflowContext:
    """
    Context for executing a Symphony workflow.

    Contains all information needed to execute a Symphony workflow
    including the workflow name, task, workdir, and execution options.

    Attributes:
        workflow_name: Name of the Symphony workflow to execute
        task: The task description to execute
        workdir: Working directory for execution
        agent_config: Optional agent configuration overrides
        context_files: Additional files to include as context
        context_text: Additional context text to prepend
        session_id: Optional session ID for resume
        timeout_seconds: Optional timeout override
        checkpoint_interval: Interval for Symphony checkpoints
        metadata: Additional execution metadata
    """

    workflow_name: str
    task: str
    workdir: Union[str, Path]
    agent_config: Optional[AgentConfig] = None
    context_files: list[Path] = field(default_factory=list)
    context_text: Optional[str] = None
    session_id: Optional[str] = None
    timeout_seconds: Optional[int] = None
    checkpoint_interval: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SymphonyBridgeResult:
    """
    Result of a Symphony bridge operation.

    Contains the execution status, output, and metadata from a
    bridge operation between Symphony workflows and Autoflow skills.

    Attributes:
        operation_id: Unique identifier for this operation
        operation_type: Type of operation (workflow_as_skill or skill_in_workflow)
        status: Execution status
        execution_result: Result from the execution
        started_at: When execution started
        completed_at: When execution completed
        duration_seconds: Total execution time
        error: Error message if execution failed
        metadata: Additional result metadata
    """

    operation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    operation_type: str = ""
    status: SymphonyBridgeStatus = SymphonyBridgeStatus.PENDING
    execution_result: Optional[Union[SkillExecutionResult, ExecutionResult]] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if operation was successful."""
        return self.status == SymphonyBridgeStatus.SUCCESS

    @property
    def output(self) -> Optional[str]:
        """Get output from execution result."""
        if isinstance(self.execution_result, SkillExecutionResult):
            return self.execution_result.output
        elif isinstance(self.execution_result, ExecutionResult):
            return self.execution_result.output
        return None

    @property
    def session_id(self) -> Optional[str]:
        """Get session ID from execution result."""
        if isinstance(self.execution_result, SkillExecutionResult):
            return self.execution_result.session_id
        elif isinstance(self.execution_result, ExecutionResult):
            return self.execution_result.session_id
        return None

    def mark_complete(
        self,
        status: SymphonyBridgeStatus,
        execution_result: Optional[Union[SkillExecutionResult, ExecutionResult]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Mark the operation as complete.

        Args:
            status: Final execution status
            execution_result: Result from the execution
            error: Error message if any
        """
        self.status = status
        self.execution_result = execution_result
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SymphonyBridgeResult(operation_id={self.operation_id!r}, "
            f"operation_type={self.operation_type!r}, status={self.status.value})"
        )


class SymphonyBridgeError(Exception):
    """Exception raised for Symphony bridge errors."""

    pass


class SymphonyBridge:
    """
    Bridge for integrating Symphony workflows with Autoflow skills.

    The SymphonyBridge provides bidirectional integration between Symphony
    workflows and Autoflow skills by:

    1. Executing Symphony workflows as if they were Autoflow skills
    2. Executing Autoflow skills within Symphony workflow contexts
    3. Translating between workflow and skill execution contexts
    4. Synchronizing state between Symphony checkpoints and Autoflow runs

    The bridge uses the SkillExecutor for skill execution and registered
    agent adapters for Symphony workflow execution.

    Example:
        >>> from autoflow.skills.symphony_bridge import SymphonyBridge
        >>> from autoflow.skills.registry import SkillRegistry
        >>> from autoflow.agents.symphony import SymphonyAdapter
        >>>
        >>> registry = SkillRegistry()
        >>> registry.load_skills()
        >>>
        >>> bridge = SymphonyBridge(registry=registry)
        >>> bridge.register_adapter("symphony", SymphonyAdapter())
        >>>
        >>> # Execute Symphony workflow as a skill
        >>> result = await bridge.execute_workflow_as_skill(
        ...     workflow_name="multi-agent-analysis",
        ...     task="Analyze the codebase",
        ...     workdir="/path/to/project"
        ... )

    Attributes:
        executor: SkillExecutor instance for skill execution
        adapters: Dictionary of registered agent adapters by type
        default_timeout: Default execution timeout in seconds
    """

    DEFAULT_TIMEOUT = 600  # 10 minutes for Symphony workflows

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        executor: Optional[SkillExecutor] = None,
        adapters: Optional[dict[str, AgentAdapter]] = None,
        default_timeout: Optional[int] = None,
    ):
        """
        Initialize the Symphony bridge.

        Args:
            registry: Optional SkillRegistry instance
            executor: Optional SkillExecutor instance
            adapters: Optional dict of pre-registered adapters
            default_timeout: Default timeout in seconds
        """
        self._executor = executor
        self._adapters: dict[str, AgentAdapter] = {}
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT

        # Create executor if not provided
        if self._executor is None:
            self._executor = SkillExecutor(registry=registry)

        # Register adapters
        if adapters:
            for agent_type, adapter in adapters.items():
                self.register_adapter(agent_type, adapter)

    @property
    def executor(self) -> SkillExecutor:
        """
        Get the skill executor.

        Returns:
            SkillExecutor instance
        """
        return self._executor

    @property
    def registry(self) -> SkillRegistry:
        """
        Get the skill registry from the executor.

        Returns:
            SkillRegistry instance
        """
        return self._executor.registry

    def register_adapter(
        self,
        agent_type: str,
        adapter: AgentAdapter,
    ) -> None:
        """
        Register an agent adapter for a specific type.

        Args:
            agent_type: Agent type identifier (e.g., "symphony")
            adapter: AgentAdapter instance
        """
        self._adapters[agent_type] = adapter
        # Also register with executor
        self._executor.register_adapter(agent_type, adapter)

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

    async def execute_workflow_as_skill(
        self,
        workflow_name: str,
        task: str,
        workdir: Union[str, Path],
        agent_type: str = "symphony",
        agent_config: Optional[AgentConfig] = None,
        context_files: Optional[list[Path]] = None,
        context_text: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        checkpoint_interval: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SymphonyBridgeResult:
        """
        Execute a Symphony workflow as if it were an Autoflow skill.

        This method creates a virtual skill definition from the Symphony workflow
        and executes it using the Symphony agent adapter. The workflow is treated
        as a skill with appropriate context translation.

        Args:
            workflow_name: Name of the Symphony workflow to execute
            task: Task description
            workdir: Working directory for execution
            agent_type: Agent type to use (default: "symphony")
            agent_config: Optional agent configuration overrides
            context_files: Optional files to include as context
            context_text: Optional additional context text
            session_id: Optional session ID for resume
            timeout_seconds: Optional timeout override
            checkpoint_interval: Optional Symphony checkpoint interval
            metadata: Optional execution metadata

        Returns:
            SymphonyBridgeResult with status and output

        Raises:
            SymphonyBridgeError: If adapter not found or execution fails

        Example:
            >>> result = await bridge.execute_workflow_as_skill(
            ...     workflow_name="multi-agent-analysis",
            ...     task="Analyze the codebase",
            ...     workdir="/path/to/project"
            ... )
            >>> if result.success:
            ...     print(result.output)
        """
        # Create result object
        result = SymphonyBridgeResult(
            operation_type="workflow_as_skill",
            metadata=metadata or {},
        )
        result.status = SymphonyBridgeStatus.RUNNING

        try:
            # Get adapter
            adapter = self._adapters.get(agent_type)
            if adapter is None:
                raise SymphonyBridgeError(
                    f"No adapter registered for agent type: {agent_type}"
                )

            # Build prompt for workflow execution
            prompt = self._build_workflow_prompt(
                workflow_name=workflow_name,
                task=task,
                context_text=context_text,
                context_files=context_files or [],
            )

            # Build agent config
            config = agent_config or AgentConfig(
                command=agent_type,
                timeout_seconds=timeout_seconds or self._default_timeout,
            )
            if config.timeout_seconds is None:
                config.timeout_seconds = timeout_seconds or self._default_timeout

            # Execute workflow
            if session_id and adapter.supports_resume():
                # Resume existing session
                execution_result = await adapter.resume(
                    session_id=session_id,
                    new_prompt=prompt,
                    config=config,
                )
            else:
                # Start new execution
                execution_result = await adapter.execute(
                    prompt=prompt,
                    workdir=workdir,
                    config=config,
                )

            # Map execution status to bridge status
            status_map = {
                ExecutionStatus.SUCCESS: SymphonyBridgeStatus.SUCCESS,
                ExecutionStatus.FAILURE: SymphonyBridgeStatus.FAILURE,
                ExecutionStatus.TIMEOUT: SymphonyBridgeStatus.FAILURE,
                ExecutionStatus.CANCELLED: SymphonyBridgeStatus.CANCELLED,
                ExecutionStatus.ERROR: SymphonyBridgeStatus.ERROR,
            }

            result.mark_complete(
                status=status_map.get(
                    execution_result.status,
                    SymphonyBridgeStatus.ERROR
                ),
                execution_result=execution_result,
                error=execution_result.error,
            )

        except SymphonyBridgeError:
            raise
        except Exception as e:
            result.mark_complete(
                status=SymphonyBridgeStatus.ERROR,
                error=f"Workflow execution failed: {str(e)}",
            )
            raise SymphonyBridgeError(f"Workflow execution failed: {e}") from e

        return result

    async def execute_skill_in_workflow(
        self,
        skill_name: str,
        workflow_session_id: str,
        task: str,
        workdir: Union[str, Path],
        agent_type: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        context_files: Optional[list[Path]] = None,
        context_text: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SymphonyBridgeResult:
        """
        Execute an Autoflow skill within a Symphony workflow context.

        This method executes an Autoflow skill while maintaining the Symphony
        workflow session context. The skill execution results are synchronized
        with the Symphony workflow state.

        Args:
            skill_name: Name of the skill to execute
            workflow_session_id: Symphony workflow session ID
            task: Task description
            workdir: Working directory for execution
            agent_type: Optional preferred agent type
            agent_config: Optional agent configuration overrides
            context_files: Optional files to include as context
            context_text: Optional additional context text
            timeout_seconds: Optional timeout override
            metadata: Optional execution metadata

        Returns:
            SymphonyBridgeResult with status and output

        Raises:
            SymphonyBridgeError: If skill not found or execution fails

        Example:
            >>> result = await bridge.execute_skill_in_workflow(
            ...     skill_name="IMPLEMENTER",
            ...     workflow_session_id="symphony-session-123",
            ...     task="Implement the feature",
            ...     workdir="/path/to/project"
            ... )
            >>> if result.success:
            ...     print(result.output)
        """
        # Create result object
        result = SymphonyBridgeResult(
            operation_type="skill_in_workflow",
            metadata=metadata or {},
        )
        result.status = SymphonyBridgeStatus.RUNNING

        try:
            # Execute skill using executor
            skill_result = await self._executor.execute_skill(
                skill_name=skill_name,
                task=task,
                workdir=workdir,
                agent_type=agent_type,
                agent_config=agent_config,
                context_files=context_files,
                context_text=context_text,
                timeout_seconds=timeout_seconds,
            )

            # Map skill execution status to bridge status
            status_map = {
                SkillExecutionStatus.SUCCESS: SymphonyBridgeStatus.SUCCESS,
                SkillExecutionStatus.FAILURE: SymphonyBridgeStatus.FAILURE,
                SkillExecutionStatus.TIMEOUT: SymphonyBridgeStatus.FAILURE,
                SkillExecutionStatus.CANCELLED: SymphonyBridgeStatus.CANCELLED,
                SkillExecutionStatus.ERROR: SymphonyBridgeStatus.ERROR,
            }

            result.mark_complete(
                status=status_map.get(
                    skill_result.status,
                    SymphonyBridgeStatus.ERROR
                ),
                execution_result=skill_result,
                error=skill_result.error,
            )

            # Store workflow session ID in metadata for state synchronization
            result.metadata["workflow_session_id"] = workflow_session_id

        except Exception as e:
            result.mark_complete(
                status=SymphonyBridgeStatus.ERROR,
                error=f"Skill execution in workflow failed: {str(e)}",
            )
            raise SymphonyBridgeError(
                f"Skill execution in workflow failed: {e}"
            ) from e

        return result

    def _build_workflow_prompt(
        self,
        workflow_name: str,
        task: str,
        context_text: Optional[str] = None,
        context_files: list[Path] = None,
    ) -> str:
        """
        Build the full prompt for workflow execution.

        Combines workflow name with task and additional context.

        Args:
            workflow_name: Name of the Symphony workflow
            task: Task description
            context_text: Optional additional context text
            context_files: Optional files to include as context

        Returns:
            Complete prompt string
        """
        parts: list[str] = []

        # Add workflow identifier
        parts.append(f"## Symphony Workflow\n\nWorkflow: {workflow_name}\n")

        # Add separator
        parts.append("\n---\n")

        # Add context text if provided
        if context_text:
            parts.append(f"## Context\n\n{context_text}\n")

        # Add task
        parts.append(f"## Task\n\n{task}")

        # Add file context if provided
        if context_files:
            parts.append("\n## Context Files\n")
            for file_path in context_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"\n### {file_path.name}\n\n```\n{content}\n```")
                except Exception as e:
                    parts.append(f"\n### {file_path.name}\n\nError reading file: {e}")

        return "\n".join(parts)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SymphonyBridge(executor={self._executor!r}, "
            f"adapters={list(self._adapters.keys())})"
        )


def create_symphony_bridge(
    registry: Optional[SkillRegistry] = None,
    load_skills: bool = True,
    adapters: Optional[dict[str, AgentAdapter]] = None,
) -> SymphonyBridge:
    """
    Factory function to create a configured Symphony bridge.

    Args:
        registry: Optional SkillRegistry instance
        load_skills: Whether to auto-load skills
        adapters: Optional dict of pre-registered adapters

    Returns:
        Configured SymphonyBridge instance

    Example:
        >>> from autoflow.agents.symphony import SymphonyAdapter
        >>> bridge = create_symphony_bridge(
        ...     load_skills=True,
        ...     adapters={"symphony": SymphonyAdapter()}
        ... )
        >>> result = await bridge.execute_workflow_as_skill(
        ...     workflow_name="multi-agent-analysis",
        ...     task="Analyze the codebase",
        ...     workdir="/path/to/project"
        ... )
    """
    if registry is None:
        registry = SkillRegistry(auto_load=load_skills)

    return SymphonyBridge(registry=registry, adapters=adapters)
