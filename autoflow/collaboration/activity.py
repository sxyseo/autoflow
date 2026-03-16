"""
Autoflow Activity Tracking Module

Provides activity tracking system that logs all team member actions for
audit trail and visibility. Implements crash-safe file operations using
write-to-temp and rename pattern.

Usage:
    from autoflow.collaboration.activity import ActivityTracker

    # Using the ActivityTracker
    tracker = ActivityTracker(".autoflow")
    tracker.log_task_created(
        user_id="user-001",
        workspace_id="workspace-001",
        task_id="task-001",
        description="Created new task for bug fix"
    )

    # Get recent activity
    activities = tracker.get_recent_activities(limit=10)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import ValidationError

from autoflow.collaboration.models import (
    ActivityEvent,
    ActivityEventType,
)
from autoflow.collaboration.types import ActivityMetadata


class ActivityTracker:
    """
    Manages activity tracking for team collaboration.

    Provides atomic file operations with crash safety using the
    write-to-temporary-and-rename pattern. Activity events are organized
    by date in subdirectories for efficient querying.

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        activities_dir: Root directory for activity storage
        backup_dir: Directory for backup files

    Example:
        >>> tracker = ActivityTracker(".autoflow")
        >>> tracker.initialize()
        >>> tracker.log_task_created(
        ...     user_id="user-001",
        ...     workspace_id="workspace-001",
        ...     task_id="task-001"
        ... )
    """

    # Subdirectories within activities directory
    ACTIVITIES_DIR = "activities"
    BACKUP_DIR = "backups"

    def __init__(self, state_dir: Union[str, Path]):
        """
        Initialize the ActivityTracker.

        Args:
            state_dir: Root directory for state storage.
                       Activities will be stored in state_dir/activities/
        """
        self.state_dir = Path(state_dir).resolve()
        self.activities_dir = self.state_dir / self.ACTIVITIES_DIR
        self.backup_dir = self.activities_dir / self.BACKUP_DIR

    @property
    def activities_dir(self) -> Path:
        """Path to activities directory."""
        return self._activities_dir

    @activities_dir.setter
    def activities_dir(self, value: Path) -> None:
        """Set activities directory and create parent structure."""
        self._activities_dir = value

    def initialize(self) -> None:
        """
        Initialize the activity directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> tracker = ActivityTracker(".autoflow")
            >>> tracker.initialize()
            >>> assert tracker.activities_dir.exists()
        """
        self.activities_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.activities_dir)
        return self.backup_dir / f"{relative}.bak"

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of an existing file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if file doesn't exist
        """
        if not file_path.exists():
            return None

        backup_path = self._get_backup_path(file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(file_path, backup_path)
        return backup_path

    def _write_json(
        self,
        file_path: Path,
        data: dict[str, Any],
        indent: int = 2,
    ) -> Path:
        """
        Write JSON data to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.
        Creates parent directories if needed.

        Args:
            file_path: Destination path
            data: JSON-serializable data
            indent: Indentation level for pretty printing

        Returns:
            Path to the written file

        Raises:
            OSError: If write operation fails
        """
        path = file_path.resolve()

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(path)

        # Write to temporary file in same directory (ensures same filesystem)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, path)
            return path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _read_json(
        self,
        file_path: Path,
        default: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Read JSON data from a file.

        Args:
            file_path: Path to the JSON file
            default: Default value if file doesn't exist or is invalid

        Returns:
            Parsed JSON data or default value

        Raises:
            ValueError: If file contains invalid JSON and no default provided
        """
        if not file_path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            if default is not None:
                return default
            raise ValueError(f"Invalid JSON in {file_path}: {e}") from e

    def _get_event_path(self, event_id: str, created_at: datetime) -> Path:
        """
        Get the file path for an activity event.

        Events are organized by date: activities/YYYY-MM/event_id.json

        Args:
            event_id: Unique event identifier
            created_at: Timestamp when event was created

        Returns:
            Path to the event file
        """
        date_str = created_at.strftime("%Y-%m")
        return self.activities_dir / date_str / f"{event_id}.json"

    def _generate_event_id(self) -> str:
        """
        Generate a unique event ID.

        Returns:
            Unique event identifier
        """
        return f"event-{uuid4().hex}"

    # === Event Logging Methods ===

    def log_event(
        self,
        event_type: ActivityEventType,
        user_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a generic activity event.

        Args:
            event_type: Type of event that occurred
            user_id: User ID who performed the action
            description: Human-readable description of the event
            workspace_id: Workspace ID where the action occurred
            team_id: Team ID associated with the action
            entity_type: Type of entity affected (task, spec, review, etc.)
            entity_id: ID of the entity affected
            metadata: Additional event data

        Returns:
            The created ActivityEvent

        Example:
            >>> event = tracker.log_event(
            ...     event_type=ActivityEventType.TASK_CREATED,
            ...     user_id="user-001",
            ...     description="Created new task",
            ...     workspace_id="workspace-001",
            ...     entity_type="task",
            ...     entity_id="task-001"
            ... )
        """
        event_id = self._generate_event_id()
        created_at = datetime.utcnow()

        event = ActivityEvent(
            id=event_id,
            event_type=event_type,
            user_id=user_id,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            metadata=metadata or {},
            created_at=created_at,
        )

        # Save event to file
        event_path = self._get_event_path(event_id, created_at)
        self._write_json(event_path, event.model_dump(mode='json'))

        return event

    def log_task_created(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task creation event.

        Args:
            user_id: User ID who created the task
            task_id: ID of the created task
            description: Description of the task
            workspace_id: Workspace ID where task was created
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent

        Example:
            >>> event = tracker.log_task_created(
            ...     user_id="user-001",
            ...     task_id="task-001",
            ...     description="Created bug fix task",
            ...     workspace_id="workspace-001"
            ... )
        """
        if not description:
            description = f"Created task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.TASK_CREATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_task_updated(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task update event.

        Args:
            user_id: User ID who updated the task
            task_id: ID of the updated task
            description: Description of the update
            workspace_id: Workspace ID where task was updated
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Updated task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.TASK_UPDATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_task_deleted(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task deletion event.

        Args:
            user_id: User ID who deleted the task
            task_id: ID of the deleted task
            description: Description of the deletion
            workspace_id: Workspace ID where task was deleted
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Deleted task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.TASK_DELETED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_task_assigned(
        self,
        user_id: str,
        task_id: str,
        assigned_to: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task assignment event.

        Args:
            user_id: User ID who assigned the task
            task_id: ID of the assigned task
            assigned_to: User ID the task was assigned to
            description: Description of the assignment
            workspace_id: Workspace ID where task was assigned
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Assigned task {task_id} to {assigned_to}"

        event_metadata = metadata or {}
        event_metadata["assigned_to"] = assigned_to

        return self.log_event(
            event_type=ActivityEventType.TASK_ASSIGNED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=event_metadata,
        )

    def log_task_completed(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task completion event.

        Args:
            user_id: User ID who completed the task
            task_id: ID of the completed task
            description: Description of the completion
            workspace_id: Workspace ID where task was completed
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Completed task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.TASK_COMPLETED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_task_failed(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a task failure event.

        Args:
            user_id: User ID associated with the task
            task_id: ID of the failed task
            description: Description of the failure
            workspace_id: Workspace ID where task failed
            team_id: Team ID associated with the task
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Task {task_id} failed"

        return self.log_event(
            event_type=ActivityEventType.TASK_FAILED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="task",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_spec_created(
        self,
        user_id: str,
        spec_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a spec creation event.

        Args:
            user_id: User ID who created the spec
            spec_id: ID of the created spec
            description: Description of the spec
            workspace_id: Workspace ID where spec was created
            team_id: Team ID associated with the spec
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Created spec {spec_id}"

        return self.log_event(
            event_type=ActivityEventType.SPEC_CREATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="spec",
            entity_id=spec_id,
            metadata=metadata,
        )

    def log_spec_updated(
        self,
        user_id: str,
        spec_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a spec update event.

        Args:
            user_id: User ID who updated the spec
            spec_id: ID of the updated spec
            description: Description of the update
            workspace_id: Workspace ID where spec was updated
            team_id: Team ID associated with the spec
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Updated spec {spec_id}"

        return self.log_event(
            event_type=ActivityEventType.SPEC_UPDATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="spec",
            entity_id=spec_id,
            metadata=metadata,
        )

    def log_spec_deleted(
        self,
        user_id: str,
        spec_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a spec deletion event.

        Args:
            user_id: User ID who deleted the spec
            spec_id: ID of the deleted spec
            description: Description of the deletion
            workspace_id: Workspace ID where spec was deleted
            team_id: Team ID associated with the spec
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Deleted spec {spec_id}"

        return self.log_event(
            event_type=ActivityEventType.SPEC_DELETED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="spec",
            entity_id=spec_id,
            metadata=metadata,
        )

    def log_review_requested(
        self,
        user_id: str,
        task_id: str,
        reviewer_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a review request event.

        Args:
            user_id: User ID who requested the review
            task_id: ID of the task to review
            reviewer_id: User ID of the requested reviewer
            description: Description of the review request
            workspace_id: Workspace ID where review was requested
            team_id: Team ID associated with the review
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Requested review from {reviewer_id} for task {task_id}"

        event_metadata = metadata or {}
        event_metadata["reviewer_id"] = reviewer_id

        return self.log_event(
            event_type=ActivityEventType.REVIEW_REQUESTED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="review",
            entity_id=task_id,
            metadata=event_metadata,
        )

    def log_review_submitted(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a review submission event.

        Args:
            user_id: User ID who submitted the review
            task_id: ID of the reviewed task
            description: Description of the review
            workspace_id: Workspace ID where review was submitted
            team_id: Team ID associated with the review
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Submitted review for task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.REVIEW_SUBMITTED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="review",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_review_approved(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a review approval event.

        Args:
            user_id: User ID who approved the review
            task_id: ID of the approved task
            description: Description of the approval
            workspace_id: Workspace ID where review was approved
            team_id: Team ID associated with the review
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Approved task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.REVIEW_APPROVED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="review",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_review_rejected(
        self,
        user_id: str,
        task_id: str,
        description: str = "",
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a review rejection event.

        Args:
            user_id: User ID who rejected the review
            task_id: ID of the rejected task
            description: Description of the rejection
            workspace_id: Workspace ID where review was rejected
            team_id: Team ID associated with the review
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Rejected task {task_id}"

        return self.log_event(
            event_type=ActivityEventType.REVIEW_REJECTED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="review",
            entity_id=task_id,
            metadata=metadata,
        )

    def log_member_added(
        self,
        user_id: str,
        member_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        description: str = "",
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a member addition event.

        Args:
            user_id: User ID who added the member
            member_id: User ID of the added member
            workspace_id: Workspace ID where member was added
            team_id: Team ID where member was added
            description: Description of the addition
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            context = workspace_id or team_id
            description = f"Added member {member_id} to {context}"

        event_metadata = metadata or {}
        event_metadata["member_id"] = member_id

        return self.log_event(
            event_type=ActivityEventType.MEMBER_ADDED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace" if workspace_id else "team",
            entity_id=workspace_id or team_id,
            metadata=event_metadata,
        )

    def log_member_removed(
        self,
        user_id: str,
        member_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        description: str = "",
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a member removal event.

        Args:
            user_id: User ID who removed the member
            member_id: User ID of the removed member
            workspace_id: Workspace ID where member was removed
            team_id: Team ID where member was removed
            description: Description of the removal
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            context = workspace_id or team_id
            description = f"Removed member {member_id} from {context}"

        event_metadata = metadata or {}
        event_metadata["member_id"] = member_id

        return self.log_event(
            event_type=ActivityEventType.MEMBER_REMOVED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace" if workspace_id else "team",
            entity_id=workspace_id or team_id,
            metadata=event_metadata,
        )

    def log_role_changed(
        self,
        user_id: str,
        member_id: str,
        new_role: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        description: str = "",
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a role change event.

        Args:
            user_id: User ID who changed the role
            member_id: User ID whose role was changed
            new_role: New role assigned to the member
            workspace_id: Workspace ID where role was changed
            team_id: Team ID where role was changed
            description: Description of the role change
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            context = workspace_id or team_id
            description = f"Changed role of {member_id} to {new_role} in {context}"

        event_metadata = metadata or {}
        event_metadata["member_id"] = member_id
        event_metadata["new_role"] = new_role

        return self.log_event(
            event_type=ActivityEventType.ROLE_CHANGED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace" if workspace_id else "team",
            entity_id=workspace_id or team_id,
            metadata=event_metadata,
        )

    def log_workspace_created(
        self,
        user_id: str,
        workspace_id: str,
        description: str = "",
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a workspace creation event.

        Args:
            user_id: User ID who created the workspace
            workspace_id: ID of the created workspace
            description: Description of the workspace
            team_id: Team ID associated with the workspace
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Created workspace {workspace_id}"

        return self.log_event(
            event_type=ActivityEventType.WORKSPACE_CREATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace",
            entity_id=workspace_id,
            metadata=metadata,
        )

    def log_workspace_updated(
        self,
        user_id: str,
        workspace_id: str,
        description: str = "",
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a workspace update event.

        Args:
            user_id: User ID who updated the workspace
            workspace_id: ID of the updated workspace
            description: Description of the update
            team_id: Team ID associated with the workspace
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Updated workspace {workspace_id}"

        return self.log_event(
            event_type=ActivityEventType.WORKSPACE_UPDATED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace",
            entity_id=workspace_id,
            metadata=metadata,
        )

    def log_workspace_deleted(
        self,
        user_id: str,
        workspace_id: str,
        description: str = "",
        team_id: Optional[str] = None,
        metadata: Optional[ActivityMetadata] = None,
    ) -> ActivityEvent:
        """
        Log a workspace deletion event.

        Args:
            user_id: User ID who deleted the workspace
            workspace_id: ID of the deleted workspace
            description: Description of the deletion
            team_id: Team ID associated with the workspace
            metadata: Additional event data

        Returns:
            The created ActivityEvent
        """
        if not description:
            description = f"Deleted workspace {workspace_id}"

        return self.log_event(
            event_type=ActivityEventType.WORKSPACE_DELETED,
            user_id=user_id,
            description=description,
            workspace_id=workspace_id,
            team_id=team_id,
            entity_type="workspace",
            entity_id=workspace_id,
            metadata=metadata,
        )

    # === Query Methods ===

    def get_recent_activities(
        self,
        limit: int = 100,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[ActivityEvent]:
        """
        Get recent activity events.

        Args:
            limit: Maximum number of events to return
            workspace_id: Filter by workspace ID
            team_id: Filter by team ID
            user_id: Filter by user ID

        Returns:
            List of ActivityEvent objects, sorted by created_at descending

        Example:
            >>> activities = tracker.get_recent_activities(limit=10)
            >>> for activity in activities:
            ...     print(f"{activity.created_at}: {activity.description}")
        """
        activities = []

        if not self.activities_dir.exists():
            return activities

        # Walk through date directories
        for date_dir in sorted(self.activities_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue

            for event_file in date_dir.glob("*.json"):
                try:
                    event_data = self._read_json(event_file)
                    if event_data is None:
                        continue

                    # Apply filters
                    if workspace_id and event_data.get("workspace_id") != workspace_id:
                        continue
                    if team_id and event_data.get("team_id") != team_id:
                        continue
                    if user_id and event_data.get("user_id") != user_id:
                        continue

                    # Convert to ActivityEvent
                    event = ActivityEvent(**event_data)
                    activities.append(event)

                    # Check if we've reached the limit
                    if len(activities) >= limit:
                        return activities
                except (json.JSONDecodeError, ValidationError, KeyError):
                    continue

        # Sort by created_at descending
        activities.sort(key=lambda e: e.created_at, reverse=True)
        return activities

    def get_activity_count(self) -> int:
        """
        Get the total count of activity events.

        Returns:
            Number of activity events
        """
        if not self.activities_dir.exists():
            return 0

        count = 0
        for date_dir in self.activities_dir.iterdir():
            if date_dir.is_dir():
                count += len(list(date_dir.glob("*.json")))

        return count

    def query_activities(
        self,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        event_type: Optional[ActivityEventType] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        sort_descending: bool = True,
    ) -> list[ActivityEvent]:
        """
        Query activity events with advanced filters.

        Provides comprehensive filtering capabilities including user, workspace,
        team, event type, entity, date range, and result limiting.

        Args:
            user_id: Filter by user ID who performed the action
            workspace_id: Filter by workspace ID
            team_id: Filter by team ID
            event_type: Filter by event type
            entity_type: Filter by entity type (task, spec, review, etc.)
            entity_id: Filter by specific entity ID
            start_date: Filter events after this date (inclusive)
            end_date: Filter events before this date (inclusive)
            limit: Maximum number of events to return
            sort_descending: Sort by created_at descending if True, ascending if False

        Returns:
            List of ActivityEvent objects matching all filters, sorted by created_at

        Example:
            >>> activities = tracker.query_activities(
            ...     workspace_id="workspace-001",
            ...     event_type=ActivityEventType.TASK_CREATED,
            ...     start_date=datetime(2026, 1, 1),
            ...     limit=50
            ... )
        """
        activities = []

        if not self.activities_dir.exists():
            return activities

        # Walk through date directories
        for date_dir in sorted(self.activities_dir.iterdir(), reverse=sort_descending):
            if not date_dir.is_dir():
                continue

            for event_file in date_dir.glob("*.json"):
                try:
                    event_data = self._read_json(event_file)
                    if event_data is None:
                        continue

                    # Apply all filters
                    if user_id and event_data.get("user_id") != user_id:
                        continue
                    if workspace_id and event_data.get("workspace_id") != workspace_id:
                        continue
                    if team_id and event_data.get("team_id") != team_id:
                        continue
                    if event_type and event_data.get("event_type") != event_type.value:
                        continue
                    if entity_type and event_data.get("entity_type") != entity_type:
                        continue
                    if entity_id and event_data.get("entity_id") != entity_id:
                        continue

                    # Date range filtering
                    event_date = datetime.fromisoformat(
                        event_data.get("created_at", "").replace("Z", "+00:00")
                    )
                    if start_date and event_date < start_date:
                        continue
                    if end_date and event_date > end_date:
                        continue

                    # Convert to ActivityEvent
                    event = ActivityEvent(**event_data)
                    activities.append(event)

                    # Check if we've reached the limit
                    if limit is not None and len(activities) >= limit:
                        return activities
                except (json.JSONDecodeError, ValidationError, KeyError, ValueError):
                    continue

        # Sort by created_at
        activities.sort(key=lambda e: e.created_at, reverse=sort_descending)
        return activities

    def get_activities_by_user(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[ActivityEvent]:
        """
        Get all activity events for a specific user.

        Args:
            user_id: User ID to filter by
            start_date: Filter events after this date (inclusive)
            end_date: Filter events before this date (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of ActivityEvent objects for the user, sorted by created_at descending

        Example:
            >>> activities = tracker.get_activities_by_user(
            ...     user_id="user-001",
            ...     limit=20
            ... )
        """
        return self.query_activities(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            sort_descending=True,
        )

    def get_activities_by_workspace(
        self,
        workspace_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[ActivityEvent]:
        """
        Get all activity events for a specific workspace.

        Args:
            workspace_id: Workspace ID to filter by
            start_date: Filter events after this date (inclusive)
            end_date: Filter events before this date (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of ActivityEvent objects for the workspace, sorted by created_at descending

        Example:
            >>> activities = tracker.get_activities_by_workspace(
            ...     workspace_id="workspace-001",
            ...     limit=50
            ... )
        """
        return self.query_activities(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            sort_descending=True,
        )

    def get_activities_by_type(
        self,
        event_type: ActivityEventType,
        workspace_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[ActivityEvent]:
        """
        Get all activity events of a specific type.

        Args:
            event_type: Event type to filter by
            workspace_id: Optional workspace ID to further filter
            start_date: Filter events after this date (inclusive)
            end_date: Filter events before this date (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of ActivityEvent objects of the specified type, sorted by created_at descending

        Example:
            >>> activities = tracker.get_activities_by_type(
            ...     event_type=ActivityEventType.TASK_COMPLETED,
            ...     workspace_id="workspace-001"
            ... )
        """
        return self.query_activities(
            event_type=event_type,
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            sort_descending=True,
        )

    def get_activities_in_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[ActivityEvent]:
        """
        Get all activity events within a specific date range.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            workspace_id: Optional workspace ID to filter
            team_id: Optional team ID to filter
            limit: Maximum number of events to return

        Returns:
            List of ActivityEvent objects within the date range, sorted by created_at descending

        Example:
            >>> from datetime import datetime, timedelta
            >>> end = datetime.utcnow()
            >>> start = end - timedelta(days=7)
            >>> activities = tracker.get_activities_in_date_range(
            ...     start_date=start,
            ...     end_date=end,
            ...     workspace_id="workspace-001"
            ... )
        """
        return self.query_activities(
            start_date=start_date,
            end_date=end_date,
            workspace_id=workspace_id,
            team_id=team_id,
            limit=limit,
            sort_descending=True,
        )

    def get_activities_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[ActivityEvent]:
        """
        Get all activity events for a specific entity (task, spec, etc.).

        Args:
            entity_type: Type of entity (task, spec, review, etc.)
            entity_id: ID of the entity
            start_date: Filter events after this date (inclusive)
            end_date: Filter events before this date (inclusive)
            limit: Maximum number of events to return

        Returns:
            List of ActivityEvent objects for the entity, sorted by created_at descending

        Example:
            >>> activities = tracker.get_activities_for_entity(
            ...     entity_type="task",
            ...     entity_id="task-001"
            ... )
        """
        return self.query_activities(
            entity_type=entity_type,
            entity_id=entity_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            sort_descending=True,
        )
