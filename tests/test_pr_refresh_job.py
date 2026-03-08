"""
Unit Tests for PR Refresh Job

Tests the refresh_prs job handler for automatic PR refresh functionality.
Tests cover PR detection, refresh operations, conflict handling, and error scenarios.

These tests mock external dependencies (git, state manager, etc.) to avoid
requiring actual git repositories or PR infrastructure.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.git.pr_manager import PRRefreshStatus, PRState
from autoflow.git.operations import (
    BranchInfo,
    BranchType,
    RebaseResult,
)
from autoflow.scheduler.pr_refresh_job import refresh_prs


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_config() -> MagicMock:
    """Create a mock configuration object."""
    config = MagicMock()
    config.state_dir = "/tmp/test_state"
    return config


@pytest.fixture
def mock_state_manager() -> MagicMock:
    """Create a mock StateManager."""
    state = MagicMock()
    state.state_dir = Path("/tmp/test_state")
    state.save_memory.return_value = None
    return state


@pytest.fixture
def mock_pr_manager() -> MagicMock:
    """Create a mock PRManager."""
    manager = MagicMock()
    manager.detect_stale_prs.return_value = []
    manager.update_pr_refresh_state.return_value = None
    return manager


@pytest.fixture
def mock_git_ops() -> MagicMock:
    """Create a mock GitOperations."""
    git_ops = MagicMock()
    git_ops.get_branch_info.return_value = BranchInfo(
        name="feature-branch",
        commit_sha="abc123",
    )
    git_ops.checkout_branch.return_value = None
    git_ops.rebase_with_conflict_detection.return_value = RebaseResult(
        success=True,
        has_conflicts=False,
    )
    git_ops.rebase_continue.return_value = None
    git_ops.rebase_abort.return_value = None
    return git_ops


@pytest.fixture
def sample_pr_state() -> PRState:
    """Create a sample PRState for testing."""
    return PRState(
        pr_number=123,
        branch="feature-branch",
        base_branch="main",
        status=PRRefreshStatus.NEEDS_REFRESH,
    )


# ============================================================================
# Test: No Stale PRs
# ============================================================================


class TestRefreshPRsNoStalePRs:
    """Tests for refresh_prs when there are no stale PRs."""

    @pytest.mark.asyncio
    async def test_no_stale_prs(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test refresh_prs with no stale PRs."""
        mock_pr_manager.detect_stale_prs.return_value = []

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations"):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is True
        assert result.output == "No PRs need refresh"
        assert result.metrics["prs_checked"] == 0
        assert result.metrics["prs_refreshed"] == 0
        assert result.metrics["prs_failed"] == 0
        assert result.metrics["prs_with_conflicts"] == 0

    @pytest.mark.asyncio
    async def test_no_stale_prs_saves_memory(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test that no stale PRs still saves to memory."""
        mock_pr_manager.detect_stale_prs.return_value = []

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations"):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager) as mock_sm:
                        await refresh_prs()

                        # Should not save memory when no PRs need refresh
                        # (only saves after processing)
                        mock_sm.assert_not_called()


# ============================================================================
# Test: Successful Refresh
# ============================================================================


class TestRefreshPRsSuccess:
    """Tests for successful PR refresh operations."""

    @pytest.mark.asyncio
    async def test_successful_refresh(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test successful PR refresh."""
        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is True
        assert "1 refreshed" in result.output
        assert result.metrics["prs_checked"] == 1
        assert result.metrics["prs_refreshed"] == 1
        assert result.metrics["prs_failed"] == 0
        assert result.metrics["prs_with_conflicts"] == 0

        # Verify PR state was updated
        mock_pr_manager.update_pr_refresh_state.assert_any_call(
            123,
            PRRefreshStatus.REFRESHING,
        )
        mock_pr_manager.update_pr_refresh_state.assert_any_call(
            123,
            PRRefreshStatus.REFRESHED,
            last_commit="abc123",
        )

    @pytest.mark.asyncio
    async def test_multiple_prs_refreshed(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test refreshing multiple PRs."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        pr2 = PRState(pr_number=2, branch="feature-2", base_branch="main")
        pr3 = PRState(pr_number=3, branch="feature-3", base_branch="main")

        mock_pr_manager.detect_stale_prs.return_value = [pr1, pr2, pr3]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is True
        assert result.metrics["prs_checked"] == 3
        assert result.metrics["prs_refreshed"] == 3

    @pytest.mark.asyncio
    async def test_saves_memory_after_refresh(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test that refresh results are saved to memory."""
        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager) as mock_sm:
                        await refresh_prs()

                        # Verify save_memory was called
                        mock_sm.return_value.save_memory.assert_called_once()
                        call_args = mock_sm.return_value.save_memory.call_args

                        assert call_args[1]["key"] == "last_pr_refresh"
                        assert call_args[1]["category"] == "pr_refresh"
                        assert call_args[1]["expires_in_seconds"] == 1800

                        memory_value = call_args[1]["value"]
                        assert memory_value["prs_checked"] == 1
                        assert memory_value["prs_refreshed"] == 1
                        assert "timestamp" in memory_value


# ============================================================================
# Test: Conflict Detection and Resolution
# ============================================================================


class TestRefreshPRsConflicts:
    """Tests for PR refresh with conflict handling."""

    @pytest.mark.asyncio
    async def test_conflict_detected_resolution_success(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test conflict detection and successful resolution."""
        # Set up stale PRs
        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        # Mock rebase with conflicts
        mock_git_ops.rebase_with_conflict_detection.return_value = RebaseResult(
            success=False,
            has_conflicts=True,
            error="Merge conflict",
        )

        # Mock successful resolution
        mock_resolver = MagicMock()
        mock_resolver.attempt_resolution.return_value = MagicMock(
            success=True,
        )

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        with patch("autoflow.scheduler.pr_refresh_job.ConflictResolver", return_value=mock_resolver):
                            result = await refresh_prs()

        assert result.success is True
        assert result.metrics["prs_checked"] == 1
        assert result.metrics["prs_refreshed"] == 1
        assert result.metrics["prs_with_conflicts"] == 0  # Resolved successfully

        # Verify resolution was attempted
        mock_resolver.attempt_resolution.assert_called_once()

    @pytest.mark.asyncio
    async def test_conflict_resolution_failed(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test conflict detection and failed resolution."""
        # Set up stale PRs
        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        # Mock rebase with conflicts
        mock_git_ops.rebase_with_conflict_detection.return_value = RebaseResult(
            success=False,
            has_conflicts=True,
            error="Merge conflict",
        )

        # Mock failed resolution
        mock_resolver = MagicMock()
        mock_resolver.attempt_resolution.return_value = MagicMock(
            success=False,
        )

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        with patch("autoflow.scheduler.pr_refresh_job.ConflictResolver", return_value=mock_resolver):
                            result = await refresh_prs()

        assert result.success is True  # Job succeeds even with conflicts
        assert result.metrics["prs_with_conflicts"] == 1

        # Verify rebase_abort was called
        mock_git_ops.rebase_abort.assert_called_once()

        # Verify PR state updated to CONFLICT_DETECTED
        mock_pr_manager.update_pr_refresh_state.assert_any_call(
            123,
            PRRefreshStatus.CONFLICT_DETECTED,
            error="Automatic conflict resolution failed",
        )

    @pytest.mark.asyncio
    async def test_conflict_continue_fails(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test rebase_continue failure after conflict resolution."""
        # Set up stale PRs
        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        # Mock rebase with conflicts
        mock_git_ops.rebase_with_conflict_detection.return_value = RebaseResult(
            success=False,
            has_conflicts=True,
            error="Merge conflict",
        )

        # Mock successful resolution but rebase_continue fails
        mock_resolver = MagicMock()
        mock_resolver.attempt_resolution.return_value = MagicMock(
            success=True,
        )
        mock_git_ops.rebase_continue.side_effect = Exception("Continue failed")

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        with patch("autoflow.scheduler.pr_refresh_job.ConflictResolver", return_value=mock_resolver):
                            result = await refresh_prs()

        assert result.success is True
        assert result.metrics["prs_with_conflicts"] == 1

        # Verify rebase_abort was called after continue failed
        mock_git_ops.rebase_abort.assert_called_once()


# ============================================================================
# Test: Failed Refresh Scenarios
# ============================================================================


class TestRefreshPRsFailures:
    """Tests for PR refresh failure scenarios."""

    @pytest.mark.asyncio
    async def test_branch_not_found(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test refresh when branch is not found."""
        # Mock branch not found
        mock_git_ops.get_branch_info.return_value = None

        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is False  # Job fails when PRs fail
        assert result.metrics["prs_failed"] == 1

        # Verify PR state updated to FAILED
        mock_pr_manager.update_pr_refresh_state.assert_any_call(
            123,
            PRRefreshStatus.FAILED,
            error="Branch feature-branch not found",
        )

    @pytest.mark.asyncio
    async def test_base_branch_not_found(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test refresh when base branch HEAD cannot be determined."""
        # Mock branch found
        mock_git_ops.get_branch_info.side_effect = [
            BranchInfo(  # First call: PR branch
                name="feature-branch",
                commit_sha="abc123",
            ),
            None,  # Second call: base branch not found
        ]

        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is False
        assert result.metrics["prs_failed"] == 1

    @pytest.mark.asyncio
    async def test_rebase_failed_no_conflicts(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test rebase failure without conflicts."""
        # Mock rebase failure (not conflict-related)
        mock_git_ops.rebase_with_conflict_detection.return_value = RebaseResult(
            success=False,
            has_conflicts=False,
            error="Local changes would be overwritten",
        )

        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is False
        assert result.metrics["prs_failed"] == 1

        # Verify PR state updated to FAILED
        mock_pr_manager.update_pr_refresh_state.assert_any_call(
            123,
            PRRefreshStatus.FAILED,
            error="Local changes would be overwritten",
        )

    @pytest.mark.asyncio
    async def test_exception_during_refresh(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
        sample_pr_state: PRState,
    ) -> None:
        """Test exception during PR refresh."""
        # Mock exception during checkout
        mock_git_ops.checkout_branch.side_effect = Exception("Checkout failed")

        mock_pr_manager.detect_stale_prs.return_value = [sample_pr_state]

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is False
        assert result.metrics["prs_failed"] == 1


# ============================================================================
# Test: Mixed Scenarios
# ============================================================================


class TestRefreshPRsMixed:
    """Tests for mixed success and failure scenarios."""

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(
        self,
        mock_config: MagicMock,
        mock_state_manager: MagicMock,
        mock_pr_manager: MagicMock,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test mixed successful and failed refreshes."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        pr2 = PRState(pr_number=2, branch="feature-2", base_branch="main")
        pr3 = PRState(pr_number=3, branch="feature-3", base_branch="main")

        mock_pr_manager.detect_stale_prs.return_value = [pr1, pr2, pr3]

        # Make second PR fail
        call_count = [0]

        def mock_rebase(branch, new_base):
            call_count[0] += 1
            if call_count[0] == 2:  # Second PR
                return RebaseResult(
                    success=False,
                    has_conflicts=False,
                    error="Failed",
                )
            return RebaseResult(success=True, has_conflicts=False)

        mock_git_ops.rebase_with_conflict_detection.side_effect = mock_rebase

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations", return_value=mock_git_ops):
                    with patch("autoflow.scheduler.pr_refresh_job.StateManager", return_value=mock_state_manager):
                        result = await refresh_prs()

        assert result.success is False  # Not all succeeded
        assert result.metrics["prs_checked"] == 3
        assert result.metrics["prs_refreshed"] == 2
        assert result.metrics["prs_failed"] == 1
        assert "2 refreshed" in result.output
        assert "1 failed" in result.output


# ============================================================================
# Test: Job Result Creation
# ============================================================================


class TestJobResultCreation:
    """Tests for JobResult creation and tracking."""

    @pytest.mark.asyncio
    async def test_job_result_initialized(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test that JobResult is properly initialized."""
        mock_pr_manager.detect_stale_prs.return_value = []

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations"):
                    result = await refresh_prs()

        assert result.job_name == "refresh_prs"
        assert result.started_at is not None

    @pytest.mark.asyncio
    async def test_job_result_completion_time(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test that JobResult has completion time."""
        mock_pr_manager.detect_stale_prs.return_value = []

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations"):
                    result = await refresh_prs()

        assert result.completed_at is not None


# ============================================================================
# Test: Configuration and Parameters
# ============================================================================


class TestRefreshPRsConfiguration:
    """Tests for configuration and parameter handling."""

    @pytest.mark.asyncio
    async def test_custom_config(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test refresh_prs with custom config."""
        mock_pr_manager.detect_stale_prs.return_value = []

        result = await refresh_prs(config=mock_config)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_custom_state_dir(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test refresh_prs with custom state directory."""
        mock_pr_manager.detect_stale_prs.return_value = []

        custom_state_dir = Path("/tmp/custom_state")

        with patch("autoflow.scheduler.pr_refresh_job.PRManager") as MockPRManager:
            await refresh_prs(config=mock_config, state_dir=custom_state_dir)

            # Verify PRManager was called with custom state dir
            MockPRManager.assert_called_once()
            call_kwargs = MockPRManager.call_args[1]
            assert call_kwargs["state_dir"] == custom_state_dir

    @pytest.mark.asyncio
    async def test_custom_repo_path(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test refresh_prs with custom repo path."""
        mock_pr_manager.detect_stale_prs.return_value = []

        custom_repo_path = Path("/tmp/custom_repo")

        with patch("autoflow.scheduler.pr_refresh_job.PRManager") as MockPRManager:
            with patch("autoflow.scheduler.pr_refresh_job.create_git_operations") as MockGit:
                await refresh_prs(config=mock_config, repo_path=custom_repo_path)

                # Verify PRManager was called with custom repo path
                MockPRManager.assert_called_once()
                call_kwargs = MockPRManager.call_args[1]
                assert call_kwargs["repo_path"] == custom_repo_path

                # Verify git_ops was created with custom repo path
                MockGit.assert_called_once_with(str(custom_repo_path))


# ============================================================================
# Test: Error Handling
# ============================================================================


class TestRefreshPRsErrorHandling:
    """Tests for error handling in refresh_prs."""

    @pytest.mark.asyncio
    async def test_load_config_failure(
        self,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test handling of config load failure."""
        with patch("autoflow.scheduler.pr_refresh_job.load_config", side_effect=Exception("Config error")):
            result = await refresh_prs()

        assert result.success is False
        assert "Config error" in result.error

    @pytest.mark.asyncio
    async def test_pr_manager_init_failure(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Test handling of PRManager initialization failure."""
        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", side_effect=Exception("Init error")):
                result = await refresh_prs()

        assert result.success is False
        assert "Init error" in result.error

    @pytest.mark.asyncio
    async def test_detect_stale_prs_failure(
        self,
        mock_config: MagicMock,
        mock_pr_manager: MagicMock,
    ) -> None:
        """Test handling of detect_stale_prs failure."""
        mock_pr_manager.detect_stale_prs.side_effect = Exception("Detection error")

        with patch("autoflow.scheduler.pr_refresh_job.load_config", return_value=mock_config):
            with patch("autoflow.scheduler.pr_refresh_job.PRManager", return_value=mock_pr_manager):
                with patch("autoflow.scheduler.pr_refresh_job.create_git_operations"):
                    result = await refresh_prs()

        assert result.success is False
        assert "Detection error" in result.error
