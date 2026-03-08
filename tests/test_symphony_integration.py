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
