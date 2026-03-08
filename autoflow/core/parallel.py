"""
Autoflow Parallel Coordinator Module

Provides coordination for parallel agent execution with proper resource management,
conflict detection, and result aggregation. Enables multiple AI agents to work
concurrently on independent tasks with isolation and safety guarantees.

Usage:
    from autoflow.core.parallel import ParallelCoordinator

    coordinator = ParallelCoordinator(max_parallel=3)
    await coordinator.initialize()

    # Execute tasks in parallel
    result = await coordinator.execute_parallel(
        tasks=[
            {"task": "Fix bug in app.py", "workdir": "./src"},
            {"task": "Update docs", "workdir": "./docs"},
            {"task": "Add tests", "workdir": "./tests"},
        ]
    )

    # Check results
    for task_id, task_result in result.task_results.items():
        if task_result.success:
            print(f"{task_id}: Success")
        else:
            print(f"{task_id}: Failed - {task_result.error}")
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

from autoflow.agents.base import AgentAdapter, ExecutionResult, ExecutionStatus
from autoflow.core.config import Config, load_config
from autoflow.core.conflict import (
    ConflictReport,
    ConflictSeverity,
    detect_task_conflicts,
)
from autoflow.core.state import (
    ParallelGroupStatus,
    ParallelTaskGroup,
    StateManager,
    Task,
    TaskStatus,
)


class CoordinatorStatus(str, Enum):
    """Status of the parallel coordinator."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    EXECUTING = "executing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ParallelExecutionError(Exception):
    """Exception raised for parallel execution errors."""

    def __init__(self, message: str, task_id: Optional[str] = None):
        self.task_id = task_id
        super().__init__(message)


@dataclass
class ParallelTaskResult:
    """
    Result from a single task in a parallel execution.

    Attributes:
        task_id: Unique identifier for the task
        success: Whether the task completed successfully
        output: Output from the task execution
        error: Error message if the task failed
        started_at: When the task started
        completed_at: When the task completed
        duration_seconds: Task execution duration
        metadata: Additional metadata
    """

    task_id: str
    success: bool = False
    output: Optional[str] = None
    error: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark the task as complete."""
        self.success = success
        self.output = output
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()


@dataclass
class ParallelExecutionResult:
    """
    Result from a parallel execution.

    Attributes:
        group_id: Unique identifier for the task group
        success: Whether the entire group completed successfully
        total_tasks: Total number of tasks in the group
        successful_tasks: Number of tasks that succeeded
        failed_tasks: Number of tasks that failed
        task_results: Dictionary mapping task IDs to their results
        conflict_report: Report of any conflicts detected
        started_at: When the execution started
        completed_at: When the execution completed
        duration_seconds: Total execution duration
        error: Error message if the group execution failed
        metadata: Additional metadata
    """

    group_id: str
    success: bool = False
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    task_results: dict[str, ParallelTaskResult] = field(default_factory=dict)
    conflict_report: Optional[ConflictReport] = None
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
        """Mark the execution as complete."""
        self.success = success
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()

        # Count successful and failed tasks
        self.successful_tasks = sum(
            1 for result in self.task_results.values() if result.success
        )
        self.failed_tasks = sum(
            1 for result in self.task_results.values() if not result.success
        )


class ParallelCoordinatorStats(BaseModel):
    """Statistics about parallel coordinator runs."""

    total_groups: int = 0
    successful_groups: int = 0
    failed_groups: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    average_group_duration: float = 0.0
    last_execution_at: Optional[datetime] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class ParallelCoordinator:
    """
    Coordinator for parallel agent execution.

    Manages concurrent execution of multiple independent tasks with:
    - Resource limiting via semaphores
    - Conflict detection before execution
    - Result aggregation from multiple agents
    - Error isolation (one failure doesn't stop others)
    - State tracking for all parallel executions

    Example:
        >>> coordinator = ParallelCoordinator(max_parallel=3)
        >>> await coordinator.initialize()
        >>>
        >>> # Execute tasks in parallel
        >>> result = await coordinator.execute_parallel(
        ...     tasks=[
        ...         {"task": "Fix bug", "workdir": "./src"},
        ...         {"task": "Update docs", "workdir": "./docs"},
        ...     ]
        ... )
        >>>
        >>> if result.success:
        ...     print(f"Completed {result.successful_tasks} tasks")

    Attributes:
        config: Configuration object
        state: StateManager instance
        max_parallel: Maximum number of concurrent tasks
        stats: Coordinator statistics
    """

    DEFAULT_MAX_PARALLEL = 3
    DEFAULT_TASK_TIMEOUT = 300  # 5 minutes per task
    DEFAULT_CONFLICT_CHECK = True

    def __init__(
        self,
        config: Optional[Config] = None,
        state_dir: Optional[Union[str, Path]] = None,
        max_parallel: Optional[int] = None,
        auto_initialize: bool = False,
    ) -> None:
        """
        Initialize the parallel coordinator.

        Args:
            config: Optional configuration object
            state_dir: Optional state directory path
            max_parallel: Maximum number of concurrent tasks
            auto_initialize: If True, initialize on creation
        """
        self._config = config
        self._state_dir = Path(state_dir) if state_dir else None
        self._max_parallel = max_parallel

        # Status tracking
        self._status = CoordinatorStatus.IDLE
        self._current_group: Optional[ParallelTaskGroup] = None

        # Components (initialized lazily)
        self._state: Optional[StateManager] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

        # Statistics
        self._stats = ParallelCoordinatorStats()

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
    def max_parallel(self) -> int:
        """Get maximum parallel tasks."""
        if self._max_parallel is not None:
            return self._max_parallel
        # Try to get from config
        if hasattr(self.config, "parallel") and self.config.parallel:
            max_par = getattr(self.config.parallel, "max_parallel", None)
            if max_par:
                return max_par
        return self.DEFAULT_MAX_PARALLEL

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Get semaphore for limiting concurrent tasks."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_parallel)
        return self._semaphore

    @property
    def status(self) -> CoordinatorStatus:
        """Get current coordinator status."""
        return self._status

    @property
    def stats(self) -> ParallelCoordinatorStats:
        """Get coordinator statistics."""
        return self._stats

    async def initialize(self) -> None:
        """
        Initialize the parallel coordinator.

        This method:
        1. Initializes state management
        2. Sets up resource limiting
        3. Validates configuration

        Raises:
            ParallelExecutionError: If initialization fails
        """
        self._status = CoordinatorStatus.INITIALIZING

        try:
            # Initialize state
            self.state.initialize()

            self._status = CoordinatorStatus.IDLE

        except Exception as e:
            self._status = CoordinatorStatus.ERROR
            raise ParallelExecutionError(f"Initialization failed: {e}") from e

    async def execute_parallel(
        self,
        tasks: list[dict[str, Any]],
        agent_adapter: Optional[AgentAdapter] = None,
        check_conflicts: bool = True,
        timeout_seconds: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ParallelExecutionResult:
        """
        Execute multiple tasks in parallel.

        Coordinates the concurrent execution of multiple independent tasks with
        proper resource management, conflict detection, and error isolation.

        Args:
            tasks: List of task dictionaries, each containing at least 'task' key
            agent_adapter: Optional agent adapter for execution
            check_conflicts: If True, check for conflicts before execution
            timeout_seconds: Timeout for each task (default: 300)
            metadata: Additional metadata for the execution

        Returns:
            ParallelExecutionResult with aggregated results from all tasks

        Raises:
            ParallelExecutionError: If execution setup fails

        Example:
            >>> result = await coordinator.execute_parallel(
            ...     tasks=[
            ...         {"task": "Fix bug in app.py", "workdir": "./src"},
            ...         {"task": "Update README", "workdir": "./docs"},
            ...         {"task": "Add tests", "workdir": "./tests"},
            ...     ],
            ...     timeout_seconds=600
            ... )
            >>>
            >>> print(f"Completed: {result.successful_tasks}/{result.total_tasks}")
        """
        self._status = CoordinatorStatus.EXECUTING

        # Create result object
        group_id = str(uuid.uuid4())[:8]
        result = ParallelExecutionResult(
            group_id=group_id,
            total_tasks=len(tasks),
            metadata=metadata or {},
        )

        # Create task group
        task_group = ParallelTaskGroup(
            id=group_id,
            title=f"Parallel Group {group_id}",
            description=f"Executing {len(tasks)} tasks in parallel",
            status=ParallelGroupStatus.IN_PROGRESS,
            max_parallel=self.max_parallel,
            metadata=metadata or {},
        )
        self._current_group = task_group

        # Save initial state
        self.state.save_parallel_group(group_id, task_group.model_dump())

        self._stats.total_groups += 1
        self._stats.total_tasks += len(tasks)

        try:
            # Conflict detection
            if check_conflicts:
                conflict_report = detect_task_conflicts(tasks)
                result.conflict_report = conflict_report

                if not conflict_report.safe_to_run:
                    result.mark_complete(
                        success=False,
                        error=f"High-severity conflicts detected: {len(conflict_report.get_high_severity())}",
                    )
                    self._stats.failed_groups += 1
                    return result

            # Execute tasks concurrently
            task_results = await self._execute_tasks_concurrent(
                tasks=tasks,
                agent_adapter=agent_adapter,
                timeout_seconds=timeout_seconds or self.DEFAULT_TASK_TIMEOUT,
            )

            # Aggregate results
            result.task_results = task_results
            result.mark_complete(success=True)

            # Update task group status
            if result.failed_tasks == 0:
                task_group.status = ParallelGroupStatus.COMPLETED
            else:
                task_group.status = ParallelGroupStatus.FAILED

            self._stats.successful_groups += 1
            self._stats.completed_tasks += result.successful_tasks
            self._stats.failed_tasks += result.failed_tasks
            self._stats.last_execution_at = datetime.utcnow()

        except Exception as e:
            result.mark_complete(success=False, error=str(e))
            task_group.status = ParallelGroupStatus.FAILED
            self._stats.failed_groups += 1
            raise ParallelExecutionError(f"Parallel execution failed: {e}") from e

        finally:
            # Save final state
            self.state.save_parallel_group(group_id, task_group.model_dump())
            self._current_group = None
            self._status = CoordinatorStatus.IDLE
            self._update_average_group_duration(result.duration_seconds or 0)

        return result

    async def _execute_tasks_concurrent(
        self,
        tasks: list[dict[str, Any]],
        agent_adapter: Optional[AgentAdapter],
        timeout_seconds: int,
    ) -> dict[str, ParallelTaskResult]:
        """
        Execute tasks concurrently with error isolation.

        Args:
            tasks: List of task dictionaries
            agent_adapter: Optional agent adapter
            timeout_seconds: Timeout per task

        Returns:
            Dictionary mapping task IDs to their results
        """
        task_results: dict[str, ParallelTaskResult] = {}

        async def execute_single_task(
            task_data: dict[str, Any],
            task_id: str,
        ) -> tuple[str, ParallelTaskResult]:
            """Execute a single task with error isolation."""
            task_result = ParallelTaskResult(task_id=task_id)

            try:
                # Use semaphore to limit concurrency
                async with self.semaphore:
                    # If an agent adapter is provided, use it
                    if agent_adapter:
                        execution_result = await agent_adapter.execute(
                            task=task_data.get("task", ""),
                            workdir=task_data.get("workdir"),
                            timeout_seconds=timeout_seconds,
                        )
                        task_result.mark_complete(
                            success=execution_result.status == ExecutionStatus.SUCCESS,
                            output=execution_result.output,
                            error=execution_result.error,
                        )
                    else:
                        # No adapter provided, simulate execution
                        # In production, this would integrate with skill executor
                        await asyncio.sleep(0.1)  # Simulate work
                        task_result.mark_complete(
                            success=True,
                            output=f"Task completed: {task_data.get('task', '')}",
                        )

            except Exception as e:
                # Error isolation: catch exceptions per task
                task_result.mark_complete(
                    success=False,
                    error=str(e),
                )

            return (task_id, task_result)

        # Create task coroutines
        coroutines = []
        for idx, task_data in enumerate(tasks):
            task_id = task_data.get("id", f"task-{idx}")
            coroutines.append(execute_single_task(task_data, task_id))

        # Execute all tasks concurrently
        results = await asyncio.gather(*coroutines, return_exceptions=True)

        # Process results
        for item in results:
            if isinstance(item, Exception):
                # Should not happen due to error isolation, but handle it
                task_id = f"error-{uuid.uuid4()[:4]}"
                task_results[task_id] = ParallelTaskResult(
                    task_id=task_id,
                    success=False,
                    error=str(item),
                )
            else:
                task_id, task_result = item
                task_results[task_id] = task_result

        return task_results

    def _update_average_group_duration(self, duration: float) -> None:
        """Update running average of group duration."""
        total = self._stats.total_groups
        current_avg = self._stats.average_group_duration
        self._stats.average_group_duration = (
            (current_avg * (total - 1) + duration) / total
        )

    async def cleanup(self) -> None:
        """
        Clean up coordinator resources.

        Resets the coordinator state and releases any held resources.
        """
        self._status = CoordinatorStatus.STOPPING
        self._current_group = None
        self._semaphore = None
        self._status = CoordinatorStatus.STOPPED

    async def __aenter__(self) -> "ParallelCoordinator":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ParallelCoordinator("
            f"status={self._status.value}, "
            f"max_parallel={self.max_parallel}, "
            f"groups={self._stats.total_groups})"
        )


def create_parallel_coordinator(
    config_path: Optional[str] = None,
    state_dir: Optional[str] = None,
    max_parallel: Optional[int] = None,
    auto_initialize: bool = True,
) -> ParallelCoordinator:
    """
    Factory function to create a configured parallel coordinator.

    Args:
        config_path: Optional path to configuration file
        state_dir: Optional state directory path
        max_parallel: Maximum number of concurrent tasks
        auto_initialize: If True, initialize on creation

    Returns:
        Configured ParallelCoordinator instance

    Example:
        >>> coordinator = create_parallel_coordinator(
        ...     max_parallel=5,
        ...     state_dir=".autoflow"
        ... )
        >>> result = await coordinator.execute_parallel(tasks=[...])
    """
    config = load_config(config_path) if config_path else None

    return ParallelCoordinator(
        config=config,
        state_dir=state_dir,
        max_parallel=max_parallel,
        auto_initialize=auto_initialize,
    )
