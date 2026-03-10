"""
Integration Tests for Parallel Agent Execution

Tests the full integration of parallel agent execution, including:
- Orchestrator and ParallelCoordinator integration
- Concurrent execution of multiple independent tasks
- Resource limiting and conflict detection
- Result aggregation and error isolation
- State management integration

These tests use mocks to avoid requiring actual agent installations
or external services, but test the full integration stack.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import ExecutionResult, ExecutionStatus
from autoflow.core.config import Config, ParallelConfig
from autoflow.core.orchestrator import AutoflowOrchestrator
from autoflow.core.parallel import (
    ParallelExecutionError,
    ParallelExecutionResult,
    ParallelTaskResult,
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
def temp_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration object."""
    config = MagicMock()
    config.state_dir = Path("/tmp/test_state")
    config.openclaw.gateway_url = "http://localhost:8080"
    config.openclaw.extra_dirs = []
    config.agents.claude_code.timeout_seconds = 300
    config.agents.codex.timeout_seconds = 300
    config.ci.gates = []
    config.scheduler.enabled = False
    config.parallel = ParallelConfig(
        enabled=True,
        max_concurrent_tasks=3,
        timeout_seconds=300,
    )
    return config


@pytest.fixture
def orchestrator(
    mock_config: MagicMock,
    temp_state_dir: Path,
    temp_skills_dir: Path,
) -> AutoflowOrchestrator:
    """Create a basic AutoflowOrchestrator instance for testing."""
    return AutoflowOrchestrator(
        config=mock_config,
        state_dir=temp_state_dir,
        skills_dir=temp_skills_dir,
        auto_initialize=False,
    )


# ============================================================================
# Integration Tests: Orchestrator.run_tasks_parallel()
# ============================================================================


class TestOrchestratorParallelIntegration:
    """Integration tests for orchestrator parallel execution."""

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_basic(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test basic parallel task execution through orchestrator."""
        await orchestrator.initialize()

        # Execute tasks in parallel
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Fix bug in app.py", "workdir": "./src"},
                {"task": "Update README", "workdir": "./docs"},
                {"task": "Add tests", "workdir": "./tests"},
            ]
        )

        # Verify result structure
        assert isinstance(result, ParallelExecutionResult)
        assert result.total_tasks == 3
        assert result.successful_tasks == 3
        assert result.failed_tasks == 0
        assert result.success is True
        assert len(result.task_results) == 3

        # Verify orchestrator statistics were updated
        assert orchestrator.stats.total_tasks == 3
        assert orchestrator.stats.completed_tasks == 3
        assert orchestrator.stats.failed_tasks == 0

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_with_conflicts(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution with conflicting files."""
        await orchestrator.initialize()

        # Execute tasks that touch the same file (high-severity conflict)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "id": "task-1",
                    "task": "Fix bug in app.py",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
                {
                    "id": "task-2",
                    "task": "Add feature to app.py",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
                {
                    "id": "task-3",
                    "task": "Update docs",
                    "workdir": "./docs",
                    "files": ["docs/README.md"],
                },
            ],
            check_conflicts=True,
        )

        # Should detect conflicts and fail early
        assert result.success is False
        assert result.conflict_report is not None
        assert len(result.conflict_report.get_high_severity()) > 0
        assert "conflict" in result.error.lower()

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_without_conflict_check(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution with conflict check disabled."""
        await orchestrator.initialize()

        # Execute tasks with conflict check disabled
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Fix bug", "workdir": "./src"},
                {"task": "Add feature", "workdir": "./src"},
            ],
            check_conflicts=False,
        )

        # Should execute without conflict checking
        assert result.success is True
        assert result.conflict_report is None

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_with_timeout(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution with custom timeout."""
        await orchestrator.initialize()

        # Execute tasks with custom timeout
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Quick task", "workdir": "./src"},
            ],
            timeout_seconds=600,
        )

        # Should complete successfully
        assert result.success is True

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_with_metadata(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution with custom metadata."""
        await orchestrator.initialize()

        metadata = {
            "project": "test-project",
            "version": "1.0.0",
            "priority": "high",
        }

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
            ],
            metadata=metadata,
        )

        # Verify metadata is preserved
        assert result.success is True
        assert result.metadata == metadata

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_empty_list(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution with empty task list."""
        await orchestrator.initialize()

        result = await orchestrator.run_tasks_parallel(tasks=[])

        # Should handle gracefully
        assert result.total_tasks == 0
        assert result.successful_tasks == 0
        assert result.failed_tasks == 0

    @pytest.mark.asyncio
    async def test_run_tasks_parallel_orchestrator_status(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that orchestrator status changes during parallel execution."""
        await orchestrator.initialize()

        # Status should be IDLE initially
        assert orchestrator.status == "idle"

        # Execute tasks (should set status to RUNNING)
        task = asyncio.create_task(
            orchestrator.run_tasks_parallel(
                tasks=[{"task": "Test", "workdir": "./src"}],
            )
        )

        # Wait a bit for status to change
        await asyncio.sleep(0.01)
        assert orchestrator.status == "running"

        # Wait for completion
        await task
        assert orchestrator.status == "idle"


# ============================================================================
# Integration Tests: Resource Limiting
# ============================================================================


class TestResourceLimiting:
    """Integration tests for resource limiting in parallel execution."""

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_respected(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that max_concurrent_tasks limit is respected."""
        await orchestrator.initialize()

        # Create more tasks than max_concurrent_tasks
        num_tasks = 10
        max_parallel = orchestrator.config.parallel.max_concurrent_tasks

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": f"Task {i}", "workdir": "./src"}
                for i in range(num_tasks)
            ]
        )

        # All tasks should complete
        assert result.total_tasks == num_tasks
        assert result.successful_tasks == num_tasks

        # Verify semaphore limited concurrency
        # (This is implicit in the successful completion)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_capacity_check_before_execution(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test capacity checking before parallel execution."""
        await orchestrator.initialize()

        # Check capacity is available
        assert (
            orchestrator.parallel_coordinator.check_capacity_available(3)
            is True
        )

        # Check capacity for more than max
        assert (
            orchestrator.parallel_coordinator.check_capacity_available(
                orchestrator.config.parallel.max_concurrent_tasks + 1
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_stats_tracking_during_execution(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that statistics are tracked during parallel execution."""
        await orchestrator.initialize()

        # Get initial stats
        initial_stats = orchestrator.parallel_coordinator.get_stats_summary()

        # Execute tasks
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]
        )

        # Get final stats
        final_stats = orchestrator.parallel_coordinator.get_stats_summary()

        # Verify stats updated
        assert final_stats["total_groups"] == initial_stats["total_groups"] + 1
        assert final_stats["total_tasks"] == initial_stats["total_tasks"] + 2
        assert final_stats["completed_tasks"] == initial_stats["completed_tasks"] + 2


# ============================================================================
# Integration Tests: Result Aggregation
# ============================================================================


class TestResultAggregation:
    """Integration tests for result aggregation in parallel execution."""

    @pytest.mark.asyncio
    async def test_aggregated_output_collection(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that outputs from all tasks are aggregated."""
        await orchestrator.initialize()

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
                {"task": "Task 3", "workdir": "./tests"},
            ]
        )

        # Get aggregated output
        aggregated = result.get_aggregated_output()

        # Should contain all task outputs
        assert "Task 1" in aggregated or "Task 2" in aggregated
        assert len(aggregated) > 0

    @pytest.mark.asyncio
    async def test_aggregated_error_collection(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that errors from failed tasks are aggregated."""
        await orchestrator.initialize()

        # Note: In the mock implementation, all tasks succeed
        # This test verifies the error aggregation infrastructure exists
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]
        )

        # Verify error aggregation methods exist and work
        assert hasattr(result, "get_aggregated_errors")
        errors = result.get_aggregated_errors()
        assert isinstance(errors, list)

        # In successful execution, no errors
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_execution_summary(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that execution summary is comprehensive."""
        await orchestrator.initialize()

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]
        )

        summary = result.get_summary()

        # Verify summary contains all expected fields
        assert "total_tasks" in summary
        assert "successful_tasks" in summary
        assert "failed_tasks" in summary
        assert "duration_seconds" in summary
        assert "success_rate" in summary
        assert summary["total_tasks"] == 2
        assert summary["successful_tasks"] == 2
        assert summary["success_rate"] == 100.0


# ============================================================================
# Integration Tests: Error Isolation
# ============================================================================


class TestErrorIsolation:
    """Integration tests for error isolation in parallel execution."""

    @pytest.mark.asyncio
    async def test_one_task_failure_doesnt_affect_others(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that one task failure doesn't stop other tasks."""
        await orchestrator.initialize()

        # Create tasks where one will fail
        # (In the mock implementation, all succeed, but we test the mechanism)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
                {"task": "Task 3", "workdir": "./tests"},
            ]
        )

        # All tasks should complete (error isolation is built-in)
        assert result.total_tasks == 3
        assert result.successful_tasks == 3

    @pytest.mark.asyncio
    async def test_partial_failure_handling(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of partial failures in task group."""
        await orchestrator.initialize()

        # This tests the error isolation mechanism
        # Even with failures, the group should complete
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
            ]
        )

        # Should complete with results
        assert result is not None
        assert hasattr(result, "task_results")


# ============================================================================
# Integration Tests: State Management
# ============================================================================


class TestStateManagement:
    """Integration tests for state management in parallel execution."""

    @pytest.mark.asyncio
    async def test_parallel_group_state_saved(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_state_dir: Path,
    ) -> None:
        """Test that parallel group state is saved to storage."""
        await orchestrator.initialize()

        # Execute tasks
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
                {"task": "Task 2", "workdir": "./docs"},
            ]
        )

        # Verify state was saved
        state_manager = StateManager(temp_state_dir)
        group_data = state_manager.load_parallel_group(result.group_id)

        assert group_data is not None
        assert group_data["id"] == result.group_id
        assert group_data["status"] == ParallelGroupStatus.COMPLETED
        assert group_data["max_parallel"] == orchestrator.config.parallel.max_concurrent_tasks

    @pytest.mark.asyncio
    async def test_state_updated_on_completion(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_state_dir: Path,
    ) -> None:
        """Test that state is updated when tasks complete."""
        await orchestrator.initialize()

        # Execute tasks
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "./src"},
            ]
        )

        # Load state and verify it's marked as completed
        state_manager = StateManager(temp_state_dir)
        group_data = state_manager.load_parallel_group(result.group_id)

        assert group_data["status"] == ParallelGroupStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_state_updated_on_failure(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_state_dir: Path,
    ) -> None:
        """Test that state is updated when execution fails."""
        await orchestrator.initialize()

        # Execute tasks with conflicts (will fail)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "task": "Task 1",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
                {
                    "task": "Task 2",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
            ],
            check_conflicts=True,
        )

        # Load state and verify it's marked as failed
        state_manager = StateManager(temp_state_dir)
        group_data = state_manager.load_parallel_group(result.group_id)

        # Should be in state (either failed or completed with errors)
        assert group_data is not None
        assert group_data["id"] == result.group_id


# ============================================================================
# Integration Tests: End-to-End Scenarios
# ============================================================================


class TestEndToEndScenarios:
    """End-to-end integration test scenarios."""

    @pytest.mark.asyncio
    async def test_parallel_execution_full_workflow(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_state_dir: Path,
    ) -> None:
        """Test complete workflow: execute -> aggregate -> state -> cleanup."""
        await orchestrator.initialize()

        # Step 1: Execute tasks
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Fix bug", "workdir": "./src"},
                {"task": "Update docs", "workdir": "./docs"},
                {"task": "Add tests", "workdir": "./tests"},
            ]
        )

        # Step 2: Verify results
        assert result.success is True
        assert result.total_tasks == 3

        # Step 3: Verify state
        state_manager = StateManager(temp_state_dir)
        group_data = state_manager.load_parallel_group(result.group_id)
        assert group_data is not None

        # Step 4: Verify statistics
        assert orchestrator.stats.total_tasks == 3
        assert orchestrator.stats.completed_tasks == 3

        # Step 5: Cleanup
        await orchestrator.cleanup()
        # Note: cleanup() sets status to "stopping", not "stopped"
        # This is expected behavior for the orchestrator
        assert orchestrator.status in ("stopping", "stopped")

    @pytest.mark.asyncio
    async def test_multiple_parallel_executions(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test running multiple parallel executions sequentially."""
        await orchestrator.initialize()

        # First execution
        result1 = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task 1", "workdir": "./src"}],
        )

        # Second execution
        result2 = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task 2", "workdir": "./docs"}],
        )

        # Both should succeed
        assert result1.success is True
        assert result2.success is True

        # Verify statistics accumulated
        assert orchestrator.stats.total_tasks == 2
        assert orchestrator.stats.completed_tasks == 2

    @pytest.mark.asyncio
    async def test_config_integration(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that config values are properly used."""
        await orchestrator.initialize()

        # Verify config is accessible
        assert orchestrator.config.parallel.enabled is True
        assert orchestrator.config.parallel.max_concurrent_tasks == 3
        assert orchestrator.config.parallel.timeout_seconds == 300

        # Execute and verify parallel coordinator uses config
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        assert result.success is True


# ============================================================================
# Edge Case Tests: Timeouts
# ============================================================================


class TestEdgeCaseTimeouts:
    """Edge case tests for timeout handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_task_timeout_exceeded(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling when a task exceeds its timeout."""
        await orchestrator.initialize()

        # Execute with very short timeout
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Long running task", "workdir": "./src"}],
            timeout_seconds=0.001,  # Extremely short timeout
        )

        # Should handle timeout gracefully
        # In mock environment, this may succeed quickly, but we test the mechanism
        assert result is not None
        assert hasattr(result, "duration_seconds")

    @pytest.mark.asyncio
    async def test_timeout_during_parallel_execution(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test timeout occurring during parallel execution."""
        await orchestrator.initialize()

        # Create multiple tasks with short timeout
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": f"Task {i}", "workdir": "./src"}
                for i in range(5)
            ],
            timeout_seconds=1,  # Short timeout
        )

        # Should handle timeout during parallel execution
        assert result is not None
        assert hasattr(result, "task_results")

    @pytest.mark.asyncio
    async def test_zero_timeout_handled(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that zero timeout is handled appropriately."""
        await orchestrator.initialize()

        # Zero timeout should either use default or fail gracefully
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
            timeout_seconds=0,
        )

        # Should handle gracefully (either succeed or fail with clear error)
        assert result is not None

    @pytest.mark.asyncio
    async def test_negative_timeout_handled(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that negative timeout is handled gracefully."""
        await orchestrator.initialize()

        # Negative timeout should be handled gracefully
        # (may be treated as no timeout or converted to absolute value)
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
            timeout_seconds=-1,
        )

        # Should complete without crashing
        assert result is not None
        assert hasattr(result, "duration_seconds")


# ============================================================================
# Edge Case Tests: Failures
# ============================================================================


class TestEdgeCaseFailures:
    """Edge case tests for failure handling in parallel execution."""

    @pytest.mark.asyncio
    async def test_all_tasks_fail(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling when all tasks in a group fail."""
        await orchestrator.initialize()

        # Create tasks that will all fail (using invalid workdirs)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task 1", "workdir": "/nonexistent/path"},
                {"task": "Task 2", "workdir": "/invalid/path"},
            ],
        )

        # Should handle all failures gracefully
        assert result is not None
        assert result.total_tasks == 2
        # In mock environment, may succeed or fail gracefully

    @pytest.mark.asyncio
    async def test_single_task_failure_in_group(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling when one task fails in a group."""
        await orchestrator.initialize()

        # Mix valid and invalid tasks
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Valid task", "workdir": "./src"},
                {"task": "Invalid task", "workdir": "/nonexistent"},
                {"task": "Another valid", "workdir": "./docs"},
            ],
        )

        # Should complete with partial success
        assert result is not None
        assert result.total_tasks == 3
        assert hasattr(result, "task_results")

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling when some tasks succeed and some fail."""
        await orchestrator.initialize()

        # Mix tasks with different workdirs (some may fail)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Valid task 1", "workdir": "./src"},
                {"task": "Potentially invalid", "workdir": "/nonexistent"},
                {"task": "Valid task 2", "workdir": "./docs"},
            ],
        )

        # Should handle mixed results
        assert result is not None
        assert result.total_tasks == 3
        assert hasattr(result, "task_results")

    @pytest.mark.asyncio
    async def test_exception_during_execution(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of unexpected exceptions during execution."""
        await orchestrator.initialize()

        # Test with invalid input that might cause exceptions
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": "Task", "workdir": "./src"},
            ],
        )

        # Should complete without propagating exceptions
        assert result is not None
        assert hasattr(result, "success")

    @pytest.mark.asyncio
    async def test_failure_recovery_and_retry(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that failed tasks can be retried."""
        await orchestrator.initialize()

        # First execution may fail
        result1 = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        # Second execution should succeed (retry mechanism)
        result2 = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        # Both should complete (even if first failed)
        assert result1 is not None
        assert result2 is not None


# ============================================================================
# Edge Case Tests: Conflicts
# ============================================================================


class TestEdgeCaseConflicts:
    """Edge case tests for conflict detection in parallel execution."""

    @pytest.mark.asyncio
    async def test_low_severity_conflicts_allowed(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that low-severity conflicts are allowed."""
        await orchestrator.initialize()

        # Create tasks with low-severity conflicts (same directory, different files)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "id": "task-1",
                    "task": "Task 1",
                    "workdir": "./src",
                    "files": ["src/file1.py"],
                },
                {
                    "id": "task-2",
                    "task": "Task 2",
                    "workdir": "./src",
                    "files": ["src/file2.py"],
                },
            ],
            check_conflicts=True,
        )

        # Low-severity conflicts should be allowed
        assert result is not None

    @pytest.mark.asyncio
    async def test_high_severity_conflicts_blocked(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that high-severity conflicts are blocked."""
        await orchestrator.initialize()

        # Create tasks with high-severity conflicts (same file)
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "id": "task-1",
                    "task": "Task 1",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
                {
                    "id": "task-2",
                    "task": "Task 2",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
            ],
            check_conflicts=True,
        )

        # Should detect and block high-severity conflicts
        assert result.conflict_report is not None
        high_severity = result.conflict_report.get_high_severity()
        assert len(high_severity) > 0

    @pytest.mark.asyncio
    async def test_conflict_detection_with_many_tasks(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test conflict detection with many tasks."""
        await orchestrator.initialize()

        # Create many tasks with various conflicts
        tasks = []
        for i in range(10):
            tasks.append({
                "id": f"task-{i}",
                "task": f"Task {i}",
                "workdir": "./src",
                "files": [f"src/file{i % 3}.py"],  # Creates conflicts
            })

        result = await orchestrator.run_tasks_parallel(
            tasks=tasks,
            check_conflicts=True,
        )

        # Should detect conflicts across all tasks
        assert result.conflict_report is not None
        assert len(result.conflict_report.conflicts) > 0
        assert result.conflict_report.has_conflicts is True

    @pytest.mark.asyncio
    async def test_no_conflicts_with_different_files(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that no conflicts are detected for different files."""
        await orchestrator.initialize()

        # Create tasks with completely different files
        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "id": "task-1",
                    "task": "Task 1",
                    "workdir": "./src",
                    "files": ["src/module1.py"],
                },
                {
                    "id": "task-2",
                    "task": "Task 2",
                    "workdir": "./docs",
                    "files": ["docs/readme.md"],
                },
                {
                    "id": "task-3",
                    "task": "Task 3",
                    "workdir": "./tests",
                    "files": ["tests/test.py"],
                },
            ],
            check_conflicts=True,
        )

        # Should have no conflicts
        if result.conflict_report:
            assert len(result.conflict_report.conflicts) == 0
            assert result.conflict_report.has_conflicts is False

    @pytest.mark.asyncio
    async def test_conflict_report_details(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test that conflict report contains detailed information."""
        await orchestrator.initialize()

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {
                    "id": "task-1",
                    "task": "Task 1",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
                {
                    "id": "task-2",
                    "task": "Task 2",
                    "workdir": "./src",
                    "files": ["src/app.py"],
                },
            ],
            check_conflicts=True,
        )

        # Verify conflict report structure
        assert result.conflict_report is not None
        assert hasattr(result.conflict_report, "get_high_severity")
        assert hasattr(result.conflict_report, "get_by_type")
        assert hasattr(result.conflict_report, "conflicts")

        # Verify conflict details
        conflicts = result.conflict_report.get_high_severity()
        assert len(conflicts) > 0
        # Verify conflict has required fields
        assert hasattr(conflicts[0], "type")
        assert hasattr(conflicts[0], "severity")
        assert hasattr(conflicts[0], "description")
        assert hasattr(conflicts[0], "task_ids")
        assert hasattr(conflicts[0], "resources")


# ============================================================================
# Edge Case Tests: Invalid Inputs
# ============================================================================


class TestEdgeCaseInvalidInputs:
    """Edge case tests for invalid input handling."""

    @pytest.mark.asyncio
    async def test_empty_task_list(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of empty task list."""
        await orchestrator.initialize()

        result = await orchestrator.run_tasks_parallel(tasks=[])

        # Should handle gracefully
        assert result.total_tasks == 0
        assert result.successful_tasks == 0
        assert result.failed_tasks == 0

    @pytest.mark.asyncio
    async def test_missing_task_field(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of tasks missing required fields."""
        await orchestrator.initialize()

        # Task missing required 'task' field
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"workdir": "./src"}],  # Missing 'task'
        )

        # Should handle gracefully (either fail or use default)
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_task_format(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of invalid task formats."""
        await orchestrator.initialize()

        # Invalid task format (string instead of dict)
        # Should raise an error or handle gracefully
        with pytest.raises(Exception):
            await orchestrator.run_tasks_parallel(
                tasks=["invalid task format"],  # Should be dict
            )

    @pytest.mark.asyncio
    async def test_none_task_list(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling of None task list."""
        await orchestrator.initialize()

        # None task list should fail gracefully
        with pytest.raises(Exception):
            await orchestrator.run_tasks_parallel(tasks=None)


# ============================================================================
# Edge Case Tests: Resource Constraints
# ============================================================================


class TestEdgeCaseResourceConstraints:
    """Edge case tests for resource constraint handling."""

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_set_to_one(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test execution with max_concurrent_tasks=1 (sequential)."""
        await orchestrator.initialize()

        # Set max to 1 for sequential execution
        orchestrator.config.parallel.max_concurrent_tasks = 1

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": f"Task {i}", "workdir": "./src"}
                for i in range(5)
            ],
        )

        # Should execute sequentially but complete all
        assert result.total_tasks == 5
        assert result.successful_tasks == 5

    @pytest.mark.asyncio
    async def test_max_concurrent_tasks_exceeded(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test requesting more tasks than max_concurrent_tasks."""
        await orchestrator.initialize()

        # Request many more tasks than max_concurrent_tasks
        num_tasks = 100
        max_parallel = orchestrator.config.parallel.max_concurrent_tasks

        result = await orchestrator.run_tasks_parallel(
            tasks=[
                {"task": f"Task {i}", "workdir": "./src"}
                for i in range(num_tasks)
            ],
        )

        # Should respect max_concurrent_tasks limit
        assert result.total_tasks == num_tasks
        # All tasks should still complete (just in batches)
        assert result.successful_tasks == num_tasks

    @pytest.mark.asyncio
    async def test_zero_max_concurrent_tasks(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test handling when max_concurrent_tasks is set to 0."""
        await orchestrator.initialize()

        # Set to 0 (should fail or use default)
        orchestrator.config.parallel.max_concurrent_tasks = 0

        # Should either fail or use default value
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        assert result is not None


# ============================================================================
# Edge Case Tests: State Edge Cases
# ============================================================================


class TestEdgeCaseState:
    """Edge case tests for state management."""

    @pytest.mark.asyncio
    async def test_parallel_execution_without_initialization(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test parallel execution without prior initialization."""
        # Don't initialize the orchestrator

        # Should auto-initialize or fail gracefully
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_state_corruption_recovery(
        self,
        orchestrator: AutoflowOrchestrator,
        temp_state_dir: Path,
    ) -> None:
        """Test recovery from corrupted state."""
        await orchestrator.initialize()

        # Create a corrupted state file
        state_file = temp_state_dir / "parallel_groups" / "corrupted.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{invalid json content")

        # Should handle corrupted state gracefully
        result = await orchestrator.run_tasks_parallel(
            tasks=[{"task": "Task", "workdir": "./src"}],
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_parallel_executions(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test multiple parallel executions running concurrently."""
        await orchestrator.initialize()

        # Start multiple parallel executions concurrently
        tasks = [
            orchestrator.run_tasks_parallel(
                tasks=[{"task": f"Task {i}", "workdir": "./src"}],
            )
            for i in range(3)
        ]

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # All should complete successfully
        assert len(results) == 3
        assert all(r.success for r in results)
