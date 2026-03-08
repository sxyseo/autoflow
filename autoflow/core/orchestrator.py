"""
Autoflow Orchestrator Module

Provides core orchestration for autonomous AI development with OpenClaw
integration. Coordinates multiple agents, skills execution, and implements
the closed-loop development cycle (discover→fix→document→code→test→refactor→commit).

Usage:
    from autoflow.core.orchestrator import AutoflowOrchestrator

    orchestrator = AutoflowOrchestrator()
    await orchestrator.initialize()

    # Run a task with skill-based execution
    result = await orchestrator.run_task(
        task="Fix the bug in app.py",
        skill_name="IMPLEMENTER"
    )

    # Run continuous iteration cycle
    await orchestrator.run_continuous_iteration()
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from autoflow.agents.base import (
    AgentAdapter,
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
    ResumeMode,
)
from autoflow.agents.claude_code import ClaudeCodeAdapter
from autoflow.agents.codex import CodexAdapter
from autoflow.agents.openclaw import OpenClawAdapter, SpawnResult
from autoflow.agents.symphony import SymphonyAdapter
from autoflow.core.config import Config, load_config
from autoflow.core.state import (
    Run,
    RunStatus,
    StateManager,
    Task,
    TaskStatus,
)
from autoflow.skills.executor import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillExecutor,
)
from autoflow.skills.registry import SkillRegistry
from autoflow.tmux.manager import TmuxManager
from autoflow.tmux.session import SessionStatus, TmuxSession


class OrchestratorStatus(str, Enum):
    """Status of the orchestrator."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    SYMPHONY_WORKFLOW = "symphony_workflow"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class CyclePhase(str, Enum):
    """Phases in the closed-loop development cycle."""

    DISCOVER = "discover"
    FIX = "fix"
    DOCUMENT = "document"
    CODE = "code"
    TEST = "test"
    REFACTOR = "refactor"
    COMMIT = "commit"


class OrchestratorError(Exception):
    """Exception raised for orchestrator errors."""

    def __init__(self, message: str, phase: Optional[CyclePhase] = None):
        self.phase = phase
        super().__init__(message)


@dataclass
class CycleResult:
    """
    Result from a single iteration cycle.

    Attributes:
        cycle_id: Unique identifier for this cycle
        phase: Current phase in the cycle
        success: Whether the cycle completed successfully
        task_result: Result from task execution
        test_result: Result from testing phase
        commit_result: Result from commit phase
        started_at: When the cycle started
        completed_at: When the cycle completed
        duration_seconds: Total cycle duration
        error: Error message if any
        metadata: Additional metadata
    """

    cycle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    phase: CyclePhase = CyclePhase.DISCOVER
    success: bool = False
    task_result: Optional[SkillExecutionResult] = None
    test_result: Optional[ExecutionResult] = None
    commit_result: Optional[ExecutionResult] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Mark the cycle as complete."""
        self.success = success
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()


class OrchestratorStats(BaseModel):
    """Statistics about orchestrator runs."""

    total_cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_commits: int = 0
    average_cycle_duration: float = 0.0
    last_cycle_at: Optional[datetime] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class AutoflowOrchestrator:
    """
    Core orchestrator for autonomous AI development.

    Coordinates multiple AI agents through OpenClaw integration to execute
    the closed-loop development cycle:
    - Discover issues
    - Fix code
    - Document changes
    - Test and verify
    - Refactor if needed
    - Commit changes

    The orchestrator integrates:
    - OpenClaw for sub-agent spawning via sessions_spawn
    - Symphony for multi-agent orchestration
    - SkillExecutor for skill-based task execution
    - TmuxManager for background session management
    - StateManager for persistent state

    Example:
        >>> orchestrator = AutoflowOrchestrator()
        >>> await orchestrator.initialize()
        >>>
        >>> # Run a single task
        >>> result = await orchestrator.run_task(
        ...     task="Implement the login feature",
        ...     skill_name="IMPLEMENTER"
        ... )
        >>>
        >>> # Start continuous iteration
        >>> await orchestrator.start_continuous_iteration()

    Attributes:
        config: Configuration object
        state: StateManager instance
        skill_executor: SkillExecutor instance
        tmux_manager: TmuxManager instance
        openclaw_adapter: OpenClaw adapter for sub-agent spawning
    """

    DEFAULT_CYCLE_TIMEOUT = 120  # 2 minutes per cycle
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 5.0

    def __init__(
        self,
        config: Optional[Config] = None,
        state_dir: Optional[Union[str, Path]] = None,
        skills_dir: Optional[Union[str, Path]] = None,
        auto_initialize: bool = False,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            config: Optional configuration object
            state_dir: Optional state directory path
            skills_dir: Optional skills directory path
            auto_initialize: If True, initialize on creation
        """
        self._config = config
        self._state_dir = Path(state_dir) if state_dir else None
        self._skills_dir = Path(skills_dir) if skills_dir else None

        # Status tracking
        self._status = OrchestratorStatus.IDLE
        self._current_task: Optional[Task] = None
        self._current_cycle: Optional[CycleResult] = None

        # Components (initialized lazily)
        self._state: Optional[StateManager] = None
        self._skill_registry: Optional[SkillRegistry] = None
        self._skill_executor: Optional[SkillExecutor] = None
        self._tmux_manager: Optional[TmuxManager] = None
        self._openclaw_adapter: Optional[OpenClawAdapter] = None
        self._adapters: dict[str, AgentAdapter] = {}

        # Statistics
        self._stats = OrchestratorStats()

        # Background task tracking
        self._continuous_task: Optional[asyncio.Task] = None
        self._running = False

        if auto_initialize:
            asyncio.create_task(self.initialize())

    @property
    def config(self) -> Config:
        """Get configuration, loading if needed."""
        if self._config is None:
            self._config = load_config()
        return self._config

    @property
    def state(self) -> StateManager:
        """Get state manager, creating if needed."""
        if self._state is None:
            state_dir = self._state_dir or self.config.state_dir
            self._state = StateManager(state_dir)
            self._state.initialize()
        return self._state

    @property
    def skill_registry(self) -> SkillRegistry:
        """Get skill registry, creating if needed."""
        if self._skill_registry is None:
            skills_dirs = []
            if self._skills_dir:
                skills_dirs.append(self._skills_dir)
            skills_dirs.extend(self.config.openclaw.extra_dirs)
            self._skill_registry = SkillRegistry(
                skills_dirs=skills_dirs,
                auto_load=True,
            )
        return self._skill_registry

    @property
    def skill_executor(self) -> SkillExecutor:
        """Get skill executor, creating if needed."""
        if self._skill_executor is None:
            self._skill_executor = SkillExecutor(
                registry=self.skill_registry,
            )
            # Register available adapters
            for name, adapter in self._get_available_adapters().items():
                self._skill_executor.register_adapter(name, adapter)
        return self._skill_executor

    @property
    def tmux_manager(self) -> TmuxManager:
        """Get tmux manager, creating if needed."""
        if self._tmux_manager is None:
            self._tmux_manager = TmuxManager(
                max_concurrent=self.config.scheduler.enabled and 5 or 3,
            )
        return self._tmux_manager

    @property
    def openclaw_adapter(self) -> OpenClawAdapter:
        """Get OpenClaw adapter, creating if needed."""
        if self._openclaw_adapter is None:
            self._openclaw_adapter = OpenClawAdapter(
                gateway_url=self.config.openclaw.gateway_url,
            )
        return self._openclaw_adapter

    @property
    def status(self) -> OrchestratorStatus:
        """Get current orchestrator status."""
        return self._status

    @property
    def stats(self) -> OrchestratorStats:
        """Get orchestrator statistics."""
        return self._stats

    def _get_available_adapters(self) -> dict[str, AgentAdapter]:
        """
        Get dictionary of available agent adapters.

        Returns:
            Dictionary mapping adapter names to instances
        """
        if not self._adapters:
            # Claude Code adapter
            try:
                self._adapters["claude-code"] = ClaudeCodeAdapter(
                    default_timeout=self.config.agents.claude_code.timeout_seconds,
                )
            except Exception:
                pass

            # Codex adapter
            try:
                self._adapters["codex"] = CodexAdapter(
                    default_timeout=self.config.agents.codex.timeout_seconds,
                )
            except Exception:
                pass

            # OpenClaw adapter
            try:
                self._adapters["openclaw"] = self.openclaw_adapter
            except Exception:
                pass

            # Symphony adapter
            try:
                self._adapters["symphony"] = SymphonyAdapter(
                    default_timeout=self.config.symphony.timeout_seconds,
                )
            except Exception:
                pass

        return self._adapters

    async def initialize(self) -> None:
        """
        Initialize the orchestrator and all components.

        This method:
        1. Initializes state management
        2. Loads skills from registry
        3. Sets up agent adapters
        4. Prepares tmux for background execution

        Raises:
            OrchestratorError: If initialization fails
        """
        self._status = OrchestratorStatus.INITIALIZING

        try:
            # Initialize state
            self.state.initialize()

            # Pre-load skills
            _ = self.skill_registry

            # Check adapters
            adapters = self._get_available_adapters()
            if not adapters:
                raise OrchestratorError(
                    "No agent adapters available. "
                    "Please ensure Claude Code, Codex, OpenClaw, or Symphony is installed."
                )

            # Check tmux availability (non-blocking)
            if not await TmuxManager.check_tmux_available():
                # Log warning but continue - tmux is optional for sync execution
                pass

            self._status = OrchestratorStatus.IDLE

        except Exception as e:
            self._status = OrchestratorStatus.ERROR
            raise OrchestratorError(f"Initialization failed: {e}") from e

    async def run_task(
        self,
        task: str,
        skill_name: str = "IMPLEMENTER",
        workdir: Optional[Union[str, Path]] = None,
        agent_type: Optional[str] = None,
        context_files: Optional[list[Path]] = None,
        context_text: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        use_tmux: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SkillExecutionResult:
        """
        Run a single task with skill-based execution.

        Executes a task using the specified skill and agent. Can run
        synchronously or in a tmux session for background execution.

        Args:
            task: Task description
            skill_name: Name of the skill to use
            workdir: Working directory (defaults to current)
            agent_type: Preferred agent type
            context_files: Files to include as context
            context_text: Additional context text
            timeout_seconds: Execution timeout
            use_tmux: If True, run in tmux session
            metadata: Additional metadata

        Returns:
            SkillExecutionResult with status and output

        Raises:
            OrchestratorError: If task execution fails

        Example:
            >>> result = await orchestrator.run_task(
            ...     task="Fix the bug in app.py",
            ...     skill_name="IMPLEMENTER"
            ... )
            >>> if result.success:
            ...     print("Task completed!")
        """
        self._status = OrchestratorStatus.RUNNING

        # Create task record
        task_id = str(uuid.uuid4())[:8]
        task_record = Task(
            id=task_id,
            title=task[:100],  # Truncate for title
            description=task,
            status=TaskStatus.IN_PROGRESS,
            metadata=metadata or {},
        )

        # Create run record
        run_id = str(uuid.uuid4())[:8]
        run_record = Run(
            id=run_id,
            task_id=task_id,
            agent=agent_type or "claude-code",
            status=RunStatus.STARTED,
            workdir=str(workdir or Path.cwd()),
        )

        # Save initial state
        self.state.save_task(task_id, task_record.model_dump())
        self.state.save_run(run_id, run_record.model_dump())

        self._current_task = task_record
        self._stats.total_tasks += 1

        try:
            # Execute via skill executor
            result = await self.skill_executor.execute_skill(
                skill_name=skill_name,
                task=task,
                workdir=workdir or Path.cwd(),
                agent_type=agent_type,
                context_files=context_files,
                context_text=context_text,
                timeout_seconds=timeout_seconds or self.DEFAULT_CYCLE_TIMEOUT,
                metadata=metadata,
            )

            # Update task status
            if result.success:
                task_record.status = TaskStatus.COMPLETED
                run_record.complete(
                    status=RunStatus.COMPLETED,
                    output=result.output,
                )
                self._stats.completed_tasks += 1
            else:
                task_record.status = TaskStatus.FAILED
                run_record.complete(
                    status=RunStatus.FAILED,
                    error=result.error,
                )
                self._stats.failed_tasks += 1

            # Update state
            self.state.save_task(task_id, task_record.model_dump())
            self.state.save_run(run_id, run_record.model_dump())

            return result

        except Exception as e:
            task_record.status = TaskStatus.FAILED
            run_record.complete(
                status=RunStatus.FAILED,
                error=str(e),
            )
            self.state.save_task(task_id, task_record.model_dump())
            self.state.save_run(run_id, run_record.model_dump())
            self._stats.failed_tasks += 1
            raise OrchestratorError(f"Task execution failed: {e}") from e

        finally:
            self._status = OrchestratorStatus.IDLE
            self._current_task = None

    async def spawn_subagent(
        self,
        task: str,
        label: str,
        agent_id: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 300,
        workdir: Optional[Union[str, Path]] = None,
    ) -> SpawnResult:
        """
        Spawn a sub-agent via OpenClaw sessions_spawn.

        This allows spawning isolated sub-agents with their own context,
        useful for parallel work with lower token cost than CLI-based
        orchestration.

        Args:
            task: Task description for the sub-agent
            label: Label for logging and UI purposes
            agent_id: Optional agent ID to spawn under
            model: Optional model override
            timeout_seconds: Timeout for the sub-agent run
            workdir: Working directory for the sub-agent

        Returns:
            SpawnResult with session_id, run_id, and status

        Raises:
            OrchestratorError: If spawn fails

        Example:
            >>> result = await orchestrator.spawn_subagent(
            ...     task="Implement the login feature",
            ...     label="login-impl",
            ...     timeout_seconds=600
            ... )
            >>> print(result.session_id)
        """
        try:
            return await self.openclaw_adapter.spawn_subagent(
                task=task,
                label=label,
                agent_id=agent_id,
                model=model,
                timeout_seconds=timeout_seconds,
                workdir=workdir,
            )
        except Exception as e:
            raise OrchestratorError(f"Failed to spawn sub-agent: {e}") from e

    async def spawn_acp_agent(
        self,
        task: str,
        agent_id: str,
        thread: bool = True,
    ) -> SpawnResult:
        """
        Spawn an ACP runtime agent (e.g., Codex) via OpenClaw.

        This allows spawning external agents like Codex CLI through
        OpenClaw's ACP runtime path.

        Args:
            task: Task description for the agent
            agent_id: Agent ID for the ACP agent
            thread: Whether to thread the session

        Returns:
            SpawnResult with session_id, run_id, and status

        Raises:
            OrchestratorError: If spawn fails
        """
        try:
            return await self.openclaw_adapter.spawn_acp_agent(
                task=task,
                agent_id=agent_id,
                thread=thread,
            )
        except Exception as e:
            raise OrchestratorError(f"Failed to spawn ACP agent: {e}") from e

    async def run_symphony_workflow(
        self,
        task: str,
        workdir: Optional[Union[str, Path]] = None,
        timeout_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        resume_session_id: Optional[str] = None,
    ) -> ExecutionResult:
        """
        Run a Symphony multi-agent workflow.

        Executes a task using Symphony's multi-agent orchestration framework.
        This allows coordinating multiple specialized agents to work on complex
        tasks collaboratively or independently.

        Args:
            task: Task description or workflow prompt
            workdir: Working directory (defaults to current)
            timeout_seconds: Execution timeout (defaults to config)
            metadata: Additional metadata for tracking
            resume_session_id: Optional session ID to resume previous workflow

        Returns:
            ExecutionResult with status, output, and session info

        Raises:
            OrchestratorError: If workflow execution fails

        Example:
            >>> result = await orchestrator.run_symphony_workflow(
            ...     task="Implement the login feature with tests",
            ...     timeout_seconds=600
            ... )
            >>> if result.success:
            ...     print(f"Workflow completed: {result.session_id}")
        """
        self._status = OrchestratorStatus.SYMPHONY_WORKFLOW

        # Create task record
        task_id = str(uuid.uuid4())[:8]
        task_record = Task(
            id=task_id,
            title=task[:100],  # Truncate for title
            description=task,
            status=TaskStatus.IN_PROGRESS,
            metadata=metadata or {},
        )

        # Create run record
        run_id = str(uuid.uuid4())[:8]
        run_record = Run(
            id=run_id,
            task_id=task_id,
            agent="symphony",
            status=RunStatus.STARTED,
            workdir=str(workdir or Path.cwd()),
        )

        # Save initial state
        self.state.save_task(task_id, task_record.model_dump())
        self.state.save_run(run_id, run_record.model_dump())

        self._current_task = task_record
        self._stats.total_tasks += 1

        try:
            # Get Symphony adapter
            adapters = self._get_available_adapters()
            if "symphony" not in adapters:
                raise OrchestratorError(
                    "Symphony adapter not available. "
                    "Please ensure Symphony CLI is installed."
                )

            symphony_adapter = adapters["symphony"]

            # Create agent config
            config = AgentConfig(
                command="symphony",
                args=["agent", "run"],
                timeout_seconds=timeout_seconds or self.config.symphony.timeout_seconds,
                metadata=metadata or {},
            )

            # Execute or resume workflow
            if resume_session_id:
                # Resume existing session
                result = await symphony_adapter.resume(
                    session_id=resume_session_id,
                    new_prompt=task,
                    config=config,
                )
            else:
                # Start new workflow
                result = await symphony_adapter.execute(
                    prompt=task,
                    workdir=workdir or Path.cwd(),
                    config=config,
                )

            # Update task and run status based on result
            if result.success:
                task_record.status = TaskStatus.COMPLETED
                run_record.complete(
                    status=RunStatus.COMPLETED,
                    output=result.output,
                )
                self._stats.completed_tasks += 1
            else:
                task_record.status = TaskStatus.FAILED
                run_record.complete(
                    status=RunStatus.FAILED,
                    error=result.error,
                )
                self._stats.failed_tasks += 1

            # Update state
            self.state.save_task(task_id, task_record.model_dump())
            self.state.save_run(run_id, run_record.model_dump())

            return result

        except Exception as e:
            task_record.status = TaskStatus.FAILED
            run_record.complete(
                status=RunStatus.FAILED,
                error=str(e),
            )
            self.state.save_task(task_id, task_record.model_dump())
            self.state.save_run(run_id, run_record.model_dump())
            self._stats.failed_tasks += 1
            raise OrchestratorError(f"Symphony workflow execution failed: {e}") from e

        finally:
            self._status = OrchestratorStatus.IDLE
            self._current_task = None

    async def run_cycle(
        self,
        task: str,
        workdir: Optional[Union[str, Path]] = None,
        auto_commit: bool = True,
        run_tests: bool = True,
    ) -> CycleResult:
        """
        Run a single closed-loop development cycle.

        Executes the full cycle: discover→fix→document→code→test→refactor→commit

        Args:
            task: Task description
            workdir: Working directory
            auto_commit: If True, automatically commit on success
            run_tests: If True, run tests before committing

        Returns:
            CycleResult with cycle status and results

        Example:
            >>> result = await orchestrator.run_cycle(
            ...     task="Fix the authentication bug",
            ...     auto_commit=True
            ... )
            >>> if result.success:
            ...     print(f"Cycle completed in {result.duration_seconds}s")
        """
        cycle = CycleResult()
        self._current_cycle = cycle
        self._stats.total_cycles += 1

        try:
            # Phase 1: Discover
            cycle.phase = CyclePhase.DISCOVER
            discover_result = await self.run_task(
                task=f"Analyze and understand: {task}",
                skill_name="CONTINUOUS_ITERATOR",
                workdir=workdir,
                context_text="Focus on understanding the problem scope.",
            )
            if not discover_result.success:
                raise OrchestratorError(
                    "Discovery phase failed",
                    phase=CyclePhase.DISCOVER,
                )

            # Phase 2: Code/Fix
            cycle.phase = CyclePhase.CODE
            code_result = await self.run_task(
                task=task,
                skill_name="IMPLEMENTER",
                workdir=workdir,
            )
            cycle.task_result = code_result
            if not code_result.success:
                raise OrchestratorError(
                    "Implementation phase failed",
                    phase=CyclePhase.CODE,
                )

            # Phase 3: Test
            if run_tests:
                cycle.phase = CyclePhase.TEST
                test_result = await self._run_tests(workdir)
                cycle.test_result = test_result
                if not test_result.success:
                    # Try to fix tests
                    cycle.phase = CyclePhase.FIX
                    fix_result = await self.run_task(
                        task=f"Fix failing tests: {test_result.error}",
                        skill_name="IMPLEMENTER",
                        workdir=workdir,
                    )
                    if not fix_result.success:
                        raise OrchestratorError(
                            "Test fix phase failed",
                            phase=CyclePhase.FIX,
                        )

            # Phase 4: Document
            cycle.phase = CyclePhase.DOCUMENT
            doc_result = await self.run_task(
                task=f"Document changes made for: {task}",
                skill_name="IMPLEMENTER",
                workdir=workdir,
                context_text="Update relevant documentation.",
            )
            # Document failures are non-blocking

            # Phase 5: Commit
            if auto_commit:
                cycle.phase = CyclePhase.COMMIT
                commit_result = await self._commit_changes(workdir, task)
                cycle.commit_result = commit_result
                if commit_result.success:
                    self._stats.total_commits += 1

            # Success
            cycle.mark_complete(success=True)
            self._stats.successful_cycles += 1
            self._stats.last_cycle_at = datetime.utcnow()

        except OrchestratorError as e:
            cycle.mark_complete(success=False, error=str(e))
            self._stats.failed_cycles += 1
            raise

        except Exception as e:
            cycle.mark_complete(success=False, error=str(e))
            self._stats.failed_cycles += 1
            raise OrchestratorError(f"Cycle failed: {e}") from e

        finally:
            self._current_cycle = None
            self._update_average_cycle_duration(cycle.duration_seconds or 0)

        return cycle

    async def _run_tests(self, workdir: Optional[Union[str, Path]]) -> ExecutionResult:
        """
        Run tests in the project.

        Args:
            workdir: Working directory

        Returns:
            ExecutionResult with test status
        """
        # Check for test commands in CI config
        test_command = None
        for gate in self.config.ci.gates:
            if gate.type == "test":
                test_command = gate.command
                break

        if not test_command:
            # Default test command
            test_command = "pytest tests/ -v"

        result = ExecutionResult(status=ExecutionStatus.SUCCESS)

        try:
            process = await asyncio.create_subprocess_shell(
                test_command,
                cwd=str(workdir or Path.cwd()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60,
            )

            result.mark_complete(
                status=(
                    ExecutionStatus.SUCCESS
                    if process.returncode == 0
                    else ExecutionStatus.FAILURE
                ),
                exit_code=process.returncode,
                output=stdout.decode("utf-8") if stdout else None,
                error=stderr.decode("utf-8") if stderr else None,
            )

        except asyncio.TimeoutError:
            result.mark_complete(
                status=ExecutionStatus.TIMEOUT,
                error="Test execution timed out",
            )
        except Exception as e:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                error=str(e),
            )

        return result

    async def _commit_changes(
        self,
        workdir: Optional[Union[str, Path]],
        message: str,
    ) -> ExecutionResult:
        """
        Commit changes to git.

        Args:
            workdir: Working directory
            message: Commit message

        Returns:
            ExecutionResult with commit status
        """
        result = ExecutionResult(status=ExecutionStatus.SUCCESS)

        try:
            workdir_path = Path(workdir or Path.cwd())

            # Stage all changes
            stage_process = await asyncio.create_subprocess_exec(
                "git", "add", "-A",
                cwd=str(workdir_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await stage_process.communicate()

            # Check if there are changes to commit
            status_process = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(workdir_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await status_process.communicate()

            if not stdout.decode("utf-8").strip():
                result.mark_complete(
                    status=ExecutionStatus.SUCCESS,
                    output="No changes to commit",
                )
                return result

            # Commit
            commit_process = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", f"autoflow: {message}",
                cwd=str(workdir_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await commit_process.communicate()

            result.mark_complete(
                status=(
                    ExecutionStatus.SUCCESS
                    if commit_process.returncode == 0
                    else ExecutionStatus.FAILURE
                ),
                exit_code=commit_process.returncode,
                output=stdout.decode("utf-8") if stdout else None,
                error=stderr.decode("utf-8") if stderr else None,
            )

        except FileNotFoundError:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                error="Git not found",
            )
        except Exception as e:
            result.mark_complete(
                status=ExecutionStatus.ERROR,
                error=str(e),
            )

        return result

    def _update_average_cycle_duration(self, duration: float) -> None:
        """Update running average of cycle duration."""
        total = self._stats.total_cycles
        current_avg = self._stats.average_cycle_duration
        self._stats.average_cycle_duration = (
            (current_avg * (total - 1) + duration) / total
        )

    async def start_continuous_iteration(
        self,
        workdir: Optional[Union[str, Path]] = None,
        interval_seconds: float = 60.0,
        max_cycles: Optional[int] = None,
        task_source: Optional[str] = None,
    ) -> None:
        """
        Start continuous iteration mode.

        Runs the closed-loop development cycle continuously, looking for
        tasks to execute. This implements the Peter Steinberger model of
        rapid 1-2 minute development cycles.

        Args:
            workdir: Working directory
            interval_seconds: Time between cycles
            max_cycles: Maximum number of cycles (None = unlimited)
            task_source: Optional path to task queue file

        Example:
            >>> await orchestrator.start_continuous_iteration(
            ...     interval_seconds=120,
            ...     max_cycles=10
            ... )
        """
        if self._running:
            return

        self._running = True
        self._status = OrchestratorStatus.RUNNING

        cycle_count = 0

        try:
            while self._running:
                # Check max cycles
                if max_cycles and cycle_count >= max_cycles:
                    break

                # Get next task
                task = await self._get_next_task(task_source)
                if not task:
                    # No tasks available, wait and retry
                    await asyncio.sleep(interval_seconds)
                    continue

                try:
                    # Run cycle
                    result = await self.run_cycle(
                        task=task,
                        workdir=workdir,
                    )

                    cycle_count += 1

                    # Wait before next cycle
                    if self._running:
                        await asyncio.sleep(interval_seconds)

                except OrchestratorError:
                    # Log error and continue
                    await asyncio.sleep(self.DEFAULT_RETRY_DELAY)

        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._status = OrchestratorStatus.STOPPED

    async def stop_continuous_iteration(self) -> None:
        """Stop continuous iteration mode."""
        self._running = False
        self._status = OrchestratorStatus.STOPPING

        if self._continuous_task:
            self._continuous_task.cancel()
            try:
                await self._continuous_task
            except asyncio.CancelledError:
                pass
            self._continuous_task = None

    async def _get_next_task(
        self,
        task_source: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the next task to execute.

        Args:
            task_source: Optional path to task queue file

        Returns:
            Task description or None if no tasks available
        """
        # First, check for pending tasks in state
        pending_tasks = self.state.list_tasks(status=TaskStatus.PENDING)
        if pending_tasks:
            task_data = pending_tasks[0]
            return task_data.get("description") or task_data.get("title")

        # Check task source file if provided
        if task_source:
            task_path = Path(task_source)
            if task_path.exists():
                try:
                    content = task_path.read_text().strip()
                    if content:
                        return content
                except Exception:
                    pass

        return None

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: int = 5,
        labels: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Task:
        """
        Add a new task to the queue.

        Args:
            title: Task title
            description: Detailed task description
            priority: Task priority (1-10, higher = more urgent)
            labels: Optional labels for categorization
            metadata: Additional metadata

        Returns:
            Created Task object

        Example:
            >>> task = orchestrator.add_task(
            ...     title="Fix login bug",
            ...     description="The login form doesn't validate input",
            ...     priority=8,
            ...     labels=["bug", "auth"]
            ... )
        """
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            id=task_id,
            title=title,
            description=description,
            priority=priority,
            labels=labels or [],
            metadata=metadata or {},
        )

        self.state.save_task(task_id, task.model_dump())
        self._stats.total_tasks += 1

        return task

    async def get_status_summary(self) -> dict[str, Any]:
        """
        Get a comprehensive status summary.

        Returns:
            Dictionary with status information
        """
        state_status = self.state.get_status()

        return {
            "orchestrator": {
                "status": self._status.value,
                "running": self._running,
                "current_task": (
                    self._current_task.id if self._current_task else None
                ),
                "current_phase": (
                    self._current_cycle.phase.value
                    if self._current_cycle else None
                ),
            },
            "stats": self._stats.model_dump(),
            "state": state_status,
            "adapters": list(self._get_available_adapters().keys()),
            "skills": self.skill_registry.list_skills(),
        }

    async def cleanup(self) -> None:
        """
        Clean up orchestrator resources.

        Stops continuous iteration and cleans up tmux sessions.
        """
        await self.stop_continuous_iteration()

        if self._tmux_manager:
            await self._tmux_manager.cleanup_all()

        for adapter in self._adapters.values():
            await adapter.cleanup()

    async def __aenter__(self) -> "AutoflowOrchestrator":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"AutoflowOrchestrator("
            f"status={self._status.value}, "
            f"tasks={self._stats.total_tasks}, "
            f"cycles={self._stats.total_cycles})"
        )


def create_orchestrator(
    config_path: Optional[str] = None,
    state_dir: Optional[str] = None,
    auto_initialize: bool = True,
) -> AutoflowOrchestrator:
    """
    Factory function to create a configured orchestrator.

    Args:
        config_path: Optional path to configuration file
        state_dir: Optional state directory path
        auto_initialize: If True, initialize on creation

    Returns:
        Configured AutoflowOrchestrator instance

    Example:
        >>> orchestrator = create_orchestrator(
        ...     config_path="config/settings.json5",
        ...     state_dir=".autoflow"
        ... )
        >>> result = await orchestrator.run_task("Fix the bug")
    """
    config = load_config(config_path) if config_path else None

    return AutoflowOrchestrator(
        config=config,
        state_dir=state_dir,
        auto_initialize=auto_initialize,
    )
