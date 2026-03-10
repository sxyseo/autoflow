"""
PR Manager - PR state tracking and refresh management

This module provides PRManager class for tracking PR state, detecting stale PRs,
and managing refresh operations. Integrates with GitOperations for git operations
and StateManager for persistent state storage.

Usage:
    from autoflow.git.pr_manager import PRManager, PRState, PRRefreshStatus

    pr_manager = PRManager(repo_path="/path/to/repo")
    pr_state = PRState(pr_number=123, branch="feature-x", base_branch="main")
    pr_manager.track_pr(pr_state)
    stale_prs = pr_manager.detect_stale_prs()
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.core.state import StateManager
from autoflow.git.operations import GitOperations, create_git_operations

logger = logging.getLogger(__name__)


class PRRefreshStatus(str, Enum):
    """
    Status of PR refresh operation.

    Tracks the lifecycle of a PR refresh attempt from detection
    through completion or failure.
    """

    NOT_TRACKED = "not_tracked"
    UP_TO_DATE = "up_to_date"
    NEEDS_REFRESH = "needs_refresh"
    REFRESHING = "refreshing"
    REFRESHED = "refreshed"
    CONFLICT_DETECTED = "conflict_detected"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    FAILED = "failed"


class PRState(BaseModel):
    """
    Represents the state of a pull request in the refresh system.

    Tracks PR metadata, refresh status, and conflict history to enable
    automatic PR refresh operations and conflict resolution.

    Attributes:
        pr_number: Pull request number
        branch: Feature branch name
        base_branch: Base branch (e.g., "main", "develop")
        status: Current refresh status
        last_refresh_at: Timestamp of last refresh attempt
        last_refresh_commit: Commit SHA after last refresh
        refresh_count: Number of refresh attempts performed
        conflict_count: Number of conflicts encountered
        needs_refresh: Whether PR needs refresh (base branch changed)
        created_at: When PR was first tracked
        updated_at: When PR state was last updated

    Example:
        >>> pr_state = PRState(
        ...     pr_number=123,
        ...     branch="feature-x",
        ...     base_branch="main"
        ... )
        >>> pr_state.touch()  # Update timestamp
    """

    pr_number: int
    branch: str
    base_branch: str
    status: PRRefreshStatus = PRRefreshStatus.NOT_TRACKED
    last_refresh_at: Optional[datetime] = None
    last_refresh_commit: Optional[str] = None
    refresh_count: int = 0
    conflict_count: int = 0
    needs_refresh: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        """Update the updated_at timestamp to current time."""
        self.updated_at = datetime.utcnow()

    def mark_refresh_attempt(self) -> None:
        """Mark that a refresh attempt was made."""
        self.refresh_count += 1
        self.last_refresh_at = datetime.utcnow()
        self.touch()

    def mark_conflict(self) -> None:
        """Mark that a conflict was detected during refresh."""
        self.conflict_count += 1
        self.status = PRRefreshStatus.CONFLICT_DETECTED
        self.touch()

    def mark_up_to_date(self) -> None:
        """Mark PR as up to date (no refresh needed)."""
        self.status = PRRefreshStatus.UP_TO_DATE
        self.needs_refresh = False
        self.touch()

    def mark_needs_refresh(self) -> None:
        """Mark PR as needing refresh."""
        self.status = PRRefreshStatus.NEEDS_REFRESH
        self.needs_refresh = True
        self.touch()

    def mark_refreshing(self) -> None:
        """Mark PR as currently being refreshed."""
        self.status = PRRefreshStatus.REFRESHING
        self.touch()

    def mark_refreshed(self, commit_sha: Optional[str] = None) -> None:
        """Mark PR as successfully refreshed."""
        self.status = PRRefreshStatus.REFRESHED
        self.needs_refresh = False
        self.refresh_count += 1
        self.last_refresh_at = datetime.utcnow()
        if commit_sha:
            self.last_refresh_commit = commit_sha
        self.touch()

    def mark_resolving(self) -> None:
        """Mark PR as having conflicts being resolved."""
        self.status = PRRefreshStatus.RESOLVING
        self.touch()

    def mark_resolved(self) -> None:
        """Mark PR conflicts as resolved."""
        self.status = PRRefreshStatus.RESOLVED
        self.touch()

    def mark_failed(self, error_message: Optional[str] = None) -> None:
        """Mark PR refresh as failed."""
        self.status = PRRefreshStatus.FAILED
        self.needs_refresh = True
        self.touch()


class PRManager:
    """
    Manages PR state tracking and refresh operations.

    Provides functionality to:
    - Track PR state persistently
    - Detect when PRs need refresh (base branch changed)
    - Update PR refresh status during operations
    - Query PRs by refresh status

    Integrates with GitOperations for git operations and StateManager
    for persistent storage.

    Attributes:
        repo_path: Path to the git repository
        git_ops: GitOperations instance for git commands
        state: StateManager instance for persistent storage
        refresh_frequency: Refresh check frequency in seconds

    Example:
        >>> pr_manager = PRManager(repo_path="/path/to/repo")
        >>> pr_state = PRState(pr_number=123, branch="feature-x", base_branch="main")
        >>> pr_manager.track_pr(pr_state)
        >>> stale_prs = pr_manager.detect_stale_prs()
        >>> print(f"Found {len(stale_prs)} PRs needing refresh")
    """

    # State storage keys
    PRS_MEMORY_KEY = "tracked_prs"
    PR_STATE_PREFIX = "pr_state"

    def __init__(
        self,
        repo_path: str | Path,
        state_dir: Optional[str | Path] = None,
        refresh_frequency: Optional[int] = None,
    ):
        """
        Initialize PRManager.

        Args:
            repo_path: Path to the git repository
            state_dir: Optional state directory path (defaults to .autoflow)
            refresh_frequency: Optional refresh check frequency in seconds.
                If None, uses default of 300 seconds (5 minutes).

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager = PRManager(
            ...     repo_path="/path/to/repo",
            ...     state_dir=".autoflow",
            ...     refresh_frequency=600
            ... )
        """
        self.repo_path = Path(repo_path).resolve()
        self.git_ops = create_git_operations(str(self.repo_path))
        self.state = StateManager(state_dir or ".autoflow")
        self.state.initialize()
        self.refresh_frequency = refresh_frequency if refresh_frequency is not None else 300

    def track_pr(self, pr_state: PRState) -> None:
        """
        Track a PR state.

        Stores PR state in persistent storage for tracking and monitoring.

        Args:
            pr_state: PR state to track

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_state = PRState(pr_number=123, branch="feature-x", base_branch="main")
            >>> pr_manager.track_pr(pr_state)
        """
        try:
            # Save PR state to memory
            pr_key = f"{self.PR_STATE_PREFIX}_{pr_state.pr_number}"
            self.state.save_memory(
                key=pr_key,
                value=pr_state.model_dump(mode="json"),
                category="pr_state",
            )

            # Update tracked PRs index
            tracked_prs = self._load_tracked_prs()
            if pr_state.pr_number not in tracked_prs:
                tracked_prs.append(pr_state.pr_number)
                self.state.save_memory(
                    key=self.PRS_MEMORY_KEY,
                    value=tracked_prs,
                    category="pr_index",
                )

            logger.info(
                "Tracking PR #%d: %s -> %s",
                pr_state.pr_number,
                pr_state.branch,
                pr_state.base_branch,
            )

        except Exception as e:
            logger.error("Failed to track PR #%d: %s", pr_state.pr_number, e)
            raise

    def load_pr_state(self, pr_number: int) -> Optional[PRState]:
        """
        Load PR state from storage.

        Args:
            pr_number: PR number to load

        Returns:
            PR state or None if not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_state = pr_manager.load_pr_state(123)
            >>> if pr_state:
            ...     print(f"PR status: {pr_state.status}")
        """
        try:
            pr_key = f"{self.PR_STATE_PREFIX}_{pr_number}"
            data = self.state.load_memory(pr_key)
            if data:
                return PRState(**data)
            return None
        except Exception as e:
            logger.error("Failed to load PR #%d: %s", pr_number, e)
            return None

    def list_prs(
        self,
        status: Optional[PRRefreshStatus] = None,
        needs_refresh: Optional[bool] = None,
    ) -> list[PRState]:
        """
        List tracked PRs, optionally filtered.

        Args:
            status: Filter by refresh status
            needs_refresh: Filter by needs_refresh flag

        Returns:
            List of PR states matching filters

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> # Get all PRs needing refresh
            >>> stale = pr_manager.list_prs(needs_refresh=True)
            >>> # Get all PRs with conflicts
            >>> conflicts = pr_manager.list_prs(status=PRRefreshStatus.CONFLICT_DETECTED)
        """
        try:
            tracked_prs = self._load_tracked_prs()
            result = []

            for pr_number in tracked_prs:
                pr_state = self.load_pr_state(pr_number)
                if pr_state:
                    # Apply filters
                    if status and pr_state.status != status:
                        continue
                    if needs_refresh is not None and pr_state.needs_refresh != needs_refresh:
                        continue
                    result.append(pr_state)

            # Sort by created_at descending
            result.sort(key=lambda p: p.created_at, reverse=True)
            return result

        except Exception as e:
            logger.error("Failed to list PRs: %s", e)
            return []

    def update_pr_refresh_state(
        self,
        pr_number: int,
        status: PRRefreshStatus,
        last_commit: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[PRState]:
        """
        Update PR refresh state.

        Updates the refresh status and related metadata for a tracked PR.
        Saves to persistent storage and returns updated state.

        Args:
            pr_number: PR number to update
            status: New refresh status
            last_commit: Optional commit SHA after refresh
            error: Optional error message if status is FAILED

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> # Mark PR as refreshing
            >>> pr_manager.update_pr_refresh_state(123, PRRefreshStatus.REFRESHING)
            >>> # Mark PR as refreshed
            >>> pr_manager.update_pr_refresh_state(
            ...     123,
            ...     PRRefreshStatus.REFRESHED,
            ...     last_commit="abc123"
            ... )
        """
        try:
            pr_state = self.load_pr_state(pr_number)
            if not pr_state:
                logger.warning("PR #%d not found for state update", pr_number)
                return None

            # Update status
            old_status = pr_state.status
            pr_state.status = status

            # Update commit if provided
            if last_commit:
                pr_state.last_refresh_commit = last_commit

            # Update timestamps and counters based on status
            if status == PRRefreshStatus.REFRESHING:
                pr_state.mark_refresh_attempt()
            elif status == PRRefreshStatus.CONFLICT_DETECTED:
                pr_state.mark_conflict()
            elif status == PRRefreshStatus.REFRESHED:
                pr_state.needs_refresh = False
                pr_state.mark_refresh_attempt()
            elif status == PRRefreshStatus.FAILED:
                pr_state.needs_refresh = True
                pr_state.touch()

            # Save updated state
            self.track_pr(pr_state)

            logger.info(
                "Updated PR #%d status: %s -> %s",
                pr_number,
                old_status.value,
                status.value,
            )

            return pr_state

        except Exception as e:
            logger.error("Failed to update PR #%d state: %s", pr_number, e)
            return None

    def _load_tracked_prs(self) -> list[int]:
        """
        Load list of tracked PR numbers.

        Returns:
            List of tracked PR numbers
        """
        try:
            data = self.state.load_memory(self.PRS_MEMORY_KEY)
            if data:
                return data
            return []
        except Exception:
            return []

    def detect_stale_prs(self) -> list[PRState]:
        """
        Detect PRs that need refresh due to base branch changes.

        Checks each tracked PR to determine if the base branch has advanced
        since the last refresh. Updates the needs_refresh flag and returns
        the list of PRs that need refresh.

        Returns:
            List of PR states that need refresh

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> stale_prs = pr_manager.detect_stale_prs()
            >>> for pr in stale_prs:
            ...     print(f"PR #{pr.pr_number} needs refresh")
        """
        try:
            all_prs = self.list_prs()
            stale_prs: list[PRState] = []

            for pr_state in all_prs:
                try:
                    # Get current HEAD commit of base branch
                    base_info = self.git_ops.get_branch_info(pr_state.base_branch)
                    if not base_info or not base_info.commit_sha:
                        logger.warning(
                            "Could not get HEAD for base branch %s of PR #%d",
                            pr_state.base_branch,
                            pr_state.pr_number,
                        )
                        continue

                    base_head = base_info.commit_sha

                    # Check if base branch has advanced since last refresh
                    needs_update = False
                    if pr_state.last_refresh_commit is None:
                        # Never refreshed, needs refresh
                        needs_update = True
                    elif base_head != pr_state.last_refresh_commit:
                        # Base branch has moved forward
                        needs_update = True

                    # Update state if needed
                    if needs_update != pr_state.needs_refresh:
                        pr_state.needs_refresh = needs_update
                        self.track_pr(pr_state)

                    # Track as stale if needs refresh
                    if needs_update:
                        stale_prs.append(pr_state)
                        logger.debug(
                            "PR #%d needs refresh (base %s advanced from %s to %s)",
                            pr_state.pr_number,
                            pr_state.base_branch,
                            pr_state.last_refresh_commit,
                            base_head,
                        )

                except Exception as e:
                    logger.error(
                        "Failed to check staleness for PR #%d: %s",
                        pr_state.pr_number,
                        e,
                    )
                    continue

            logger.info(
                "Detected %d stale PRs out of %d tracked",
                len(stale_prs),
                len(all_prs),
            )

            return stale_prs

        except Exception as e:
            logger.error("Failed to detect stale PRs: %s", e)
            return []

    # === Real-time PR Status Update Methods ===

    def mark_up_to_date(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR as up to date (no refresh needed).

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_up_to_date(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_up_to_date()
        self.track_pr(pr_state)

        logger.info("Marked PR #%d as up to date", pr_number)
        return pr_state

    def mark_needs_refresh(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR as needing refresh.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_needs_refresh(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_needs_refresh()
        self.track_pr(pr_state)

        logger.info("Marked PR #%d as needing refresh", pr_number)
        return pr_state

    def mark_refreshing(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR as currently being refreshed.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_refreshing(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_refreshing()
        self.track_pr(pr_state)

        logger.info("Marked PR #%d as refreshing", pr_number)
        return pr_state

    def mark_refreshed(
        self, pr_number: int, commit_sha: Optional[str] = None
    ) -> Optional[PRState]:
        """
        Mark PR as successfully refreshed.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update
            commit_sha: Optional commit SHA after refresh

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_refreshed(123, commit_sha="abc123")
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_refreshed(commit_sha)
        self.track_pr(pr_state)

        logger.info(
            "Marked PR #%d as refreshed (commit: %s)",
            pr_number,
            commit_sha or "unknown",
        )
        return pr_state

    def mark_conflict_detected(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR as having conflict detected during refresh.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_conflict_detected(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_conflict()
        self.track_pr(pr_state)

        logger.warning("Marked PR #%d as having conflicts", pr_number)
        return pr_state

    def mark_resolving(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR as having conflicts being resolved.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_resolving(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_resolving()
        self.track_pr(pr_state)

        logger.info("Marked PR #%d as resolving conflicts", pr_number)
        return pr_state

    def mark_resolved(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR conflicts as resolved.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_resolved(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_resolved()
        self.track_pr(pr_state)

        logger.info("Marked PR #%d conflicts as resolved", pr_number)
        return pr_state

    def mark_failed(self, pr_number: int) -> Optional[PRState]:
        """
        Mark PR refresh as failed.

        Real-time status update with immediate persistence.

        Args:
            pr_number: PR number to update

        Returns:
            Updated PR state or None if PR not found

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> pr_manager.mark_failed(123)
        """
        pr_state = self.load_pr_state(pr_number)
        if not pr_state:
            logger.warning("PR #%d not found for status update", pr_number)
            return None

        pr_state.mark_failed()
        self.track_pr(pr_state)

        logger.error("Marked PR #%d refresh as failed", pr_number)
        return pr_state

    def get_status(self) -> dict[str, Any]:
        """
        Get status summary of tracked PRs.

        Returns:
            Dictionary with PR tracking status and metrics

        Example:
            >>> pr_manager = PRManager(repo_path="/path/to/repo")
            >>> status = pr_manager.get_status()
            >>> print(f"Tracking {status['total_prs']} PRs")
        """
        try:
            all_prs = self.list_prs()

            # Count by status
            status_counts: dict[str, int] = {}
            for pr in all_prs:
                status = pr.status.value
                status_counts[status] = status_counts.get(status, 0) + 1

            # Count needs refresh
            needs_refresh_count = sum(1 for pr in all_prs if pr.needs_refresh)

            # Count total conflicts
            total_conflicts = sum(pr.conflict_count for pr in all_prs)

            return {
                "repo_path": str(self.repo_path),
                "total_prs": len(all_prs),
                "needs_refresh": needs_refresh_count,
                "total_conflicts": total_conflicts,
                "by_status": status_counts,
            }

        except Exception as e:
            logger.error("Failed to get PR manager status: %s", e)
            return {
                "repo_path": str(self.repo_path),
                "error": str(e),
            }
