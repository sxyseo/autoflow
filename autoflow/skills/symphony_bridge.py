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
from autoflow.core.state import StateManager, RunStatus, TaskStatus
from autoflow.skills.executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutionStatus,
    SkillExecutor,
)
from autoflow.skills.registry import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
    SkillStatus,
)


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

    State Synchronization:
    When a state_dir is provided, the bridge maintains persistent state
    mapping between Symphony checkpoints and Autoflow runs. This enables:
    - Bi-directional state sync: checkpoint ↔ run
    - Checkpoint discovery from runs and vice versa
    - Persistent checkpoint state storage in run metadata
    - Status mapping between checkpoint and run states

    Example:
        >>> from autoflow.skills.symphony_bridge import SymphonyBridge
        >>> from autoflow.skills.registry import SkillRegistry
        >>> from autoflow.agents.symphony import SymphonyAdapter
        >>>
        >>> registry = SkillRegistry()
        >>> registry.load_skills()
        >>>
        >>> bridge = SymphonyBridge(registry=registry, state_dir=".autoflow")
        >>> bridge.register_adapter("symphony", SymphonyAdapter())
        >>>
        >>> # Execute Symphony workflow as a skill
        >>> result = await bridge.execute_workflow_as_skill(
        ...     workflow_name="multi-agent-analysis",
        ...     task="Analyze the codebase",
        ...     workdir="/path/to/project"
        ... )
        >>>
        >>> # Sync checkpoint state to run
        >>> bridge.sync_checkpoint_to_run(
        ...     checkpoint_id="checkpoint-123",
        ...     run_id=result.session_id,
        ...     checkpoint_data={"status": "complete"}
        ... )

    Attributes:
        executor: SkillExecutor instance for skill execution
        adapters: Dictionary of registered agent adapters by type
        default_timeout: Default execution timeout in seconds
        state_manager: Optional StateManager for persistent state
    """

    DEFAULT_TIMEOUT = 600  # 10 minutes for Symphony workflows
    DEFAULT_STATE_DIR = ".autoflow"

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        executor: Optional[SkillExecutor] = None,
        adapters: Optional[dict[str, AgentAdapter]] = None,
        default_timeout: Optional[int] = None,
        state_dir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the Symphony bridge.

        Args:
            registry: Optional SkillRegistry instance
            executor: Optional SkillExecutor instance
            adapters: Optional dict of pre-registered adapters
            default_timeout: Default timeout in seconds
            state_dir: Optional state directory for persistent storage
        """
        self._executor = executor
        self._adapters: dict[str, AgentAdapter] = {}
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT
        self._registered_workflow_skills: set[str] = set()
        self._state_manager: Optional[StateManager] = None

        # Create executor if not provided
        if self._executor is None:
            self._executor = SkillExecutor(registry=registry)

        # Initialize state manager
        if state_dir is not None:
            self._state_manager = StateManager(state_dir)
            self._state_manager.initialize()

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

    @property
    def state_manager(self) -> Optional[StateManager]:
        """
        Get the state manager if initialized.

        Returns:
            StateManager instance or None
        """
        return self._state_manager

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

    def _create_virtual_skill(
        self,
        workflow_name: str,
        workflow_description: Optional[str] = None,
        workflow_metadata: Optional[dict[str, Any]] = None,
    ) -> SkillDefinition:
        """
        Create a virtual skill definition from a Symphony workflow.

        This method translates a Symphony workflow into a SkillDefinition
        that can be registered and invoked like any other Autoflow skill.

        Args:
            workflow_name: Name of the Symphony workflow
            workflow_description: Optional description of the workflow
            workflow_metadata: Optional additional workflow metadata

        Returns:
            SkillDefinition for the workflow

        Raises:
            SymphonyBridgeError: If workflow_name is invalid
        """
        # Validate workflow name format (should be valid skill name)
        if not workflow_name or not isinstance(workflow_name, str):
            raise SymphonyBridgeError(
                f"Invalid workflow name: {workflow_name!r}"
            )

        # Convert workflow name to skill name format
        # e.g., "multi-agent-analysis" -> "MULTI_AGENT_ANALYSIS"
        skill_name = workflow_name.upper().replace("-", "_")

        # Create skill metadata
        metadata = SkillMetadata(
            name=skill_name,
            description=workflow_description or f"Symphony workflow: {workflow_name}",
            version="1.0.0",
            agents=["symphony"],
            enabled=True,
        )

        # Build skill content that describes the workflow invocation
        content_parts: list[str] = []

        # Add workflow header
        content_parts.append(f"# Symphony Workflow: {workflow_name}\n")

        # Add description if provided
        if workflow_description:
            content_parts.append(f"{workflow_description}\n")

        # Add workflow metadata if provided
        if workflow_metadata:
            content_parts.append("\n## Workflow Metadata\n")
            for key, value in workflow_metadata.items():
                content_parts.append(f"- {key}: {value}\n")

        # Add execution instructions
        content_parts.append("\n## Execution Instructions\n")
        content_parts.append(
            "This is a Symphony workflow that will be executed through the "
            "Symphony agent adapter. The workflow will be invoked with the "
            "provided task and context.\n"
        )

        # Add workflow invocation template
        content_parts.append("\n## Workflow Invocation\n")
        content_parts.append(f"**Workflow Name:** {workflow_name}\n")
        content_parts.append(
            "**Agent Type:** symphony\n"
        )

        content = "".join(content_parts)

        # Create skill definition (file_path is virtual)
        skill = SkillDefinition(
            metadata=metadata,
            content=content,
            file_path=Path(f"virtual://symphony/{workflow_name}/SKILL.md"),
            status=SkillStatus.LOADED,
            errors=[],
        )

        return skill

    def register_workflow_as_skill(
        self,
        workflow_name: str,
        workflow_description: Optional[str] = None,
        workflow_metadata: Optional[dict[str, Any]] = None,
        override: bool = False,
    ) -> SkillDefinition:
        """
        Register a Symphony workflow as a virtual skill in the registry.

        This method creates a virtual skill from a Symphony workflow and
        registers it in the skill registry, making it discoverable and
        invocable like any other Autoflow skill.

        Args:
            workflow_name: Name of the Symphony workflow
            workflow_description: Optional description of the workflow
            workflow_metadata: Optional additional workflow metadata
            override: Whether to override existing skill with same name

        Returns:
            The registered SkillDefinition

        Raises:
            SymphonyBridgeError: If skill already exists and override=False

        Example:
            >>> skill = bridge.register_workflow_as_skill(
            ...     workflow_name="multi-agent-analysis",
            ...     workflow_description="Analyzes code using multiple agents"
            ... )
            >>> print(skill.name)
            MULTI_AGENT_ANALYSIS
        """
        # Create virtual skill
        skill = self._create_virtual_skill(
            workflow_name=workflow_name,
            workflow_description=workflow_description,
            workflow_metadata=workflow_metadata,
        )

        # Check if skill already exists
        existing = self.registry.get_skill(skill.name)
        if existing is not None and not override:
            raise SymphonyBridgeError(
                f"Skill '{skill.name}' already exists in registry. "
                f"Use override=True to replace it."
            )

        # Register skill in registry using the correct API
        # register_skill takes metadata and content separately
        from autoflow.skills.registry import SkillRegistryError

        try:
            registered = self.registry.register_skill(
                metadata=skill.metadata.model_dump(),
                content=skill.content,
            )
        except SkillRegistryError as e:
            raise SymphonyBridgeError(f"Failed to register workflow skill: {e}") from e

        # Track registered workflow skill
        self._registered_workflow_skills.add(registered.name)

        return registered

    def unregister_workflow_skill(
        self,
        workflow_name: str,
    ) -> bool:
        """
        Unregister a Symphony workflow skill from the registry.

        Args:
            workflow_name: Name of the Symphony workflow

        Returns:
            True if skill was unregistered, False if not found

        Example:
            >>> removed = bridge.unregister_workflow_skill("multi-agent-analysis")
            >>> print(removed)
            True
        """
        # Convert workflow name to skill name format
        skill_name = workflow_name.upper().replace("-", "_")

        # Unregister from registry
        unregistered = self.registry.unregister_skill(skill_name)

        # Remove from tracking set
        if unregistered:
            self._registered_workflow_skills.discard(skill_name)

        return unregistered

    def get_registered_workflow_skills(self) -> list[SkillDefinition]:
        """
        Get all Symphony workflow skills currently registered.

        Returns:
            List of SkillDefinition objects for Symphony workflows

        Example:
            >>> workflow_skills = bridge.get_registered_workflow_skills()
            >>> for skill in workflow_skills:
            ...     print(skill.name)
        """
        # Get skills from tracking set
        workflow_skills: list[SkillDefinition] = []

        for skill_name in self._registered_workflow_skills:
            skill = self.registry.get_skill(skill_name)
            if skill is not None:
                workflow_skills.append(skill)

        return workflow_skills

    def is_workflow_registered(self, workflow_name: str) -> bool:
        """
        Check if a Symphony workflow is registered as a skill.

        Args:
            workflow_name: Name of the Symphony workflow

        Returns:
            True if workflow is registered as a skill

        Example:
            >>> registered = bridge.is_workflow_registered("multi-agent-analysis")
            >>> print(registered)
            True
        """
        # Convert workflow name to skill name format
        skill_name = workflow_name.upper().replace("-", "_")

        # Check if skill exists
        skill = self.registry.get_skill(skill_name)
        return skill is not None

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

    async def execute_workflow_skill(
        self,
        workflow_name: str,
        task: str,
        workdir: Union[str, Path],
        agent_type: Optional[str] = None,
        agent_config: Optional[AgentConfig] = None,
        context_files: Optional[list[Path]] = None,
        context_text: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SymphonyBridgeResult:
        """
        Execute a Symphony workflow through the standard skill execution flow.

        This method demonstrates the complete workflow-to-skill translation:
        1. The workflow is registered as a virtual skill
        2. The skill is executed through the standard SkillExecutor
        3. Results are returned in a SymphonyBridgeResult

        This differs from execute_workflow_as_skill() by using the standard
        skill execution path rather than directly invoking the adapter.

        Args:
            workflow_name: Name of the Symphony workflow
            task: Task description
            workdir: Working directory for execution
            agent_type: Optional preferred agent type (defaults to "symphony")
            agent_config: Optional agent configuration overrides
            context_files: Optional files to include as context
            context_text: Optional additional context text
            session_id: Optional session ID for resume
            timeout_seconds: Optional timeout override
            metadata: Optional execution metadata

        Returns:
            SymphonyBridgeResult with status and output

        Raises:
            SymphonyBridgeError: If workflow not registered or execution fails

        Example:
            >>> # Register workflow as skill
            >>> bridge.register_workflow_as_skill(
            ...     workflow_name="multi-agent-analysis",
            ...     workflow_description="Analyzes code using multiple agents"
            ... )
            >>>
            >>> # Execute through standard skill flow
            >>> result = await bridge.execute_workflow_skill(
            ...     workflow_name="multi-agent-analysis",
            ...     task="Analyze the codebase",
            ...     workdir="/path/to/project"
            ... )
            >>> if result.success:
            ...     print(result.output)
        """
        # Convert workflow name to skill name format
        skill_name = workflow_name.upper().replace("-", "_")

        # Create result object
        result = SymphonyBridgeResult(
            operation_type="workflow_as_skill",
            metadata=metadata or {},
        )
        result.status = SymphonyBridgeStatus.RUNNING

        try:
            # Check if workflow is registered as a skill
            skill = self.registry.get_skill(skill_name)
            if skill is None:
                raise SymphonyBridgeError(
                    f"Workflow '{workflow_name}' is not registered as a skill. "
                    f"Call register_workflow_as_skill('{workflow_name}') first."
                )

            # Execute through standard skill executor
            skill_result = await self._executor.execute_skill(
                skill_name=skill_name,
                task=task,
                workdir=workdir,
                agent_type=agent_type or "symphony",
                agent_config=agent_config,
                context_files=context_files,
                context_text=context_text,
                session_id=session_id,
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

        except SymphonyBridgeError:
            raise
        except Exception as e:
            result.mark_complete(
                status=SymphonyBridgeStatus.ERROR,
                error=f"Workflow skill execution failed: {str(e)}",
            )
            raise SymphonyBridgeError(
                f"Workflow skill execution failed: {e}"
            ) from e

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
        context_files: Optional[list[Path]] = None,
    ) -> str:
        """
        Build the full prompt for workflow execution.

        Translates skill execution context into Symphony workflow prompt format.
        This is the core context mapping logic for the translation layer.

        Args:
            workflow_name: Name of the Symphony workflow
            task: Task description
            context_text: Optional additional context text
            context_files: Optional files to include as context

        Returns:
            Complete prompt string formatted for Symphony workflow execution
        """
        parts: list[str] = []

        # Add workflow identifier with execution context
        parts.append(f"## Symphony Workflow Execution\n")
        parts.append(f"**Workflow:** {workflow_name}\n")
        parts.append(f"**Execution Mode:** Autoflow Skill Bridge\n")

        # Add separator
        parts.append("\n---\n")

        # Add context text if provided
        if context_text:
            parts.append(f"## Execution Context\n\n{context_text}\n")
            parts.append("\n---\n")

        # Add task as primary objective
        parts.append(f"## Task Objective\n\n{task}")

        # Add file context if provided
        if context_files:
            parts.append("\n\n## Context Files\n")
            parts.append(
                "The following files are provided as context for this workflow execution:\n"
            )
            for file_path in context_files:
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"\n### {file_path}\n")
                    parts.append(f"```\n{content}\n```")
                except Exception as e:
                    parts.append(f"\n### {file_path}\n")
                    parts.append(f"**Error reading file:** {e}")

        # Add execution instructions for Symphony
        parts.append("\n\n## Execution Instructions\n")
        parts.append(
            "Execute the Symphony workflow with the provided task and context. "
            "The workflow should leverage its multi-agent coordination capabilities "
            "to complete the task while respecting the provided context and constraints.\n"
        )

        return "\n".join(parts)

    # === State Synchronization Methods ===

    def sync_checkpoint_to_run(
        self,
        checkpoint_id: str,
        run_id: str,
        checkpoint_data: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Synchronize Symphony checkpoint state to Autoflow run.

        Maps Symphony checkpoint information to Autoflow run state,
        storing checkpoint metadata in the run's metadata field.

        Args:
            checkpoint_id: Symphony checkpoint identifier
            run_id: Autoflow run identifier
            checkpoint_data: Optional checkpoint data to store

        Returns:
            True if synchronization successful, False otherwise

        Raises:
            SymphonyBridgeError: If state manager not initialized or sync fails

        Example:
            >>> success = bridge.sync_checkpoint_to_run(
            ...     checkpoint_id="symphony-checkpoint-123",
            ...     run_id="autoflow-run-456",
            ...     checkpoint_data={"step": "analysis", "status": "complete"}
            ... )
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # Load current run data
            run_data = self._state_manager.load_run(run_id)
            if run_data is None:
                return False

            # Initialize metadata if needed
            if "metadata" not in run_data:
                run_data["metadata"] = {}

            # Store checkpoint information
            checkpoint_info = {
                "checkpoint_id": checkpoint_id,
                "synced_at": datetime.utcnow().isoformat(),
            }
            if checkpoint_data:
                checkpoint_info["checkpoint_data"] = checkpoint_data

            run_data["metadata"]["symphony_checkpoint"] = checkpoint_info

            # Update run status based on checkpoint if available
            if checkpoint_data and "status" in checkpoint_data:
                # Map checkpoint status to run status
                checkpoint_status = checkpoint_data["status"]
                if checkpoint_status == "complete":
                    run_data["status"] = RunStatus.COMPLETED.value
                elif checkpoint_status == "failed":
                    run_data["status"] = RunStatus.FAILED.value
                elif checkpoint_status == "running":
                    run_data["status"] = RunStatus.RUNNING.value

            # Save updated run data
            self._state_manager.save_run(run_id, run_data)
            return True

        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to sync checkpoint to run: {e}"
            ) from e

    def sync_run_to_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        run_data_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Synchronize Autoflow run state to Symphony checkpoint format.

        Extracts relevant run information and formats it for Symphony
        checkpoint consumption.

        Args:
            run_id: Autoflow run identifier
            checkpoint_id: Symphony checkpoint identifier
            run_data_override: Optional run data to use instead of loading

        Returns:
            Dictionary containing run state formatted for Symphony checkpoint

        Raises:
            SymphonyBridgeError: If state manager not initialized or sync fails

        Example:
            >>> checkpoint_data = bridge.sync_run_to_checkpoint(
            ...     run_id="autoflow-run-456",
            ...     checkpoint_id="symphony-checkpoint-123"
            ... )
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # Load run data if not provided
            if run_data_override is None:
                run_data = self._state_manager.load_run(run_id)
                if run_data is None:
                    raise SymphonyBridgeError(f"Run not found: {run_id}")
            else:
                run_data = run_data_override

            # Build checkpoint data from run state
            checkpoint_data = {
                "checkpoint_id": checkpoint_id,
                "run_id": run_id,
                "synced_at": datetime.utcnow().isoformat(),
                "run_status": run_data.get("status"),
                "agent": run_data.get("agent"),
                "started_at": run_data.get("started_at"),
                "completed_at": run_data.get("completed_at"),
                "duration_seconds": run_data.get("duration_seconds"),
                "output": run_data.get("output"),
                "error": run_data.get("error"),
            }

            # Include metadata if present
            if "metadata" in run_data:
                checkpoint_data["run_metadata"] = run_data["metadata"]

            return checkpoint_data

        except SymphonyBridgeError:
            raise
        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to sync run to checkpoint: {e}"
            ) from e

    def get_run_from_checkpoint(
        self,
        checkpoint_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Find Autoflow run associated with a Symphony checkpoint.

        Searches through runs to find one with matching checkpoint ID
        in its metadata.

        Args:
            checkpoint_id: Symphony checkpoint identifier

        Returns:
            Run data dictionary if found, None otherwise

        Raises:
            SymphonyBridgeError: If state manager not initialized

        Example:
            >>> run = bridge.get_run_from_checkpoint("symphony-checkpoint-123")
            >>> if run:
            ...     print(f"Found run: {run['id']}")
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # List all runs and search for checkpoint match
            runs = self._state_manager.list_runs()
            for run in runs:
                metadata = run.get("metadata", {})
                checkpoint_info = metadata.get("symphony_checkpoint", {})
                if checkpoint_info.get("checkpoint_id") == checkpoint_id:
                    return run
            return None

        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to find run from checkpoint: {e}"
            ) from e

    def get_checkpoint_from_run(
        self,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Get Symphony checkpoint information associated with a run.

        Extracts checkpoint metadata from the run's metadata field.

        Args:
            run_id: Autoflow run identifier

        Returns:
            Checkpoint information dict if found, None otherwise

        Raises:
            SymphonyBridgeError: If state manager not initialized

        Example:
            >>> checkpoint = bridge.get_checkpoint_from_run("autoflow-run-456")
            >>> if checkpoint:
            ...     print(f"Checkpoint ID: {checkpoint['checkpoint_id']}")
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # Load run data
            run_data = self._state_manager.load_run(run_id)
            if run_data is None:
                return None

            # Extract checkpoint info from metadata
            metadata = run_data.get("metadata", {})
            checkpoint_info = metadata.get("symphony_checkpoint")

            return checkpoint_info

        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to get checkpoint from run: {e}"
            ) from e

    def _save_checkpoint_state(
        self,
        run_id: str,
        checkpoint_id: str,
        checkpoint_state: dict[str, Any],
    ) -> None:
        """
        Save checkpoint state to run metadata.

        Internal method for persisting checkpoint state information
        within a run's metadata field.

        Args:
            run_id: Autoflow run identifier
            checkpoint_id: Symphony checkpoint identifier
            checkpoint_state: Checkpoint state data to save

        Raises:
            SymphonyBridgeError: If state manager not initialized or save fails
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # Load current run data
            run_data = self._state_manager.load_run(run_id)
            if run_data is None:
                raise SymphonyBridgeError(f"Run not found: {run_id}")

            # Initialize metadata if needed
            if "metadata" not in run_data:
                run_data["metadata"] = {}

            # Save checkpoint state
            run_data["metadata"]["symphony_checkpoint_state"] = {
                "checkpoint_id": checkpoint_id,
                "state": checkpoint_state,
                "saved_at": datetime.utcnow().isoformat(),
            }

            # Save updated run
            self._state_manager.save_run(run_id, run_data)

        except SymphonyBridgeError:
            raise
        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to save checkpoint state: {e}"
            ) from e

    def _load_checkpoint_state(
        self,
        run_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Load checkpoint state from run metadata.

        Internal method for retrieving checkpoint state information
        from a run's metadata field.

        Args:
            run_id: Autoflow run identifier

        Returns:
            Checkpoint state dict if found, None otherwise

        Raises:
            SymphonyBridgeError: If state manager not initialized or load fails
        """
        if self._state_manager is None:
            raise SymphonyBridgeError(
                "State manager not initialized. Provide state_dir parameter."
            )

        try:
            # Load run data
            run_data = self._state_manager.load_run(run_id)
            if run_data is None:
                return None

            # Extract checkpoint state from metadata
            metadata = run_data.get("metadata", {})
            checkpoint_state_info = metadata.get("symphony_checkpoint_state")

            return checkpoint_state_info

        except Exception as e:
            raise SymphonyBridgeError(
                f"Failed to load checkpoint state: {e}"
            ) from e

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
