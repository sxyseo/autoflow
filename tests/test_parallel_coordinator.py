"""
Unit Tests for Parallel Coordinator

Tests the ParallelCoordinator class for coordinating parallel agent execution,
resource management, conflict detection, and result aggregation.

These tests use mocks to avoid requiring actual agent installations
or external services.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import ExecutionResult, ExecutionStatus
from autoflow.core.conflict import (
    ConflictInfo,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    detect_task_conflicts,
)
from autoflow.core.parallel import (
    CoordinatorStatus,
    ParallelCoordinator,
    ParallelCoordinatorStats,
    ParallelExecutionError,
    ParallelExecutionResult,
    ParallelTaskResult,
    create_parallel_coordinator,
)
from autoflow.core.state import ParallelGroupStatus, StateManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration object."""
    config = MagicMock()
    config.state_dir = Path("/tmp/test_state")
    config.parallel.max_parallel = 3
    return config


@pytest.fixture
def mock_agent_adapter() -> MagicMock:
    """Create a mock agent adapter."""
    adapter = MagicMock()
    adapter.execute = AsyncMock(
        return_value=ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output="Task completed successfully",
        )
    )
    return adapter


@pytest.fixture
def coordinator(
    mock_config: MagicMock,
    temp_state_dir: Path,
) -> ParallelCoordinator:
    """Create a basic ParallelCoordinator instance for testing."""
    return ParallelCoordinator(
        config=mock_config,
        state_dir=temp_state_dir,
        auto_initialize=False,
    )


# ============================================================================
# CoordinatorStatus Enum Tests
# ============================================================================


class TestCoordinatorStatus:
    """Tests for CoordinatorStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert CoordinatorStatus.IDLE.value == "idle"
        assert CoordinatorStatus.INITIALIZING.value == "initializing"
        assert CoordinatorStatus.EXECUTING.value == "executing"
        assert CoordinatorStatus.STOPPING.value == "stopping"
        assert CoordinatorStatus.STOPPED.value == "stopped"
        assert CoordinatorStatus.ERROR.value == "error"

    def test_status_is_string_enum(self) -> None:
        """Test that status is a string enum."""
        assert isinstance(CoordinatorStatus.IDLE, str)


# ============================================================================
# ParallelExecutionError Tests
# ============================================================================


class TestParallelExecutionError:
    """Tests for ParallelExecutionError exception."""

    def test_error_message(self) -> None:
        """Test error message."""
        error = ParallelExecutionError("Something went wrong")

        assert str(error) == "Something went wrong"
        assert error.task_id is None

    def test_error_with_task_id(self) -> None:
        """Test error with task_id."""
        error = ParallelExecutionError("Task failed", task_id="task-123")

        assert str(error) == "Task failed"
        assert error.task_id == "task-123"


# ============================================================================
# ParallelTaskResult Tests
# ============================================================================


class TestParallelTaskResult:
    """Tests for ParallelTaskResult dataclass."""

    def test_task_result_init(self) -> None:
        """Test task result initialization."""
        result = ParallelTaskResult(task_id="task-1")

        assert result.task_id == "task-1"
        assert result.success is False
        assert result.output is None
        assert result.error is None
        assert result.started_at is not None
        assert result.completed_at is None
        assert result.duration_seconds is None
        assert result.metadata == {}

    def test_task_result_mark_complete_success(self) -> None:
        """Test marking task as successful."""
        result = ParallelTaskResult(task_id="task-1")
        result.mark_complete(success=True, output="Done")

        assert result.success is True
        assert result.output == "Done"
        assert result.error is None
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

    def test_task_result_mark_complete_error(self) -> None:
        """Test marking task as failed."""
        result = ParallelTaskResult(task_id="task-1")
        result.mark_complete(success=False, error="Failed")

        assert result.success is False
        assert result.output is None
        assert result.error == "Failed"
        assert result.completed_at is not None

    def test_task_result_with_metadata(self) -> None:
        """Test task result with custom metadata."""
        result = ParallelTaskResult(
            task_id="task-1",
            metadata={"key": "value"},
        )

        assert result.metadata == {"key": "value"}


# ============================================================================
# ParallelExecutionResult Tests
# ============================================================================


class TestParallelExecutionResult:
    """Tests for ParallelExecutionResult dataclass."""

    def test_execution_result_init(self) -> None:
        """Test execution result initialization."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=3,
        )

        assert result.group_id == "group-1"
        assert result.total_tasks == 3
        assert result.success is False
        assert result.successful_tasks == 0
        assert result.failed_tasks == 0
        assert result.task_results == {}
        assert result.conflict_report is None
        assert result.started_at is not None
        assert result.completed_at is None
        assert result.duration_seconds is None
        assert result.error is None

    def test_mark_complete_success(self) -> None:
        """Test marking execution as successful."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=2,
        )
        result.task_results = {
            "task-1": ParallelTaskResult(task_id="task-1"),
            "task-2": ParallelTaskResult(task_id="task-2"),
        }
        result.task_results["task-1"].mark_complete(success=True)
        result.task_results["task-2"].mark_complete(success=True)

        result.mark_complete(success=True)

        assert result.success is True
        assert result.successful_tasks == 2
        assert result.failed_tasks == 0
        assert result.completed_at is not None
        assert result.duration_seconds is not None

    def test_mark_complete_partial_failure(self) -> None:
        """Test marking execution with partial failures."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=2,
        )
        result.task_results = {
            "task-1": ParallelTaskResult(task_id="task-1"),
            "task-2": ParallelTaskResult(task_id="task-2"),
        }
        result.task_results["task-1"].mark_complete(success=True)
        result.task_results["task-2"].mark_complete(
            success=False,
            error="Failed",
        )

        result.mark_complete(success=True)

        assert result.success is True  # Overall success
        assert result.successful_tasks == 1
        assert result.failed_tasks == 1

    def test_get_aggregated_output(self) -> None:
        """Test getting aggregated output."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=2,
        )
        result.task_results = {
            "task-1": ParallelTaskResult(
                task_id="task-1",
                success=True,
                output="Output 1",
            ),
            "task-2": ParallelTaskResult(
                task_id="task-2",
                success=True,
                output="Output 2",
            ),
        }

        output = result.get_aggregated_output()

        assert "=== Task task-1 ===" in output
        assert "Output 1" in output
        assert "=== Task task-2 ===" in output
        assert "Output 2" in output

    def test_get_aggregated_errors(self) -> None:
        """Test getting aggregated errors."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=2,
        )
        result.task_results = {
            "task-1": ParallelTaskResult(
                task_id="task-1",
                success=False,
                error="Error 1",
            ),
            "task-2": ParallelTaskResult(
                task_id="task-2",
                success=False,
                error="Error 2",
            ),
        }

        errors = result.get_aggregated_errors()

        assert len(errors) == 2
        assert "Task task-1: Error 1" in errors
        assert "Task task-2: Error 2" in errors

    def test_get_summary(self) -> None:
        """Test getting execution summary."""
        result = ParallelExecutionResult(
            group_id="group-1",
            total_tasks=3,
        )
        result.task_results = {
            "task-1": ParallelTaskResult(
                task_id="task-1",
                success=True,
            ),
            "task-2": ParallelTaskResult(
                task_id="task-2",
                success=True,
            ),
            "task-3": ParallelTaskResult(
                task_id="task-3",
                success=False,
                error="Failed",
            ),
        }
        result.mark_complete(success=True)

        summary = result.get_summary()

        assert summary["group_id"] == "group-1"
        assert summary["total_tasks"] == 3
        assert summary["successful_tasks"] == 2
        assert summary["failed_tasks"] == 1
        assert summary["success_rate"] == pytest.approx(66.67)
        assert summary["has_errors"] is True
        assert summary["error_count"] == 1


# ============================================================================
# ParallelCoordinatorStats Tests
# ============================================================================


class TestParallelCoordinatorStats:
    """Tests for ParallelCoordinatorStats model."""

    def test_stats_init(self) -> None:
        """Test stats initialization."""
        stats = ParallelCoordinatorStats()

        assert stats.total_groups == 0
        assert stats.successful_groups == 0
        assert stats.failed_groups == 0
        assert stats.total_tasks == 0
        assert stats.completed_tasks == 0
        assert stats.failed_tasks == 0
        assert stats.average_group_duration == 0.0
        assert stats.last_execution_at is None
        assert stats.max_parallel == 3
        assert stats.active_tasks == 0
        assert stats.started_at is not None

    def test_stats_with_values(self) -> None:
        """Test stats with custom values."""
        now = datetime.utcnow()
        stats = ParallelCoordinatorStats(
            total_groups=10,
            successful_groups=8,
            failed_groups=2,
            total_tasks=30,
            completed_tasks=25,
            failed_tasks=5,
            average_group_duration=45.5,
            max_parallel=5,
            active_tasks=2,
            last_execution_at=now,
        )

        assert stats.total_groups == 10
        assert stats.successful_groups == 8
        assert stats.failed_groups == 2
        assert stats.total_tasks == 30
        assert stats.completed_tasks == 25
        assert stats.failed_tasks == 5
        assert stats.average_group_duration == 45.5
        assert stats.max_parallel == 5
        assert stats.active_tasks == 2
        assert stats.last_execution_at == now


# ============================================================================
# ParallelCoordinator Init Tests
# ============================================================================


class TestParallelCoordinatorInit:
    """Tests for ParallelCoordinator initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        coordinator = ParallelCoordinator()

        assert coordinator._config is None
        assert coordinator._status == CoordinatorStatus.IDLE
        assert coordinator._current_group is None
        assert coordinator._state is None
        assert coordinator._max_parallel is None

    def test_init_with_config(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test initialization with config."""
        coordinator = ParallelCoordinator(config=mock_config)

        assert coordinator._config == mock_config

    def test_init_with_state_dir(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test initialization with state directory."""
        coordinator = ParallelCoordinator(state_dir=temp_state_dir)

        assert coordinator._state_dir == temp_state_dir

    def test_init_with_max_parallel(self) -> None:
        """Test initialization with max_parallel."""
        coordinator = ParallelCoordinator(max_parallel=5)

        assert coordinator._max_parallel == 5

    def test_init_status_idle(self) -> None:
        """Test initial status is IDLE."""
        coordinator = ParallelCoordinator()

        assert coordinator.status == CoordinatorStatus.IDLE


# ============================================================================
# ParallelCoordinator Properties Tests
# ============================================================================


class TestParallelCoordinatorProperties:
    """Tests for ParallelCoordinator properties."""

    def test_status_property(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test status property."""
        assert coordinator.status == CoordinatorStatus.IDLE

        coordinator._status = CoordinatorStatus.EXECUTING
        assert coordinator.status == CoordinatorStatus.EXECUTING

    def test_max_parallel_property_default(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test max_parallel property with default."""
        # Remove the mock's parallel config to test default
        coordinator._config.parallel = None

        assert coordinator.max_parallel == 3  # DEFAULT_MAX_PARALLEL

    def test_max_parallel_property_from_config(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test max_parallel property from config."""
        assert coordinator.max_parallel == 3

    def test_max_parallel_property_override(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test max_parallel property with override."""
        coordinator = ParallelCoordinator(
            state_dir=temp_state_dir,
            max_parallel=7,
        )

        assert coordinator.max_parallel == 7

    def test_stats_property(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test stats property."""
        stats = coordinator.stats

        assert isinstance(stats, ParallelCoordinatorStats)
        assert stats.total_groups == 0

    def test_semaphore_property(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test semaphore property."""
        semaphore = coordinator.semaphore

        assert isinstance(semaphore, asyncio.Semaphore)

    def test_config_property_lazy_load(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test config property loads config lazily."""
        coordinator = ParallelCoordinator(state_dir=temp_state_dir)

        with patch(
            "autoflow.core.parallel.load_config"
        ) as mock_load:
            mock_load.return_value = MagicMock()
            _ = coordinator.config

            mock_load.assert_called_once()

    def test_state_property_creates_manager(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test state property creates StateManager."""
        coordinator = ParallelCoordinator(state_dir=temp_state_dir)

        state = coordinator.state

        assert isinstance(state, StateManager)


# ============================================================================
# ParallelCoordinator Initialize Tests
# ============================================================================


class TestParallelCoordinatorInitialize:
    """Tests for ParallelCoordinator.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_success(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test successful initialization."""
        await coordinator.initialize()

        assert coordinator.status == CoordinatorStatus.IDLE

    @pytest.mark.asyncio
    async def test_initialize_sets_status(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test initialization sets status correctly."""
        # Start initialization
        init_task = asyncio.create_task(coordinator.initialize())

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Wait for completion
        await init_task

        assert coordinator.status == CoordinatorStatus.IDLE

    @pytest.mark.asyncio
    async def test_initialize_failure(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test initialization failure."""
        with patch.object(
            coordinator.state,
            "initialize",
            side_effect=Exception("State init failed"),
        ):
            with pytest.raises(ParallelExecutionError) as exc_info:
                await coordinator.initialize()

            assert "Initialization failed" in str(exc_info.value)
            assert coordinator.status == CoordinatorStatus.ERROR


# ============================================================================
# ParallelCoordinator Check Capacity Tests
# ============================================================================


class TestParallelCoordinatorCheckCapacity:
    """Tests for ParallelCoordinator.check_capacity_available method."""

    def test_check_capacity_available(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test checking capacity with no active tasks."""
        assert coordinator.check_capacity_available(1) is True
        assert coordinator.check_capacity_available(3) is True
        assert coordinator.check_capacity_available(4) is False

    def test_check_capacity_with_active_tasks(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test checking capacity with active tasks."""
        coordinator._stats.active_tasks = 2

        assert coordinator.check_capacity_available(1) is True
        assert coordinator.check_capacity_available(2) is False


# ============================================================================
# ParallelCoordinator Execute Parallel Tests
# ============================================================================


class TestParallelCoordinatorExecuteParallel:
    """Tests for ParallelCoordinator.execute_parallel method."""

    @pytest.mark.asyncio
    async def test_execute_parallel_success_no_adapter(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test successful parallel execution without adapter."""
        await coordinator.initialize()

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            tasks = [
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]

            result = await coordinator.execute_parallel(
                tasks=tasks,
                check_conflicts=False,
            )

            assert result.success is True
            assert result.total_tasks == 2
            assert result.successful_tasks == 2
            assert result.failed_tasks == 0
            assert len(result.task_results) == 2

    @pytest.mark.asyncio
    async def test_execute_parallel_with_adapter(
        self,
        coordinator: ParallelCoordinator,
        mock_agent_adapter: MagicMock,
    ) -> None:
        """Test successful parallel execution with agent adapter."""
        await coordinator.initialize()

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            tasks = [
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]

            result = await coordinator.execute_parallel(
                tasks=tasks,
                agent_adapter=mock_agent_adapter,
                check_conflicts=False,
            )

            assert result.success is True
            assert result.total_tasks == 2
            assert result.successful_tasks == 2
            assert mock_agent_adapter.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_parallel_with_failure(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test parallel execution with partial failure."""
        await coordinator.initialize()

        # Mock adapter that fails on second task
        adapter = MagicMock()
        adapter.execute = AsyncMock(side_effect=[
            ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                output="Success",
            ),
            ExecutionResult(
                status=ExecutionStatus.ERROR,
                error="Failed",
            ),
        ])

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            tasks = [
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]

            result = await coordinator.execute_parallel(
                tasks=tasks,
                agent_adapter=adapter,
                check_conflicts=False,
            )

            assert result.success is True  # Overall success
            assert result.total_tasks == 2
            assert result.successful_tasks == 1
            assert result.failed_tasks == 1

    @pytest.mark.asyncio
    async def test_execute_parallel_with_conflicts(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test parallel execution with conflict detection."""
        await coordinator.initialize()

        # Mock conflict detection
        conflict_info = ConflictInfo(
            type=ConflictType.FILE_OVERLAP,
            severity=ConflictSeverity.HIGH,
            description="Same file",
            task_ids=["task-1", "task-2"],
            resources=["src/main.py"],
        )
        conflict_report = ConflictReport(
            has_conflicts=True,
            conflicts=[conflict_info],
            total_tasks=2,
            safe_to_run=False,
        )

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            with patch(
                "autoflow.core.parallel.detect_task_conflicts",
                return_value=conflict_report,
            ):
                tasks = [
                    {"task": "Task 1", "workdir": "./src"},
                    {"task": "Task 2", "workdir": "./src"},
                ]

                result = await coordinator.execute_parallel(
                    tasks=tasks,
                    check_conflicts=True,
                )

            assert result.success is False
            assert result.conflict_report is not None
            assert "High-severity conflicts detected" in result.error

    @pytest.mark.asyncio
    async def test_execute_parallel_timeout(
        self,
        coordinator: ParallelCoordinator,
        mock_agent_adapter: MagicMock,
    ) -> None:
        """Test parallel execution with timeout."""
        await coordinator.initialize()

        # Mock adapter that raises timeout error
        mock_agent_adapter.execute = AsyncMock(
            side_effect=asyncio.TimeoutError("Task timed out"),
        )

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            tasks = [{"task": "Task 1", "workdir": "./src"}]

            result = await coordinator.execute_parallel(
                tasks=tasks,
                agent_adapter=mock_agent_adapter,
                check_conflicts=False,
                timeout_seconds=1,
            )

            # Overall success (error isolation)
            assert result.success is True
            # But the task itself failed
            assert result.failed_tasks == 1
            task_result = list(result.task_results.values())[0]
            assert "timed out" in task_result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_parallel_with_custom_metadata(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test parallel execution with custom metadata."""
        await coordinator.initialize()

        metadata = {"project": "test", "run_id": "123"}

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            result = await coordinator.execute_parallel(
                tasks=[{"task": "Task 1", "workdir": "./src"}],
                check_conflicts=False,
                metadata=metadata,
            )

            assert result.metadata == metadata

    @pytest.mark.asyncio
    async def test_execute_parallel_updates_stats(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test that execute_parallel updates stats."""
        await coordinator.initialize()

        # Mock state saving to avoid datetime serialization issues
        with patch.object(coordinator.state, "save_parallel_group"):
            result = await coordinator.execute_parallel(
                tasks=[
                    {"task": "Task 1", "workdir": "./src"},
                    {"task": "Task 2", "workdir": "./docs"},
                ],
                check_conflicts=False,
            )

            stats = coordinator.stats
            assert stats.total_groups == 1
            assert stats.successful_groups == 1
            assert stats.total_tasks == 2
            assert stats.completed_tasks == 2


# ============================================================================
# ParallelCoordinator Get Stats Summary Tests
# ============================================================================


class TestParallelCoordinatorGetStatsSummary:
    """Tests for ParallelCoordinator.get_stats_summary method."""

    def test_get_stats_summary(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test getting stats summary."""
        coordinator._stats.total_groups = 10
        coordinator._stats.successful_groups = 8
        coordinator._stats.failed_groups = 2
        coordinator._stats.active_tasks = 1

        summary = coordinator.get_stats_summary()

        assert summary["total_groups"] == 10
        assert summary["successful_groups"] == 8
        assert summary["failed_groups"] == 2
        assert summary["max_parallel"] == 3
        assert summary["active_tasks"] == 1
        assert summary["available_slots"] == 2
        assert "started_at" in summary


# ============================================================================
# ParallelCoordinator Cleanup Tests
# ============================================================================


class TestParallelCoordinatorCleanup:
    """Tests for ParallelCoordinator.cleanup method."""

    @pytest.mark.asyncio
    async def test_cleanup(
        self,
        coordinator: ParallelCoordinator,
    ) -> None:
        """Test cleanup."""
        coordinator._status = CoordinatorStatus.EXECUTING
        coordinator._current_group = MagicMock()

        await coordinator.cleanup()

        assert coordinator.status == CoordinatorStatus.STOPPED
        assert coordinator._current_group is None


# ============================================================================
# ParallelCoordinator Context Manager Tests
# ============================================================================


class TestParallelCoordinatorContextManager:
    """Tests for ParallelCoordinator async context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test using coordinator as async context manager."""
        async with ParallelCoordinator(
            state_dir=temp_state_dir,
        ) as coordinator:
            assert coordinator.status == CoordinatorStatus.IDLE

            # Mock state saving to avoid datetime serialization issues
            with patch.object(coordinator.state, "save_parallel_group"):
                # Execute a task
                result = await coordinator.execute_parallel(
                    tasks=[{"task": "Test", "workdir": "./src"}],
                    check_conflicts=False,
                )
                assert result.success is True

        # After exiting context, should be stopped
        assert coordinator.status == CoordinatorStatus.STOPPED


# ============================================================================
# ParallelCoordinator Repr Tests
# ============================================================================


class TestParallelCoordinatorRepr:
    """Tests for ParallelCoordinator.__repr__ method."""

    def test_repr(self, coordinator: ParallelCoordinator) -> None:
        """Test string representation."""
        repr_str = repr(coordinator)

        assert "ParallelCoordinator" in repr_str
        assert "status=idle" in repr_str
        assert "max_parallel=3" in repr_str


# ============================================================================
# Create Parallel Coordinator Tests
# ============================================================================


class TestCreateParallelCoordinator:
    """Tests for create_parallel_coordinator factory function."""

    def test_create_parallel_coordinator_default(self) -> None:
        """Test creating coordinator with defaults."""
        coordinator = create_parallel_coordinator(
            auto_initialize=False,
        )

        assert isinstance(coordinator, ParallelCoordinator)
        assert coordinator._max_parallel is None

    def test_create_parallel_coordinator_with_params(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test creating coordinator with parameters."""
        coordinator = create_parallel_coordinator(
            state_dir=str(temp_state_dir),
            max_parallel=5,
            auto_initialize=False,
        )

        assert isinstance(coordinator, ParallelCoordinator)
        assert coordinator._state_dir == temp_state_dir
        assert coordinator._max_parallel == 5

    def test_create_parallel_coordinator_with_config_path(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test creating coordinator with config path."""
        with patch(
            "autoflow.core.parallel.load_config"
        ) as mock_load:
            mock_load.return_value = MagicMock()

            coordinator = create_parallel_coordinator(
                config_path="/path/to/config.yaml",
                auto_initialize=False,
            )

            mock_load.assert_called_once_with("/path/to/config.yaml")
            assert coordinator._config is not None
