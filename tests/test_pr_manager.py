"""
Unit Tests for PR Manager

Tests the PRManager class and related models (PRState, PRRefreshStatus)
for PR state tracking and refresh management.

These tests mock GitOperations and use temporary state directories
to avoid affecting real repositories or state files.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.git.pr_manager import (
    PRManager,
    PRRefreshStatus,
    PRState,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def mock_git_ops() -> MagicMock:
    """Create a mock GitOperations instance."""
    git_ops = MagicMock()
    git_ops.get_branch_info = MagicMock()
    return git_ops


@pytest.fixture
def sample_pr_state() -> PRState:
    """Return a sample PRState for testing."""
    return PRState(
        pr_number=123,
        branch="feature-x",
        base_branch="main",
    )


@pytest.fixture
def pr_manager(temp_state_dir: Path, mock_git_ops: MagicMock) -> PRManager:
    """Create a PRManager instance with temporary state and mocked git ops."""
    with patch("autoflow.git.pr_manager.create_git_operations", return_value=mock_git_ops):
        with patch("autoflow.git.pr_manager.StateManager") as mock_state_class:
            # Create a real StateManager with temp directory
            from autoflow.core.state import StateManager

            real_state = StateManager(temp_state_dir)
            real_state.initialize()

            mock_state_class.return_value = real_state

            manager = PRManager(repo_path="/tmp/test_repo", state_dir=temp_state_dir)
            # Replace state with real one for testing
            manager.state = real_state

            return manager


# ============================================================================
# PRRefreshStatus Enum Tests
# ============================================================================


class TestPRRefreshStatus:
    """Tests for PRRefreshStatus enum."""

    def test_pr_refresh_status_values(self) -> None:
        """Test PRRefreshStatus enum values."""
        assert PRRefreshStatus.NOT_TRACKED == "not_tracked"
        assert PRRefreshStatus.UP_TO_DATE == "up_to_date"
        assert PRRefreshStatus.NEEDS_REFRESH == "needs_refresh"
        assert PRRefreshStatus.REFRESHING == "refreshing"
        assert PRRefreshStatus.REFRESHED == "refreshed"
        assert PRRefreshStatus.CONFLICT_DETECTED == "conflict_detected"
        assert PRRefreshStatus.RESOLVING == "resolving"
        assert PRRefreshStatus.RESOLVED == "resolved"
        assert PRRefreshStatus.FAILED == "failed"

    def test_pr_refresh_status_is_string(self) -> None:
        """Test that PRRefreshStatus values are strings."""
        assert isinstance(PRRefreshStatus.NOT_TRACKED.value, str)

    def test_pr_refresh_status_from_string(self) -> None:
        """Test creating PRRefreshStatus from string."""
        status = PRRefreshStatus("refreshing")
        assert status == PRRefreshStatus.REFRESHING


# ============================================================================
# PRState Model Tests
# ============================================================================


class TestPRState:
    """Tests for PRState model."""

    def test_pr_state_init_minimal(self) -> None:
        """Test PRState initialization with minimal fields."""
        pr_state = PRState(
            pr_number=123,
            branch="feature-x",
            base_branch="main",
        )

        assert pr_state.pr_number == 123
        assert pr_state.branch == "feature-x"
        assert pr_state.base_branch == "main"
        assert pr_state.status == PRRefreshStatus.NOT_TRACKED
        assert pr_state.last_refresh_at is None
        assert pr_state.last_refresh_commit is None
        assert pr_state.refresh_count == 0
        assert pr_state.conflict_count == 0
        assert pr_state.needs_refresh is False
        assert pr_state.created_at is not None
        assert pr_state.updated_at is not None

    def test_pr_state_init_full(self) -> None:
        """Test PRState initialization with all fields."""
        now = datetime.utcnow()
        pr_state = PRState(
            pr_number=456,
            branch="feature-y",
            base_branch="develop",
            status=PRRefreshStatus.REFRESHING,
            last_refresh_at=now,
            last_refresh_commit="abc123",
            refresh_count=5,
            conflict_count=2,
            needs_refresh=True,
        )

        assert pr_state.pr_number == 456
        assert pr_state.branch == "feature-y"
        assert pr_state.base_branch == "develop"
        assert pr_state.status == PRRefreshStatus.REFRESHING
        assert pr_state.last_refresh_at == now
        assert pr_state.last_refresh_commit == "abc123"
        assert pr_state.refresh_count == 5
        assert pr_state.conflict_count == 2
        assert pr_state.needs_refresh is True

    def test_pr_state_touch(self) -> None:
        """Test PRState.touch() updates timestamp."""
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")
        original_updated = pr_state.updated_at

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)
        pr_state.touch()

        assert pr_state.updated_at > original_updated

    def test_pr_state_mark_refresh_attempt(self) -> None:
        """Test PRState.mark_refresh_attempt() updates counters."""
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")

        original_count = pr_state.refresh_count
        original_updated = pr_state.updated_at

        time.sleep(0.01)
        pr_state.mark_refresh_attempt()

        assert pr_state.refresh_count == original_count + 1
        assert pr_state.last_refresh_at is not None
        assert pr_state.updated_at > original_updated
        assert pr_state.updated_at > pr_state.last_refresh_at

    def test_pr_state_mark_conflict(self) -> None:
        """Test PRState.mark_conflict() updates conflict counter."""
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")

        original_count = pr_state.conflict_count

        time.sleep(0.01)
        pr_state.mark_conflict()

        assert pr_state.conflict_count == original_count + 1
        assert pr_state.updated_at is not None


# ============================================================================
# PRManager Init Tests
# ============================================================================


class TestPRManagerInit:
    """Tests for PRManager initialization."""

    def test_init_with_path(self, temp_state_dir: Path) -> None:
        """Test PRManager initialization with path."""
        with patch("autoflow.git.pr_manager.create_git_operations") as mock_git:
            manager = PRManager(
                repo_path="/tmp/test_repo",
                state_dir=temp_state_dir,
            )

            assert manager.repo_path == Path("/tmp/test_repo").resolve()
            assert manager.state is not None
            mock_git.assert_called_once()

    def test_init_with_string_path(self, temp_state_dir: Path) -> None:
        """Test PRManager initialization with string path."""
        with patch("autoflow.git.pr_manager.create_git_operations") as mock_git:
            manager = PRManager(
                repo_path="/tmp/test_repo",
                state_dir=str(temp_state_dir),
            )

            assert manager.repo_path == Path("/tmp/test_repo").resolve()


# ============================================================================
# PRManager Track PR Tests
# ============================================================================


class TestPRManagerTrackPR:
    """Tests for PRManager.track_pr() method."""

    def test_track_pr(self, pr_manager: PRManager, sample_pr_state: PRState) -> None:
        """Test tracking a PR."""
        pr_manager.track_pr(sample_pr_state)

        loaded = pr_manager.load_pr_state(123)

        assert loaded is not None
        assert loaded.pr_number == 123
        assert loaded.branch == "feature-x"
        assert loaded.base_branch == "main"

    def test_track_pr_updates_index(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test tracking a PR updates the tracked PRs index."""
        pr_manager.track_pr(sample_pr_state)

        tracked_prs = pr_manager._load_tracked_prs()

        assert 123 in tracked_prs

    def test_track_pr_duplicate(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test tracking the same PR twice doesn't duplicate in index."""
        pr_manager.track_pr(sample_pr_state)
        pr_manager.track_pr(sample_pr_state)

        tracked_prs = pr_manager._load_tracked_prs()

        # Should only appear once
        assert tracked_prs.count(123) == 1

    def test_track_pr_multiple(self, pr_manager: PRManager) -> None:
        """Test tracking multiple PRs."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        pr2 = PRState(pr_number=2, branch="feature-2", base_branch="main")

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        tracked_prs = pr_manager._load_tracked_prs()

        assert len(tracked_prs) == 2
        assert 1 in tracked_prs
        assert 2 in tracked_prs


# ============================================================================
# PRManager Load PR State Tests
# ============================================================================


class TestPRManagerLoadPR:
    """Tests for PRManager.load_pr_state() method."""

    def test_load_pr_existing(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test loading an existing PR."""
        pr_manager.track_pr(sample_pr_state)

        loaded = pr_manager.load_pr_state(123)

        assert loaded is not None
        assert loaded.pr_number == 123
        assert loaded.branch == "feature-x"

    def test_load_pr_nonexistent(self, pr_manager: PRManager) -> None:
        """Test loading a non-existent PR returns None."""
        loaded = pr_manager.load_pr_state(999)

        assert loaded is None

    def test_load_pr_after_update(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test loading PR after state update."""
        pr_manager.track_pr(sample_pr_state)

        # Update the PR
        sample_pr_state.status = PRRefreshStatus.REFRESHED
        pr_manager.track_pr(sample_pr_state)

        loaded = pr_manager.load_pr_state(123)

        assert loaded is not None
        assert loaded.status == PRRefreshStatus.REFRESHED


# ============================================================================
# PRManager List PRs Tests
# ============================================================================


class TestPRManagerListPRs:
    """Tests for PRManager.list_prs() method."""

    def test_list_prs_all(self, pr_manager: PRManager) -> None:
        """Test listing all tracked PRs."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        pr2 = PRState(pr_number=2, branch="feature-2", base_branch="main")

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        prs = pr_manager.list_prs()

        assert len(prs) == 2
        pr_numbers = [pr.pr_number for pr in prs]
        assert 1 in pr_numbers
        assert 2 in pr_numbers

    def test_list_prs_empty(self, pr_manager: PRManager) -> None:
        """Test listing PRs when none tracked."""
        prs = pr_manager.list_prs()

        assert prs == []

    def test_list_prs_filter_by_status(self, pr_manager: PRManager) -> None:
        """Test filtering PRs by status."""
        pr1 = PRState(
            pr_number=1,
            branch="feature-1",
            base_branch="main",
            status=PRRefreshStatus.REFRESHING,
        )
        pr2 = PRState(
            pr_number=2,
            branch="feature-2",
            base_branch="main",
            status=PRRefreshStatus.REFRESHED,
        )

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        refreshing = pr_manager.list_prs(status=PRRefreshStatus.REFRESHING)

        assert len(refreshing) == 1
        assert refreshing[0].pr_number == 1

    def test_list_prs_filter_by_needs_refresh(self, pr_manager: PRManager) -> None:
        """Test filtering PRs by needs_refresh flag."""
        pr1 = PRState(
            pr_number=1,
            branch="feature-1",
            base_branch="main",
            needs_refresh=True,
        )
        pr2 = PRState(
            pr_number=2,
            branch="feature-2",
            base_branch="main",
            needs_refresh=False,
        )

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        stale = pr_manager.list_prs(needs_refresh=True)

        assert len(stale) == 1
        assert stale[0].pr_number == 1

    def test_list_prs_sorted_by_created_at(
        self, pr_manager: PRManager
    ) -> None:
        """Test PRs are sorted by created_at descending."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        time.sleep(0.01)
        pr2 = PRState(pr_number=2, branch="feature-2", base_branch="main")

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        prs = pr_manager.list_prs()

        # Most recent first
        assert prs[0].pr_number == 2
        assert prs[1].pr_number == 1


# ============================================================================
# PRManager Update Refresh State Tests
# ============================================================================


class TestPRManagerUpdateRefreshState:
    """Tests for PRManager.update_pr_refresh_state() method."""

    def test_update_pr_status_to_refreshing(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test updating PR status to REFRESHING."""
        pr_manager.track_pr(sample_pr_state)

        updated = pr_manager.update_pr_refresh_state(
            123, PRRefreshStatus.REFRESHING
        )

        assert updated is not None
        assert updated.status == PRRefreshStatus.REFRESHING
        assert updated.refresh_count == 1
        assert updated.last_refresh_at is not None

    def test_update_pr_status_to_refreshed_with_commit(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test updating PR status to REFRESHED with commit."""
        pr_manager.track_pr(sample_pr_state)

        updated = pr_manager.update_pr_refresh_state(
            123,
            PRRefreshStatus.REFRESHED,
            last_commit="abc123",
        )

        assert updated is not None
        assert updated.status == PRRefreshStatus.REFRESHED
        assert updated.last_refresh_commit == "abc123"
        assert updated.needs_refresh is False

    def test_update_pr_status_to_conflict_detected(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test updating PR status to CONFLICT_DETECTED."""
        pr_manager.track_pr(sample_pr_state)

        updated = pr_manager.update_pr_refresh_state(
            123, PRRefreshStatus.CONFLICT_DETECTED
        )

        assert updated is not None
        assert updated.status == PRRefreshStatus.CONFLICT_DETECTED
        assert updated.conflict_count == 1

    def test_update_pr_status_to_failed(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test updating PR status to FAILED."""
        pr_manager.track_pr(sample_pr_state)

        updated = pr_manager.update_pr_refresh_state(123, PRRefreshStatus.FAILED)

        assert updated is not None
        assert updated.status == PRRefreshStatus.FAILED
        assert updated.needs_refresh is True

    def test_update_pr_nonexistent(self, pr_manager: PRManager) -> None:
        """Test updating non-existent PR returns None."""
        updated = pr_manager.update_pr_refresh_state(
            999, PRRefreshStatus.REFRESHING
        )

        assert updated is None


# ============================================================================
# PRManager Detect Stale PRs Tests
# ============================================================================


class TestPRManagerDetectStale:
    """Tests for PRManager.detect_stale_prs() method."""

    def test_detect_stale_no_refresh_yet(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test detecting stale PR when never refreshed."""
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")
        pr_manager.track_pr(pr_state)

        # Mock branch info
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = "abc123"
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        stale = pr_manager.detect_stale_prs()

        assert len(stale) == 1
        assert stale[0].pr_number == 123
        assert stale[0].needs_refresh is True

    def test_detect_stale_base_branch_advanced(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test detecting stale PR when base branch advanced."""
        pr_state = PRState(
            pr_number=123,
            branch="feature",
            base_branch="main",
            last_refresh_commit="old-commit",
        )
        pr_manager.track_pr(pr_state)

        # Mock branch info with new commit
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = "new-commit"
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        stale = pr_manager.detect_stale_prs()

        assert len(stale) == 1
        assert stale[0].needs_refresh is True

    def test_detect_stale_up_to_date(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test detecting PR is up to date."""
        commit_sha = "abc123"
        pr_state = PRState(
            pr_number=123,
            branch="feature",
            base_branch="main",
            last_refresh_commit=commit_sha,
        )
        pr_manager.track_pr(pr_state)

        # Mock branch info with same commit
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = commit_sha
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        stale = pr_manager.detect_stale_prs()

        assert len(stale) == 0
        # Check that needs_refresh was updated to False
        loaded = pr_manager.load_pr_state(123)
        assert loaded is not None
        assert loaded.needs_refresh is False

    def test_detect_stale_multiple_prs(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test detecting stale PRs among multiple tracked."""
        pr1 = PRState(pr_number=1, branch="feature-1", base_branch="main")
        pr2 = PRState(
            pr_number=2,
            branch="feature-2",
            base_branch="main",
            last_refresh_commit="abc123",
        )
        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        # Mock branch info
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = "new-commit"
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        stale = pr_manager.detect_stale_prs()

        # PR1 never refreshed, PR2 has old commit - both stale
        assert len(stale) == 2

    def test_detect_stale_handles_missing_branch_info(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test detecting stale PR handles missing branch info gracefully."""
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")
        pr_manager.track_pr(pr_state)

        # Mock branch info returns None
        mock_git_ops.get_branch_info.return_value = None

        stale = pr_manager.detect_stale_prs()

        # Should skip PR with missing branch info
        assert len(stale) == 0


# ============================================================================
# PRManager Get Status Tests
# ============================================================================


class TestPRManagerGetStatus:
    """Tests for PRManager.get_status() method."""

    def test_get_status_empty(self, pr_manager: PRManager) -> None:
        """Test getting status when no PRs tracked."""
        status = pr_manager.get_status()

        assert "repo_path" in status
        assert status["total_prs"] == 0
        assert status["needs_refresh"] == 0
        assert status["total_conflicts"] == 0
        assert status["by_status"] == {}

    def test_get_status_with_prs(self, pr_manager: PRManager) -> None:
        """Test getting status with tracked PRs."""
        pr1 = PRState(
            pr_number=1,
            branch="feature-1",
            base_branch="main",
            status=PRRefreshStatus.REFRESHING,
            needs_refresh=True,
            conflict_count=2,
        )
        pr2 = PRState(
            pr_number=2,
            branch="feature-2",
            base_branch="main",
            status=PRRefreshStatus.REFRESHED,
            conflict_count=1,
        )

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        status = pr_manager.get_status()

        assert status["total_prs"] == 2
        assert status["needs_refresh"] == 1
        assert status["total_conflicts"] == 3
        assert status["by_status"]["refreshing"] == 1
        assert status["by_status"]["refreshed"] == 1

    def test_get_status_includes_repo_path(self, pr_manager: PRManager) -> None:
        """Test status includes repo path."""
        status = pr_manager.get_status()

        assert "repo_path" in status
        assert "test_repo" in status["repo_path"]


# ============================================================================
# Integration Tests
# ============================================================================


class TestPRManagerIntegration:
    """Integration tests for PR manager workflows."""

    def test_full_pr_lifecycle(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test complete PR lifecycle from tracking to refresh."""
        # Track PR
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")
        pr_manager.track_pr(pr_state)

        # Detect it needs refresh
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = "abc123"
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        stale = pr_manager.detect_stale_prs()
        assert len(stale) == 1

        # Mark as refreshing
        pr_manager.update_pr_refresh_state(123, PRRefreshStatus.REFRESHING)

        # Mark as refreshed
        pr_manager.update_pr_refresh_state(
            123,
            PRRefreshStatus.REFRESHED,
            last_commit="abc123",
        )

        # Verify final state
        final = pr_manager.load_pr_state(123)
        assert final is not None
        assert final.status == PRRefreshStatus.REFRESHED
        assert final.needs_refresh is False

    def test_conflict_detection_workflow(
        self, pr_manager: PRManager, mock_git_ops: MagicMock
    ) -> None:
        """Test workflow for detecting and handling conflicts."""
        # Track PR
        pr_state = PRState(pr_number=123, branch="feature", base_branch="main")
        pr_manager.track_pr(pr_state)

        # Detect stale
        mock_branch_info = MagicMock()
        mock_branch_info.commit_sha = "abc123"
        mock_git_ops.get_branch_info.return_value = mock_branch_info

        pr_manager.detect_stale_prs()

        # Start refresh
        pr_manager.update_pr_refresh_state(123, PRRefreshStatus.REFRESHING)

        # Detect conflict
        pr_manager.update_pr_refresh_state(
            123, PRRefreshStatus.CONFLICT_DETECTED
        )

        # Verify conflict recorded
        final = pr_manager.load_pr_state(123)
        assert final is not None
        assert final.status == PRRefreshStatus.CONFLICT_DETECTED
        assert final.conflict_count == 1


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestPRManagerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_pr_state_with_special_branch_name(self, pr_manager: PRManager) -> None:
        """Test PR state with special characters in branch name."""
        pr_state = PRState(
            pr_number=123,
            branch="feature/with-slashes",
            base_branch="main",
        )
        pr_manager.track_pr(pr_state)

        loaded = pr_manager.load_pr_state(123)
        assert loaded is not None
        assert loaded.branch == "feature/with-slashes"

    def test_multiple_refresh_attempts(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test multiple refresh attempts increment counter."""
        pr_manager.track_pr(sample_pr_state)

        # First refresh cycle (REFRESHING + REFRESHED both increment count)
        pr_manager.update_pr_refresh_state(123, PRRefreshStatus.REFRESHING)
        pr_manager.update_pr_refresh_state(
            123,
            PRRefreshStatus.REFRESHED,
            last_commit="commit1",
        )

        loaded = pr_manager.load_pr_state(123)
        assert loaded is not None
        first_count = loaded.refresh_count
        assert first_count == 2  # Incremented twice (REFRESHING + REFRESHED)

        # Second refresh cycle
        pr_manager.update_pr_refresh_state(123, PRRefreshStatus.REFRESHING)
        pr_manager.update_pr_refresh_state(
            123,
            PRRefreshStatus.REFRESHED,
            last_commit="commit2",
        )

        loaded = pr_manager.load_pr_state(123)
        assert loaded is not None
        assert loaded.refresh_count == 4  # Two more increments

    def test_conflict_count_increments(
        self, pr_manager: PRManager, sample_pr_state: PRState
    ) -> None:
        """Test conflict count increments with each conflict."""
        pr_manager.track_pr(sample_pr_state)

        # First conflict
        pr_manager.update_pr_refresh_state(
            123, PRRefreshStatus.CONFLICT_DETECTED
        )

        # Second conflict
        pr_manager.update_pr_refresh_state(
            123, PRRefreshStatus.CONFLICT_DETECTED
        )

        loaded = pr_manager.load_pr_state(123)
        assert loaded is not None
        assert loaded.conflict_count == 2

    def test_list_prs_combined_filters(self, pr_manager: PRManager) -> None:
        """Test listing PRs with multiple filters."""
        pr1 = PRState(
            pr_number=1,
            branch="feature-1",
            base_branch="main",
            status=PRRefreshStatus.REFRESHING,
            needs_refresh=True,
        )
        pr2 = PRState(
            pr_number=2,
            branch="feature-2",
            base_branch="main",
            status=PRRefreshStatus.REFRESHING,
            needs_refresh=False,
        )

        pr_manager.track_pr(pr1)
        pr_manager.track_pr(pr2)

        # Filter by both status and needs_refresh
        result = pr_manager.list_prs(
            status=PRRefreshStatus.REFRESHING,
            needs_refresh=True,
        )

        assert len(result) == 1
        assert result[0].pr_number == 1
