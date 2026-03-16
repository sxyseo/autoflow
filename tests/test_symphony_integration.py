"""
Integration Tests for Symphony Workflow Execution

Tests the integration between Autoflow Orchestrator and Symphony framework
for multi-agent workflow execution. These tests verify that Symphony workflows
can be triggered from Autoflow, state is synchronized properly, and results
flow back correctly.

These tests use mocks to avoid requiring actual Symphony CLI installation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.agents.base import (
    AgentConfig,
    ExecutionResult,
    ExecutionStatus,
)
from autoflow.core.orchestrator import (
    AutoflowOrchestrator,
    OrchestratorError,
    OrchestratorStatus,
)
from autoflow.core.state import RunStatus, TaskStatus


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
def mock_config(temp_state_dir: Path) -> MagicMock:
    """Create a mock configuration object with Symphony config."""
    config = MagicMock()
    config.state_dir = temp_state_dir
    config.openclaw.gateway_url = "http://localhost:8080"
    config.openclaw.extra_dirs = []
    config.agents.claude_code.timeout_seconds = 300
    config.agents.codex.timeout_seconds = 300
    config.symphony.enabled = True
    config.symphony.gateway_url = "http://localhost:8080"
    config.symphony.timeout_seconds = 600
    config.symphony.api_key = "test-key"
    config.symphony.project_id = "test-project"
    config.ci.gates = []
    config.scheduler.enabled = False
    return config


@pytest.fixture
def mock_symphony_adapter() -> MagicMock:
    """Create a mock Symphony adapter."""
    adapter = MagicMock()

    # Mock execute method
    execute_result = ExecutionResult()
    execute_result.mark_complete(
        status=ExecutionStatus.SUCCESS,
        exit_code=0,
        output="Workflow completed successfully",
    )
    execute_result.session_id = "symphony-session-123"
    adapter.execute = AsyncMock(return_value=execute_result)

    # Mock resume method
    resume_result = ExecutionResult()
    resume_result.mark_complete(
        status=ExecutionStatus.SUCCESS,
        exit_code=0,
        output="Workflow resumed and completed",
    )
    resume_result.session_id = "symphony-session-123"
    adapter.resume = AsyncMock(return_value=resume_result)

    # Mock health check
    adapter.check_health = AsyncMock(return_value=True)

    return adapter


@pytest.fixture
def orchestrator(
    mock_config: MagicMock,
    temp_state_dir: Path,
    temp_skills_dir: Path,
) -> AutoflowOrchestrator:
    """Create an AutoflowOrchestrator instance for testing."""
    return AutoflowOrchestrator(
        config=mock_config,
        state_dir=temp_state_dir,
        skills_dir=temp_skills_dir,
        auto_initialize=False,
    )


# ============================================================================
# Symphony Workflow Execution Tests
# ============================================================================


class TestSymphonyWorkflowExecution:
    """Tests for Symphony workflow execution via orchestrator."""

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_success(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test successful Symphony workflow execution."""
        # Initialize orchestrator
        await orchestrator.initialize()

        # Mock the adapter availability
        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Implement the login feature",
                workdir="/tmp/test",
                timeout_seconds=300,
            )

        # Verify result
        assert result.success is True
        assert result.output == "Workflow completed successfully"
        assert result.session_id == "symphony-session-123"

        # Verify adapter was called correctly
        mock_symphony_adapter.execute.assert_called_once()
        call_args = mock_symphony_adapter.execute.call_args
        assert call_args[1]["prompt"] == "Implement the login feature"
        assert isinstance(call_args[1]["config"], AgentConfig)

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_with_metadata(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test Symphony workflow execution with custom metadata."""
        await orchestrator.initialize()

        metadata = {
            "workflow_type": "multi-agent",
            "priority": "high",
        }

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Analyze codebase",
                metadata=metadata,
            )

        assert result.success is True
        mock_symphony_adapter.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_status_tracking(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that orchestrator status is tracked correctly during workflow."""
        await orchestrator.initialize()

        # Check initial status
        assert orchestrator.status == OrchestratorStatus.IDLE

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            # Run workflow
            result = await orchestrator.run_symphony_workflow(task="Test task")
            assert result.success is True

        # Status should return to IDLE after completion
        assert orchestrator.status == OrchestratorStatus.IDLE

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_adapter_not_available(
        self,
        orchestrator: AutoflowOrchestrator,
    ) -> None:
        """Test error handling when Symphony adapter is not available."""
        await orchestrator.initialize()

        # Mock no adapters available
        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={},
        ):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.run_symphony_workflow(
                    task="Test task",
                )

            assert "Symphony adapter not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_failure(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test handling of Symphony workflow failure."""
        await orchestrator.initialize()

        # Mock a failed execution
        failure_result = ExecutionResult()
        failure_result.mark_complete(
            status=ExecutionStatus.FAILURE,
            exit_code=1,
            output="Workflow failed",
            error="Agent execution failed",
        )
        mock_symphony_adapter.execute = AsyncMock(return_value=failure_result)

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Failing task",
            )

        # Result should indicate failure
        assert result.success is False
        assert result.error == "Agent execution failed"

    @pytest.mark.asyncio
    async def test_run_symphony_workflow_statistics_tracking(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that workflow execution updates statistics correctly."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(task="Success task")

        # Verify statistics
        stats = orchestrator.stats
        assert stats.total_tasks == 1
        assert stats.completed_tasks == 1
        assert stats.failed_tasks == 0


# ============================================================================
# Symphony Session Resume Tests
# ============================================================================


class TestSymphonySessionResume:
    """Tests for Symphony session resume functionality."""

    @pytest.mark.asyncio
    async def test_resume_symphony_session(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test resuming an existing Symphony session."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Continue with the implementation",
                resume_session_id="existing-session-456",
            )

        assert result.success is True
        assert result.session_id == "symphony-session-123"

        # Verify resume was called instead of execute
        mock_symphony_adapter.resume.assert_called_once()
        mock_symphony_adapter.execute.assert_not_called()

        # Verify resume parameters
        call_args = mock_symphony_adapter.resume.call_args
        assert call_args[1]["session_id"] == "existing-session-456"
        assert call_args[1]["new_prompt"] == "Continue with the implementation"

    @pytest.mark.asyncio
    async def test_resume_symphony_session_failure(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test handling of resume failure."""
        await orchestrator.initialize()

        # Mock a failed resume
        failure_result = ExecutionResult()
        failure_result.mark_complete(
            status=ExecutionStatus.FAILURE,
            exit_code=1,
            error="Session not found",
        )
        mock_symphony_adapter.resume = AsyncMock(return_value=failure_result)

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Continue task",
                resume_session_id="nonexistent-session",
            )

        assert result.success is False
        assert "Session not found" in result.error


# ============================================================================
# State Persistence Tests
# ============================================================================


class TestSymphonyStatePersistence:
    """Tests for state persistence during Symphony workflow execution."""

    @pytest.mark.asyncio
    async def test_task_and_run_records_created(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
        temp_state_dir: Path,
    ) -> None:
        """Test that task and run records are created and persisted."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Implement feature",
                workdir="/tmp/project",
            )

        # Verify task was saved
        tasks = orchestrator.state.list_tasks()
        assert len(tasks) == 1
        task = tasks[0]
        assert task["title"] == "Implement feature"
        assert task["status"] == TaskStatus.COMPLETED

        # Verify run was saved
        runs = orchestrator.state.list_runs()
        assert len(runs) == 1
        run = runs[0]
        assert run["agent"] == "symphony"
        assert run["status"] == RunStatus.COMPLETED
        assert run["workdir"] == "/tmp/project"

    @pytest.mark.asyncio
    async def test_failed_workflow_state_updates(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that failed workflows update state correctly."""
        await orchestrator.initialize()

        # Mock a failed execution
        failure_result = ExecutionResult()
        failure_result.mark_complete(
            status=ExecutionStatus.FAILURE,
            exit_code=1,
            error="Execution failed",
        )
        mock_symphony_adapter.execute = AsyncMock(return_value=failure_result)

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Failing task",
            )

        # Verify task status
        tasks = orchestrator.state.list_tasks()
        assert tasks[0]["status"] == TaskStatus.FAILED

        # Verify run status and error
        runs = orchestrator.state.list_runs()
        assert runs[0]["status"] == RunStatus.FAILED
        assert runs[0]["error"] == "Execution failed"

    @pytest.mark.asyncio
    async def test_workflow_with_metadata_persisted(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that workflow metadata is persisted correctly."""
        await orchestrator.initialize()

        metadata = {
            "workflow_id": "wf-123",
            "agents": ["coder", "tester"],
            "priority": "high",
        }

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Test task",
                metadata=metadata,
            )

        # Verify metadata was saved
        tasks = orchestrator.state.list_tasks()
        assert tasks[0]["metadata"] == metadata


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestSymphonyErrorHandling:
    """Tests for error handling in Symphony workflow execution."""

    @pytest.mark.asyncio
    async def test_workflow_execution_exception(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test handling of exceptions during workflow execution."""
        await orchestrator.initialize()

        # Mock an exception during execution
        mock_symphony_adapter.execute = AsyncMock(
            side_effect=Exception("Symphony CLI crashed"),
        )

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.run_symphony_workflow(
                    task="Test task",
                )

            assert "Symphony workflow execution failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_workflow_timeout(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test handling of workflow timeout."""
        await orchestrator.initialize()

        # Mock a timeout result
        timeout_result = ExecutionResult()
        timeout_result.mark_complete(
            status=ExecutionStatus.TIMEOUT,
            exit_code=-1,
            error="Execution timed out after 300 seconds",
        )
        mock_symphony_adapter.execute = AsyncMock(return_value=timeout_result)

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            result = await orchestrator.run_symphony_workflow(
                task="Long running task",
                timeout_seconds=300,
            )

        assert result.success is False
        assert "timed out" in result.error.lower()

    @pytest.mark.asyncio
    async def test_status_cleanup_on_error(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that orchestrator status is cleaned up even on error."""
        await orchestrator.initialize()

        mock_symphony_adapter.execute = AsyncMock(
            side_effect=Exception("Test error"),
        )

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            try:
                await orchestrator.run_symphony_workflow(
                    task="Failing task",
                )
            except OrchestratorError:
                pass

        # Status should still return to IDLE
        assert orchestrator.status == OrchestratorStatus.IDLE
        assert orchestrator._current_task is None


# ============================================================================
# Configuration Tests
# ============================================================================


class TestSymphonyConfiguration:
    """Tests for Symphony configuration handling."""

    @pytest.mark.asyncio
    async def test_default_timeout_used(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test that default timeout from config is used."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Test task",
            )

        # Verify timeout was set from config
        call_args = mock_symphony_adapter.execute.call_args
        assert call_args[1]["config"].timeout_seconds == 600

    @pytest.mark.asyncio
    async def test_custom_timeout_overrides_default(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test that custom timeout overrides config default."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Test task",
                timeout_seconds=900,
            )

        # Verify custom timeout was used
        call_args = mock_symphony_adapter.execute.call_args
        assert call_args[1]["config"].timeout_seconds == 900

    @pytest.mark.asyncio
    async def test_default_workdir(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test that default workdir is used when not specified."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            await orchestrator.run_symphony_workflow(
                task="Test task",
            )

        # Verify current working directory was used
        call_args = mock_symphony_adapter.execute.call_args
        workdir = call_args[1]["workdir"]
        # Should be a Path object pointing to current directory
        assert isinstance(workdir, Path)


# ============================================================================
# Integration Tests
# ============================================================================


class TestSymphonyIntegration:
    """Integration tests for Symphony workflow execution."""

    @pytest.mark.asyncio
    async def test_full_workflow_lifecycle(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test complete workflow lifecycle from start to finish."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            # Execute workflow
            result = await orchestrator.run_symphony_workflow(
                task="Implement login feature with tests",
                timeout_seconds=600,
                metadata={"feature": "login"},
            )

        # Verify success
        assert result.success is True

        # Verify state persistence
        tasks = orchestrator.state.list_tasks()
        runs = orchestrator.state.list_runs()
        assert len(tasks) == 1
        assert len(runs) == 1

        # Verify statistics
        stats = orchestrator.stats
        assert stats.total_tasks == 1
        assert stats.completed_tasks == 1

        # Verify status returned to idle
        assert orchestrator.status == OrchestratorStatus.IDLE

    @pytest.mark.asyncio
    async def test_multiple_sequential_workflows(
        self,
        orchestrator: AutoflowOrchestrator,
        mock_symphony_adapter: MagicMock,
    ) -> None:
        """Test running multiple workflows sequentially."""
        await orchestrator.initialize()

        with patch.object(
            orchestrator,
            "_get_available_adapters",
            return_value={"symphony": mock_symphony_adapter},
        ):
            # Run first workflow
            result1 = await orchestrator.run_symphony_workflow(
                task="First workflow",
            )
            assert result1.success is True

            # Run second workflow
            result2 = await orchestrator.run_symphony_workflow(
                task="Second workflow",
            )
            assert result2.success is True

        # Verify both were tracked
        tasks = orchestrator.state.list_tasks()
        runs = orchestrator.state.list_runs()
        assert len(tasks) == 2
        assert len(runs) == 2

        # Verify statistics
        stats = orchestrator.stats
        assert stats.total_tasks == 2
        assert stats.completed_tasks == 2


# ============================================================================
# Review Gate Checkpoint Tests
# ============================================================================


class TestCheckpointReviewGates:
    """Tests for review gate and checkpoint integration."""

    @pytest.fixture
    def symphony_bridge(
        self,
        temp_state_dir: Path,
    ) -> Any:
        """Create a SymphonyBridge instance for testing."""
        from autoflow.skills.symphony_bridge import SymphonyBridge

        return SymphonyBridge(state_dir=temp_state_dir)

    @pytest.fixture
    def mock_gate_config(self) -> Any:
        """Create a mock gate configuration."""
        from autoflow.ci.gates import GateConfig

        return GateConfig(
            enabled=True,
            timeout_seconds=300,
        )

    # ------------------------------------------------------------------------
    # Checkpoint Creation Tests
    # ------------------------------------------------------------------------

    def test_create_gate_checkpoint(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test creating a checkpoint at a review gate."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
            require_approval=True,
        )

        # Verify checkpoint ID format
        assert checkpoint_id.startswith("checkpoint-")
        assert len(checkpoint_id) > 20

        # Verify checkpoint was saved
        status = symphony_bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["status"] == "pending"
        assert status["gate_name"] == "Tests"
        assert status["gate_type"] == "test"
        assert status["require_approval"] is True

    def test_create_gate_checkpoint_with_custom_name(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test creating a checkpoint with a custom name."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Security",
            gate_type="security",
            workdir=workdir,
            checkpoint_name="custom-security-check",
        )

        status = symphony_bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["gate_name"] == "Security"
        assert status["gate_type"] == "security"

    def test_create_gate_checkpoint_with_metadata(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test creating a checkpoint with additional metadata."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        metadata = {
            "test_count": 42,
            "coverage_percentage": 85.5,
        }

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
            metadata=metadata,
        )

        # Metadata should be stored with checkpoint
        gate_checkpoint_run_id = f"gate-checkpoint-{checkpoint_id}"
        run_data = symphony_bridge._state_manager.load_run(gate_checkpoint_run_id)
        checkpoint_info = run_data["metadata"]["symphony_checkpoint"]
        assert checkpoint_info["metadata"] == metadata

    def test_create_gate_checkpoint_without_state_manager(self) -> None:
        """Test error handling when state manager is not initialized."""
        from autoflow.skills.symphony_bridge import SymphonyBridge, SymphonyBridgeError

        bridge = SymphonyBridge()  # No state_dir

        with pytest.raises(SymphonyBridgeError) as exc_info:
            bridge.create_gate_checkpoint(
                gate_name="Tests",
                gate_type="test",
                workdir="/tmp",
            )

        assert "State manager not initialized" in str(exc_info.value)

    # ------------------------------------------------------------------------
    # Checkpoint Status Tests
    # ------------------------------------------------------------------------

    def test_get_gate_checkpoint_status(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test getting checkpoint status."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Lint",
            gate_type="lint",
            workdir=workdir,
        )

        status = symphony_bridge.get_gate_checkpoint_status(checkpoint_id)

        assert status["checkpoint_id"] == checkpoint_id
        assert status["status"] == "pending"
        assert status["gate_name"] == "Lint"
        assert status["gate_type"] == "lint"
        assert status["created_at"] is not None
        assert status["approved_at"] is None
        assert status["rejected_at"] is None

    def test_get_gate_checkpoint_status_not_found(
        self,
        symphony_bridge: Any,
    ) -> None:
        """Test getting status of non-existent checkpoint."""
        from autoflow.skills.symphony_bridge import SymphonyBridgeError

        with pytest.raises(SymphonyBridgeError) as exc_info:
            symphony_bridge.get_gate_checkpoint_status("nonexistent-checkpoint")

        assert "not found" in str(exc_info.value).lower()

    # ------------------------------------------------------------------------
    # Checkpoint Approval Tests
    # ------------------------------------------------------------------------

    def test_approve_gate_checkpoint(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test approving a checkpoint."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Approve checkpoint
        success = symphony_bridge.approve_gate_checkpoint(
            checkpoint_id=checkpoint_id,
            approver="reviewer-1",
            notes="All tests passed",
        )

        assert success is True

        # Verify status updated
        status = symphony_bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["status"] == "approved"
        assert status["approved_at"] is not None

    def test_approve_nonexistent_checkpoint(
        self,
        symphony_bridge: Any,
    ) -> None:
        """Test approving a non-existent checkpoint."""
        from autoflow.skills.symphony_bridge import SymphonyBridgeError

        with pytest.raises(SymphonyBridgeError) as exc_info:
            symphony_bridge.approve_gate_checkpoint(
                checkpoint_id="nonexistent-checkpoint",
            )

        assert "not found" in str(exc_info.value).lower()

    # ------------------------------------------------------------------------
    # Checkpoint Rejection Tests
    # ------------------------------------------------------------------------

    def test_reject_gate_checkpoint(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test rejecting a checkpoint."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Security",
            gate_type="security",
            workdir=workdir,
        )

        # Reject checkpoint
        success = symphony_bridge.reject_gate_checkpoint(
            checkpoint_id=checkpoint_id,
            reason="Security vulnerabilities found",
            rejecter="security-reviewer",
        )

        assert success is True

        # Verify status updated
        status = symphony_bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["status"] == "rejected"
        assert status["rejected_at"] is not None

    # ------------------------------------------------------------------------
    # Checkpoint Waiting Tests
    # ------------------------------------------------------------------------

    def test_wait_for_checkpoint_approval(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test waiting for checkpoint approval."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Approve in background after short delay
        import threading
        import time

        def approve_after_delay():
            time.sleep(0.1)
            symphony_bridge.approve_gate_checkpoint(
                checkpoint_id=checkpoint_id,
                approver="reviewer",
            )

        thread = threading.Thread(target=approve_after_delay)
        thread.start()

        # Wait for approval (should succeed)
        approved = symphony_bridge.wait_for_gate_checkpoint_approval(
            checkpoint_id=checkpoint_id,
            timeout_seconds=5,
        )

        thread.join()
        assert approved is True

    def test_wait_for_checkpoint_rejection(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test waiting when checkpoint is rejected."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Reject immediately
        symphony_bridge.reject_gate_checkpoint(
            checkpoint_id=checkpoint_id,
            reason="Tests failed",
        )

        # Wait for approval (should return False)
        approved = symphony_bridge.wait_for_gate_checkpoint_approval(
            checkpoint_id=checkpoint_id,
            timeout_seconds=1,
        )

        assert approved is False

    def test_wait_for_checkpoint_timeout(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test waiting for checkpoint with timeout."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Wait without approving (should timeout)
        approved = symphony_bridge.wait_for_gate_checkpoint_approval(
            checkpoint_id=checkpoint_id,
            timeout_seconds=1,
        )

        assert approved is False

    # ------------------------------------------------------------------------
    # Checkpoint Listing Tests
    # ------------------------------------------------------------------------

    def test_list_gate_checkpoints(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test listing all gate checkpoints."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        # Create multiple checkpoints
        cp1 = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )
        cp2 = symphony_bridge.create_gate_checkpoint(
            gate_name="Lint",
            gate_type="lint",
            workdir=workdir,
        )
        cp3 = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # List all checkpoints
        all_checkpoints = symphony_bridge.list_gate_checkpoints()
        assert len(all_checkpoints) == 3

        # Filter by gate type
        test_checkpoints = symphony_bridge.list_gate_checkpoints(gate_type="test")
        assert len(test_checkpoints) == 2

        # Filter by gate name
        lint_checkpoints = symphony_bridge.list_gate_checkpoints(gate_name="Lint")
        assert len(lint_checkpoints) == 1

    def test_list_gate_checkpoints_by_status(
        self,
        symphony_bridge: Any,
        tmp_path: Path,
    ) -> None:
        """Test listing checkpoints filtered by status."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        # Create checkpoints
        cp1 = symphony_bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )
        cp2 = symphony_bridge.create_gate_checkpoint(
            gate_name="Lint",
            gate_type="lint",
            workdir=workdir,
        )

        # Approve one
        symphony_bridge.approve_gate_checkpoint(cp1)

        # List pending
        pending = symphony_bridge.list_gate_checkpoints(status="pending")
        assert len(pending) == 1
        assert pending[0]["checkpoint_id"] == cp2

        # List approved
        approved = symphony_bridge.list_gate_checkpoints(status="approved")
        assert len(approved) == 1
        assert approved[0]["checkpoint_id"] == cp1

    # ------------------------------------------------------------------------
    # SymphonyCheckpointGate Tests
    # ------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_checkpoint_gate_without_symphony(
        self,
        mock_gate_config: Any,
    ) -> None:
        """Test checkpoint gate pass-through when Symphony unavailable."""
        from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

        # Create a checkpoint gate wrapping a test gate
        test_gate = TestGate(config=mock_gate_config)
        checkpoint_gate = SymphonyCheckpointGate(
            wrapped_gate=test_gate,
            require_approval=False,
        )

        # Should pass through to wrapped gate
        result = await checkpoint_gate.run()

        # Gate should execute normally (checkpoint skipped when Symphony unavailable)
        # The checkpoint gate has its own name, but wraps the test gate
        assert result.gate_name == "Symphony Checkpoint"
        assert result.metadata["wrapped_gate"] == "Tests"

    @pytest.mark.asyncio
    async def test_checkpoint_gate_properties(
        self,
        mock_gate_config: Any,
    ) -> None:
        """Test checkpoint gate property access."""
        from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

        test_gate = TestGate(config=mock_gate_config)
        checkpoint_gate = SymphonyCheckpointGate(
            wrapped_gate=test_gate,
            checkpoint_name="test-checkpoint",
            require_approval=True,
        )

        # Verify properties
        assert checkpoint_gate.wrapped_gate.gate_name == "Tests"
        assert checkpoint_gate.checkpoint_name == "test-checkpoint"
        assert checkpoint_gate._require_approval is True  # Private field
        assert checkpoint_gate.checkpoint_id is None  # Not created yet

    @pytest.mark.asyncio
    async def test_checkpoint_gate_check_delegation(
        self,
        mock_gate_config: Any,
    ) -> None:
        """Test that checkpoint gate delegates check operations to wrapped gate."""
        from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

        test_gate = TestGate(config=mock_gate_config)
        checkpoint_gate = SymphonyCheckpointGate(wrapped_gate=test_gate)

        # Check operations should delegate
        assert "pytest" in checkpoint_gate.check_names

        # Add check should delegate
        checkpoint_gate.add_check(
            name="custom-test",
            command=["pytest", "tests/custom/"],
            required=False,
        )

        assert "custom-test" in checkpoint_gate.check_names

        # Remove check should delegate
        removed = checkpoint_gate.remove_check("custom-test")
        assert removed is True
        assert "custom-test" not in checkpoint_gate.check_names

    @pytest.mark.asyncio
    async def test_checkpoint_gate_approve_reject(
        self,
        mock_gate_config: Any,
    ) -> None:
        """Test checkpoint gate approve/reject methods."""
        from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

        test_gate = TestGate(config=mock_gate_config)
        checkpoint_gate = SymphonyCheckpointGate(
            wrapped_gate=test_gate,
            require_approval=True,
        )

        # These should not raise errors even without Symphony
        checkpoint_gate.approve_checkpoint(approver="reviewer", notes="Approved")
        checkpoint_gate.reject_checkpoint(reason="Test", rejecter="reviewer")

    def test_checkpoint_gate_repr(
        self,
        mock_gate_config: Any,
    ) -> None:
        """Test checkpoint gate string representation."""
        from autoflow.ci.gates import SymphonyCheckpointGate, TestGate

        test_gate = TestGate(config=mock_gate_config)
        checkpoint_gate = SymphonyCheckpointGate(
            wrapped_gate=test_gate,
            checkpoint_name="test-cp",
        )

        repr_str = repr(checkpoint_gate)
        assert "SymphonyCheckpointGate" in repr_str
        assert "Tests" in repr_str  # wrapped gate name
        assert "test-cp" in repr_str  # checkpoint name

    # ------------------------------------------------------------------------
    # Approval Flow from Checkpoint Tests
    # ------------------------------------------------------------------------

    def test_load_checkpoint_for_approval(
        self,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test loading checkpoint data for approval."""
        from autoflow.skills.symphony_bridge import SymphonyBridge
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        # Create checkpoint
        bridge = SymphonyBridge(state_dir=temp_state_dir)
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Load checkpoint for approval
        approval_config = ApprovalGateConfig()
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        checkpoint_data = approval_gate.load_checkpoint_for_approval(checkpoint_id)

        assert checkpoint_data is not None
        assert checkpoint_data["checkpoint_id"] == checkpoint_id
        assert checkpoint_data["gate_name"] == "Tests"
        assert checkpoint_data["gate_type"] == "test"

    def test_load_checkpoint_for_approval_not_found(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test loading non-existent checkpoint for approval."""
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        approval_config = ApprovalGateConfig()
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        checkpoint_data = approval_gate.load_checkpoint_for_approval("nonexistent")

        assert checkpoint_data is None

    def test_grant_approval_from_checkpoint(
        self,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test granting approval from checkpoint results."""
        from autoflow.skills.symphony_bridge import SymphonyBridge
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        # Create and approve checkpoint
        bridge = SymphonyBridge(state_dir=temp_state_dir)
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
            metadata={
                "test_results": {"total": 10, "passed": 10, "failed": 0, "skipped": 0},
                "coverage_data": {"total": 85.0},
                "qa_findings_count": {"CRITICAL": 0, "HIGH": 0},
            },
        )

        bridge.approve_gate_checkpoint(checkpoint_id, approver="reviewer")

        # Grant approval from checkpoint
        # Disable coverage requirement for testing
        approval_config = ApprovalGateConfig(require_coverage=False)
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        approved, messages = approval_gate.grant_approval_from_checkpoint(
            checkpoint_id=checkpoint_id,
            git_commit="abc123",
        )

        # Show messages if failed
        if not approved:
            print(f"\nApproval failed. Messages: {messages}")

        assert approved is True
        # Note: messages may contain informational messages like "Approval granted"
        # so we don't check len(messages) == 0

        # Verify token was created
        token = approval_gate.load_token()
        assert token is not None
        assert token.metadata["source"] == "symphony_checkpoint"
        assert token.metadata["checkpoint_id"] == checkpoint_id

    def test_grant_approval_from_unapproved_checkpoint(
        self,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test granting approval from unapproved checkpoint."""
        from autoflow.skills.symphony_bridge import SymphonyBridge
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        # Create checkpoint but don't approve
        bridge = SymphonyBridge(state_dir=temp_state_dir)
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
        )

        # Try to grant approval from pending checkpoint
        approval_config = ApprovalGateConfig()
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        approved, messages = approval_gate.grant_approval_from_checkpoint(
            checkpoint_id=checkpoint_id,
        )

        assert approved is False
        assert any("Only approved checkpoints" in m for m in messages)

    def test_verify_checkpoint_approval(
        self,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test verifying checkpoint approval."""
        from autoflow.skills.symphony_bridge import SymphonyBridge
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        # Create, approve, and grant approval from checkpoint
        bridge = SymphonyBridge(state_dir=temp_state_dir)
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = bridge.create_gate_checkpoint(
            gate_name="Tests",
            gate_type="test",
            workdir=workdir,
            metadata={
                "test_results": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
                "coverage_data": {"total": 90.0},
                "qa_findings_count": {"CRITICAL": 0, "HIGH": 0},
            },
        )

        bridge.approve_gate_checkpoint(checkpoint_id)

        approval_config = ApprovalGateConfig(require_coverage=False)
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        # Grant approval from checkpoint
        approved, _ = approval_gate.grant_approval_from_checkpoint(checkpoint_id)
        assert approved is True

        # Verify checkpoint approval
        is_valid, messages = approval_gate.verify_checkpoint_approval(checkpoint_id)

        assert is_valid is True
        assert any("valid" in m.lower() for m in messages)

    def test_create_token_from_checkpoint_results(
        self,
        temp_state_dir: Path,
    ) -> None:
        """Test creating approval token directly from checkpoint results."""
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        approval_config = ApprovalGateConfig()
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        # Create token from raw checkpoint results
        token = approval_gate.create_token_from_checkpoint_results(
            test_results={"total": 20, "passed": 20, "failed": 0, "skipped": 0},
            coverage_data={"total": 95.0, "branches": 92.0, "functions": 98.0},
            qa_findings_count={"CRITICAL": 0, "HIGH": 0, "MEDIUM": 1, "LOW": 3},
            checkpoint_id="checkpoint-test-validation-abc123",
            gate_name="Tests",
            gate_type="test",
            git_commit="def456",
            approved_at="2026-03-08T12:00:00",
            approver="code-reviewer",
        )

        assert token is not None
        assert token.metadata["source"] == "symphony_checkpoint"
        assert token.metadata["checkpoint_id"] == "checkpoint-test-validation-abc123"
        assert token.metadata["gate_name"] == "Tests"
        assert token.metadata["gate_type"] == "test"
        assert token.metadata["approved_at"] == "2026-03-08T12:00:00"
        assert token.metadata["approver"] == "code-reviewer"
        assert token.test_results["total"] == 20
        assert token.coverage_data["total"] == 95.0

    # ------------------------------------------------------------------------
    # Integration: End-to-End Checkpoint Flow Tests
    # ------------------------------------------------------------------------

    def test_full_checkpoint_approval_flow(
        self,
        temp_state_dir: Path,
        tmp_path: Path,
    ) -> None:
        """Test complete flow from checkpoint creation to approval token."""
        from autoflow.skills.symphony_bridge import SymphonyBridge
        from autoflow.review.approval import ApprovalGate, ApprovalGateConfig

        # Step 1: Create checkpoint at gate
        bridge = SymphonyBridge(state_dir=temp_state_dir)
        workdir = tmp_path / "project"
        workdir.mkdir()

        checkpoint_id = bridge.create_gate_checkpoint(
            gate_name="Security",
            gate_type="security",
            workdir=workdir,
            require_approval=True,
            metadata={
                "test_results": {"total": 15, "passed": 15, "failed": 0, "skipped": 0},
                "coverage_data": {"total": 88.0},
                "qa_findings_count": {"CRITICAL": 0, "HIGH": 0},
            },
        )

        # Step 2: Verify checkpoint is pending
        status = bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["status"] == "pending"

        # Step 3: Approve checkpoint
        bridge.approve_gate_checkpoint(
            checkpoint_id=checkpoint_id,
            approver="security-reviewer",
            notes="All security checks passed",
        )

        # Step 4: Verify checkpoint is approved
        status = bridge.get_gate_checkpoint_status(checkpoint_id)
        assert status["status"] == "approved"
        assert status["approver"] == "security-reviewer"

        # Step 5: Grant Autoflow approval from checkpoint
        # Disable coverage requirement for testing
        approval_config = ApprovalGateConfig(require_coverage=False)
        approval_gate = ApprovalGate(config=approval_config, work_dir=str(temp_state_dir))

        approved, messages = approval_gate.grant_approval_from_checkpoint(
            checkpoint_id=checkpoint_id,
            git_commit="abc123def",
        )

        assert approved is True

        # Step 6: Verify approval token exists and is valid
        is_valid, _ = approval_gate.verify_checkpoint_approval(checkpoint_id)
        assert is_valid is True

        # Step 7: Verify token metadata
        token = approval_gate.load_token()
        assert token.metadata["checkpoint_id"] == checkpoint_id
        assert token.metadata["gate_name"] == "Security"
        assert token.metadata["gate_type"] == "security"
