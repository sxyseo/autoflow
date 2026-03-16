"""
Autoflow Intake Sync Module

Provides bidirectional synchronization between Autoflow tasks and external issues.
Tracks task state changes and pushes updates back to GitHub, GitLab, Linear, etc.

Usage:
    from autoflow.intake.sync import SyncManager, SyncManagerConfig

    config = SyncManagerConfig()
    sync = SyncManager(config=config)

    # Track a task-issue mapping
    sync.track_mapping("task-001", "github", "GH-123")

    # Sync a single task
    result = await sync.sync_task("task-001")

    # Sync all pending tasks
    results = await sync.sync_all()
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.core.config import Config, load_config
from autoflow.core.state import Spec, StateManager, Task, TaskStatus
from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueSourceType,
    IssueStatus,
)
from autoflow.intake.github_client import GitHubClient
from autoflow.intake.gitlab_client import GitLabClient
from autoflow.intake.linear_client import LinearClient
from autoflow.intake.models import Issue, IssueSource, SourceType


class SyncStatus(str, Enum):
    """Status of a sync operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncDirection(str, Enum):
    """Direction of synchronization."""

    PUSH = "push"  # Autoflow -> External source
    PULL = "pull"  # External source -> Autoflow
    BIDIRECTIONAL = "bidirectional"


class SyncError(Exception):
    """Exception raised for sync errors."""

    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        source_id: Optional[str] = None,
    ):
        self.task_id = task_id
        self.source_id = source_id
        super().__init__(message)


@dataclass
class TaskIssueMapping:
    """
    Mapping between an Autoflow task and an external issue.

    Attributes:
        task_id: Autoflow task identifier
        source_type: Type of external source
        issue_id: External issue identifier
        source_url: URL to the external issue
        last_sync_at: Timestamp of last successful sync
        last_sync_status: Status of last sync attempt
        sync_count: Number of successful syncs
        created_at: When this mapping was created
        metadata: Additional mapping metadata
    """

    task_id: str
    source_type: SourceType
    issue_id: str
    source_url: str = ""
    last_sync_at: Optional[datetime] = None
    last_sync_status: SyncStatus = SyncStatus.PENDING
    sync_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_synced(self, status: SyncStatus) -> None:
        """Mark the mapping as synced."""
        self.last_sync_at = datetime.utcnow()
        self.last_sync_status = status
        if status == SyncStatus.SUCCESS:
            self.sync_count += 1

    def to_dict(self) -> dict[str, Any]:
        """Convert mapping to dictionary for storage."""
        return {
            "task_id": self.task_id,
            "source_type": self.source_type.value,
            "issue_id": self.issue_id,
            "source_url": self.source_url,
            "last_sync_at": self.last_sync_at.isoformat()
            if self.last_sync_at
            else None,
            "last_sync_status": self.last_sync_status.value,
            "sync_count": self.sync_count,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskIssueMapping:
        """Create mapping from dictionary."""
        return cls(
            task_id=data["task_id"],
            source_type=SourceType(data["source_type"]),
            issue_id=data["issue_id"],
            source_url=data.get("source_url", ""),
            last_sync_at=(
                datetime.fromisoformat(data["last_sync_at"])
                if data.get("last_sync_at")
                else None
            ),
            last_sync_status=SyncStatus(
                data.get("last_sync_status", SyncStatus.PENDING)
            ),
            sync_count=data.get("sync_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SyncResult:
    """
    Result from a sync operation.

    Attributes:
        sync_id: Unique identifier for this sync operation
        task_id: Task that was synced
        issue_id: External issue ID
        direction: Direction of sync
        success: Whether sync completed successfully
        status: Final sync status
        updates_pushed: Number of updates pushed to external source
        updates_pulled: Number of updates pulled from external source
        comments_added: Number of comments added
        errors: List of error messages
        started_at: When sync started
        completed_at: When sync completed
        duration_seconds: Total sync duration
        metadata: Additional metadata
    """

    sync_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    issue_id: str = ""
    direction: SyncDirection = SyncDirection.PUSH
    success: bool = False
    status: SyncStatus = SyncStatus.PENDING
    updates_pushed: int = 0
    updates_pulled: int = 0
    comments_added: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        status: SyncStatus,
        error: Optional[str] = None,
    ) -> None:
        """Mark the sync as complete."""
        self.success = success
        self.status = status
        if error:
            self.errors.append(error)
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


class SyncStats(BaseModel):
    """Statistics about sync operations."""

    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    skipped_syncs: int = 0
    total_updates_pushed: int = 0
    total_updates_pulled: int = 0
    total_comments_added: int = 0
    average_duration: float = 0.0
    last_sync_at: Optional[datetime] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)


class SyncManagerConfig(BaseModel):
    """
    Configuration for the sync manager.

    Attributes:
        state_dir: Directory for storing state
        direction: Default sync direction
        auto_sync: Whether to automatically sync on task changes
        sync_comments: Whether to sync comments back to issues
        sync_status: Whether to sync status changes
        sync_labels: Whether to sync label changes
        dry_run: If True, don't actually push updates
        batch_size: Number of tasks to sync per batch
        max_concurrent_syncs: Maximum number of concurrent sync operations
        retry_attempts: Number of retry attempts for failed syncs
        retry_delay_seconds: Delay between retry attempts
        metadata: Additional configuration metadata
    """

    state_dir: Path = Field(default_factory=lambda: Path(".auto-claude/state"))
    direction: SyncDirection = SyncDirection.PUSH
    auto_sync: bool = False
    sync_comments: bool = True
    sync_status: bool = True
    sync_labels: bool = True
    dry_run: bool = False
    batch_size: int = 10
    max_concurrent_syncs: int = 5
    retry_attempts: int = 3
    retry_delay_seconds: float = 2.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SyncManager:
    """
    Manages bidirectional synchronization between Autoflow and external issues.

    The sync manager tracks mappings between Autoflow tasks and external issues,
    monitors task state changes, and pushes updates back to the source systems.

    Features:
    - Task-to-issue mapping tracking
    - Status synchronization
    - Comment syncing
    - Batch synchronization
    - Error handling and retry logic
    - Statistics and history tracking

    Example:
        >>> config = SyncManagerConfig()
        >>> sync = SyncManager(config=config)
        >>> await sync.initialize()
        >>>
        >>> # Track a new mapping
        >>> sync.track_mapping("task-001", SourceType.GITHUB, "123")
        >>>
        >>> # Sync a single task
        >>> result = await sync.sync_task("task-001")
        >>>
        >>> # Sync all pending tasks
        >>> results = await sync.sync_all()

    Attributes:
        config: Sync manager configuration
        state: StateManager instance
        clients: Mapping of source types to client instances
        stats: Sync statistics
    """

    MAPPINGS_FILE = "sync_mappings.json"
    HISTORY_DIR = "sync_history"

    DEFAULT_TIMEOUT = 60  # 1 minute per sync

    def __init__(
        self,
        config: Optional[SyncManagerConfig] = None,
        state: Optional[StateManager] = None,
        auto_initialize: bool = False,
    ) -> None:
        """
        Initialize the sync manager.

        Args:
            config: Optional sync manager configuration
            state: Optional state manager
            auto_initialize: If True, initialize on creation
        """
        self._config = config or SyncManagerConfig()
        self._state = state

        # Mappings storage
        self._mappings: dict[str, TaskIssueMapping] = {}  # task_id -> mapping

        # Components
        self._clients: dict[SourceType, IssueClient] = {}

        # Statistics
        self._stats = SyncStats()

        # Background task tracking
        self._running = False

        if auto_initialize:
            asyncio.create_task(self.initialize())

    @property
    def config(self) -> SyncManagerConfig:
        """Get sync manager configuration."""
        return self._config

    @property
    def state(self) -> StateManager:
        """Get state manager, creating if needed."""
        if self._state is None:
            self._state = StateManager(self._config.state_dir)
            self._state.initialize()
        return self._state

    @property
    def stats(self) -> SyncStats:
        """Get sync statistics."""
        return self._stats

    @property
    def mappings(self) -> dict[str, TaskIssueMapping]:
        """Get all task-issue mappings."""
        return self._mappings.copy()

    def initialize(self) -> None:
        """
        Initialize the sync manager.

        Sets up client instances and loads mappings from state.
        """
        try:
            # Initialize clients for each source type
            self._clients = {
                SourceType.GITHUB: GitHubClient(),
                SourceType.GITLAB: GitLabClient(),
                SourceType.LINEAR: LinearClient(),
            }

            # Load mappings from state
            self._load_mappings()

        except Exception as e:
            raise SyncError(
                f"Failed to initialize sync manager: {e}",
            ) from e

    def track_mapping(
        self,
        task_id: str,
        source_type: SourceType,
        issue_id: str,
        source_url: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> TaskIssueMapping:
        """
        Track a mapping between a task and an external issue.

        Args:
            task_id: Autoflow task identifier
            source_type: Type of external source
            issue_id: External issue identifier
            source_url: URL to the external issue
            metadata: Additional metadata

        Returns:
            The created TaskIssueMapping

        Example:
            >>> mapping = sync.track_mapping(
            ...     task_id="task-001",
            ...     source_type=SourceType.GITHUB,
            ...     issue_id="123",
            ...     source_url="https://github.com/owner/repo/issues/123"
            ... )
        """
        mapping = TaskIssueMapping(
            task_id=task_id,
            source_type=source_type,
            issue_id=issue_id,
            source_url=source_url,
            metadata=metadata or {},
        )

        self._mappings[task_id] = mapping
        self._save_mappings()
        return mapping

    def untrack_mapping(self, task_id: str) -> bool:
        """
        Remove a task-issue mapping.

        Args:
            task_id: Task identifier

        Returns:
            True if mapping was removed, False if not found
        """
        if task_id in self._mappings:
            del self._mappings[task_id]
            self._save_mappings()
            return True
        return False

    def get_mapping(self, task_id: str) -> Optional[TaskIssueMapping]:
        """
        Get the mapping for a task.

        Args:
            task_id: Task identifier

        Returns:
            TaskIssueMapping or None if not found
        """
        return self._mappings.get(task_id)

    async def sync_task(
        self,
        task_id: str,
        direction: Optional[SyncDirection] = None,
    ) -> SyncResult:
        """
        Sync a single task with its external issue.

        Args:
            task_id: Task identifier
            direction: Sync direction (defaults to config direction)

        Returns:
            SyncResult with sync statistics

        Example:
            >>> result = await sync.sync_task("task-001")
            >>> if result.success:
            ...     print(f"Synced {result.updates_pushed} updates")
        """
        direction = direction or self._config.direction
        result = SyncResult(
            task_id=task_id,
            direction=direction,
        )

        # Get mapping
        mapping = self._mappings.get(task_id)
        if not mapping:
            result.mark_complete(
                success=False,
                status=SyncStatus.FAILED,
                error=f"No mapping found for task: {task_id}",
            )
            return result

        result.issue_id = mapping.issue_id

        try:
            # Get task from state
            task_dict = self.state.load_task(task_id)
            if not task_dict:
                result.mark_complete(
                    success=False,
                    status=SyncStatus.FAILED,
                    error=f"Task not found: {task_id}",
                )
                return result

            task = Task(**task_dict)

            # Get client for this source type
            client = self._clients.get(mapping.source_type)
            if not client:
                result.mark_complete(
                    success=False,
                    status=SyncStatus.FAILED,
                    error=f"No client available for source type: {mapping.source_type.value}",
                )
                return result

            # Build client config from source
            # First, we need to find the source configuration
            # For now, we'll use a minimal config
            client_config = IssueClientConfig(
                source_type=IssueSourceType(mapping.source_type.value),
                metadata=mapping.metadata,
            )

            # Perform sync based on direction
            if direction in (SyncDirection.PUSH, SyncDirection.BIDIRECTIONAL):
                await self._push_updates(
                    task=task,
                    mapping=mapping,
                    client=client,
                    client_config=client_config,
                    result=result,
                )

            if direction in (SyncDirection.PULL, SyncDirection.BIDIRECTIONAL):
                await self._pull_updates(
                    task=task,
                    mapping=mapping,
                    client=client,
                    client_config=client_config,
                    result=result,
                )

            # Update mapping
            mapping.mark_synced(SyncStatus.SUCCESS)
            self._save_mappings()

            result.mark_complete(success=True, status=SyncStatus.SUCCESS)

            # Update stats
            self._stats.total_syncs += 1
            self._stats.successful_syncs += 1
            self._stats.total_updates_pushed += result.updates_pushed
            self._stats.total_updates_pulled += result.updates_pulled
            self._stats.total_comments_added += result.comments_added
            self._stats.last_sync_at = datetime.utcnow()

        except Exception as e:
            error_msg = f"Sync failed: {e}"
            result.mark_complete(
                success=False,
                status=SyncStatus.FAILED,
                error=error_msg,
            )

            # Update mapping
            if mapping:
                mapping.mark_synced(SyncStatus.FAILED)
                self._save_mappings()

            # Update stats
            self._stats.total_syncs += 1
            self._stats.failed_syncs += 1

        return result

    async def sync_all(
        self,
        direction: Optional[SyncDirection] = None,
        task_ids: Optional[list[str]] = None,
    ) -> list[SyncResult]:
        """
        Sync multiple tasks with their external issues.

        Args:
            direction: Sync direction (defaults to config direction)
            task_ids: Optional list of task IDs to sync (all if None)

        Returns:
            List of SyncResult objects

        Example:
            >>> results = await sync.sync_all(
            ...     direction=SyncDirection.PUSH,
            ...     task_ids=["task-001", "task-002"]
            ... )
            >>> successful = [r for r in results if r.success]
        """
        direction = direction or self._config.direction

        # Filter tasks
        tasks_to_sync = task_ids or list(self._mappings.keys())
        tasks_to_sync = [t for t in tasks_to_sync if t in self._mappings]

        if not tasks_to_sync:
            return []

        # Process concurrently with limit
        semaphore = asyncio.Semaphore(self._config.max_concurrent_syncs)

        async def sync_with_semaphore(task_id: str) -> SyncResult:
            async with semaphore:
                return await self.sync_task(task_id, direction=direction)

        # Run sync tasks
        results = await asyncio.gather(
            *[sync_with_semaphore(task_id) for task_id in tasks_to_sync],
            return_exceptions=True,
        )

        # Process results
        sync_results = []
        for r in results:
            if isinstance(r, Exception):
                error_result = SyncResult(
                    task_id="unknown",
                    direction=direction,
                )
                error_result.mark_complete(
                    success=False,
                    status=SyncStatus.FAILED,
                    error=str(r),
                )
                sync_results.append(error_result)
            else:
                sync_results.append(r)

        return sync_results

    async def _push_updates(
        self,
        task: Task,
        mapping: TaskIssueMapping,
        client: IssueClient,
        client_config: IssueClientConfig,
        result: SyncResult,
    ) -> None:
        """
        Push updates from task to external issue.

        Args:
            task: The task to sync from
            mapping: Task-issue mapping
            client: Client for the external source
            client_config: Client configuration
            result: Result object to update
        """
        if self._config.dry_run:
            return

        # Map task status to issue status
        if self._config.sync_status:
            issue_status = self._map_task_status_to_issue_status(task.status)
            if issue_status:
                update_result = await client.update_status(
                    issue_id=mapping.issue_id,
                    status=issue_status,
                    config=client_config,
                )

                if update_result.success:
                    result.updates_pushed += 1
                else:
                    result.errors.append(
                        f"Failed to update status: {update_result.error}"
                    )

        # Add comment if task has updated notes
        if self._config.sync_comments and task.description:
            # Check if we should add a comment
            # This is a simplified version - in practice, you'd check
            # if the description has changed since last sync
            comment_result = await client.create_comment(
                issue_id=mapping.issue_id,
                comment=f"Task updated: {task.title}\n\n{task.description}",
                config=client_config,
            )

            if comment_result.success:
                result.comments_added += 1
            else:
                result.errors.append(f"Failed to add comment: {comment_result.error}")

    async def _pull_updates(
        self,
        task: Task,
        mapping: TaskIssueMapping,
        client: IssueClient,
        client_config: IssueClientConfig,
        result: SyncResult,
    ) -> None:
        """
        Pull updates from external issue to task.

        Args:
            task: The task to sync to
            mapping: Task-issue mapping
            client: Client for the external source
            client_config: Client configuration
            result: Result object to update
        """
        # Fetch latest issue data
        fetch_result = await client.fetch_issue(
            issue_id=mapping.issue_id,
            config=client_config,
        )

        if not fetch_result.success:
            result.errors.append(f"Failed to fetch issue: {fetch_result.error}")
            return

        issue_data = fetch_result.data
        if not issue_data:
            return

        # Update task based on issue data
        # This is a simplified version - in practice, you'd do
        # more sophisticated comparison and updates
        result.updates_pulled += 1

    def _map_task_status_to_issue_status(
        self,
        task_status: TaskStatus,
    ) -> Optional[IssueStatus]:
        """
        Map Autoflow task status to issue status.

        Args:
            task_status: Task status

        Returns:
            Corresponding issue status or None
        """
        status_map = {
            TaskStatus.PENDING: IssueStatus.OPEN,
            TaskStatus.IN_PROGRESS: IssueStatus.IN_PROGRESS,
            TaskStatus.COMPLETED: IssueStatus.CLOSED,
            TaskStatus.FAILED: IssueStatus.OPEN,
            TaskStatus.CANCELLED: IssueStatus.CANCELLED,
        }

        return status_map.get(task_status)

    def _load_mappings(self) -> None:
        """Load mappings from state."""
        try:
            mappings_file = self.state.state_dir / self.MAPPINGS_FILE
            if not mappings_file.exists():
                return

            data = self.state.read_json(mappings_file, default={})
            mappings_data = data.get("mappings", {})

            self._mappings = {}
            for task_id, mapping_data in mappings_data.items():
                try:
                    self._mappings[task_id] = TaskIssueMapping.from_dict(mapping_data)
                except (KeyError, ValueError) as e:
                    # Skip invalid mappings
                    continue

        except Exception as e:
            raise SyncError(f"Failed to load mappings: {e}") from e

    def _save_mappings(self) -> None:
        """Save mappings to state."""
        try:
            mappings_data = {
                task_id: mapping.to_dict()
                for task_id, mapping in self._mappings.items()
            }

            data = {
                "mappings": mappings_data,
                "updated_at": datetime.utcnow().isoformat(),
            }

            mappings_file = self.state.state_dir / self.MAPPINGS_FILE
            self.state.write_json(mappings_file, data)

        except Exception as e:
            raise SyncError(f"Failed to save mappings: {e}") from e

    def get_stats(self) -> SyncStats:
        """
        Get sync statistics.

        Returns:
            SyncStats object with current statistics
        """
        return self._stats

    def reset_stats(self) -> None:
        """Reset sync statistics."""
        self._stats = SyncStats()
