"""
Autoflow Work Queue Module

Provides work item models and distributed work queue management for
coordinating task distribution across nodes in a cluster.

Usage:
    from autoflow.coordination.work_queue import WorkItem

    # Create a work item
    work = WorkItem(id="work-001", task="Implement feature X")
    work.assign_to("node-001")
    work.start()
    work.complete()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class WorkItemStatus(str, Enum):
    """Status of a work item in the queue."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class WorkItem(BaseModel):
    """
    Represents a unit of work in the distributed queue.

    A work item represents a task that needs to be executed by a node
    in the cluster. It tracks assignment status, execution state, and
    retry information for fault tolerance.

    Attributes:
        id: Unique work item identifier
        task: Description of the task to execute
        status: Current work status
        assigned_node: ID of the node this work is assigned to (None if unassigned)
        retry_count: Number of times this work has been retried
        max_retries: Maximum number of retry attempts allowed
        created_at: When the work item was created
        assigned_at: When the work was assigned to a node (None if unassigned)
        started_at: When work started (None if not started)
        completed_at: When work completed (None if not completed)
        priority: Work priority (1-10, higher is more urgent)
        metadata: Additional work information
        error: Error message if work failed (None otherwise)

    Example:
        >>> work = WorkItem(
        ...     id="work-001",
        ...     task="Implement feature X",
        ...     priority=8,
        ...     max_retries=3
        ... )
        >>> work.assign_to("node-001")
        >>> work.start()
        >>> if work.failed:
        ...     work.retry()
        >>> else:
        ...     work.complete()
    """

    id: str
    task: str
    status: WorkItemStatus = WorkItemStatus.PENDING
    assigned_node: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    priority: int = 5
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    @property
    def can_retry(self) -> bool:
        """
        Check if this work item can be retried.

        Returns:
            True if retry count is less than max retries

        Example:
            >>> if work.can_retry:
            ...     work.retry()
        """
        return self.retry_count < self.max_retries

    @property
    def failed(self) -> bool:
        """
        Check if this work item has failed.

        Returns:
            True if status is FAILED and no retries remaining

        Example:
            >>> if work.failed:
            ...     print("Work failed permanently")
        """
        return (
            self.status == WorkItemStatus.FAILED
            and not self.can_retry
        )

    def assign_to(self, node_id: str) -> None:
        """
        Assign this work item to a node.

        Sets the assigned_node, updates status to ASSIGNED, and records
        the assignment time.

        Args:
            node_id: ID of the node to assign work to

        Example:
            >>> work.assign_to("node-001")
            >>> assert work.assigned_node == "node-001"
        """
        self.assigned_node = node_id
        self.status = WorkItemStatus.ASSIGNED
        self.assigned_at = datetime.utcnow()

    def start(self) -> None:
        """
        Mark the work item as started.

        Sets the status to RUNNING and records the start time.
        Should be called by the node when it begins executing the work.

        Example:
            >>> work.start()
            >>> assert work.status == WorkItemStatus.RUNNING
        """
        self.status = WorkItemStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(self, status: WorkItemStatus = WorkItemStatus.COMPLETED) -> None:
        """
        Mark the work item as completed.

        Sets the final status and records the completion time.
        Should be called by the node when work finishes.

        Args:
            status: Final status (defaults to COMPLETED, can be FAILED)

        Example:
            >>> work.complete()
            >>> # or if it failed
            >>> work.complete(status=WorkItemStatus.FAILED)
        """
        self.status = status
        self.completed_at = datetime.utcnow()

    def fail(self, error: Optional[str] = None) -> None:
        """
        Mark the work item as failed.

        Sets the status to FAILED, records the completion time,
        and stores the error message.

        Args:
            error: Optional error message describing the failure

        Example:
            >>> work.fail("Connection timeout")
            >>> assert work.status == WorkItemStatus.FAILED
            >>> assert work.error == "Connection timeout"
        """
        self.status = WorkItemStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error = error

    def retry(self) -> None:
        """
        Retry this work item.

        Increments retry_count, resets status to PENDING, and clears
        assignment and timestamps for re-queueing.

        Raises:
            ValueError: If max retries has been exceeded

        Example:
            >>> if work.can_retry:
            ...     work.retry()
            ...     # Can be reassigned to a node
        """
        if not self.can_retry:
            raise ValueError(
                f"Max retries ({self.max_retries}) exceeded. "
                f"Current retry count: {self.retry_count}"
            )

        self.retry_count += 1
        self.status = WorkItemStatus.PENDING
        self.assigned_node = None
        self.assigned_at = None
        self.started_at = None
        self.completed_at = None
        self.error = None

    def duration_seconds(self) -> Optional[float]:
        """
        Calculate the execution duration of the work item.

        Returns:
            Duration in seconds, or None if work hasn't completed

        Example:
            >>> if work.completed_at:
            ...     print(f"Duration: {work.duration_seconds()}s")
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def time_since_created(self) -> float:
        """
        Calculate time elapsed since work item creation.

        Returns:
            Seconds since creation

        Example:
            >>> print(f"Age: {work.time_since_created()}s")
        """
        return (datetime.utcnow() - self.created_at).total_seconds()

    def touch(self) -> None:
        """
        Update the work item's timestamps to current time.

        This can be used to keep track of activity on long-running work.

        Example:
            >>> work.touch()
        """
        # For work items, we update based on current state
        if self.status == WorkItemStatus.RUNNING and self.started_at:
            # Don't modify started_at as it affects duration calculation
            pass


class DistributedWorkQueue:
    """
    Manages a distributed work queue for task distribution across nodes.

    The DistributedWorkQueue provides persistent storage and atomic operations
    for work items, supporting priority-based dequeue, node assignment, and
    fault tolerance through retry logic. Uses write-to-temporary-and-rename
    pattern for crash safety.

    Attributes:
        queue_dir: Directory for queue state storage
        backup_dir: Directory for backup files

    Example:
        >>> queue = DistributedWorkQueue(".autoflow/queue")
        >>> queue.initialize()
        >>> work = WorkItem(id="work-001", task="Fix bug", priority=8)
        >>> queue.enqueue(work)
        >>> next_work = queue.dequeue()
        >>> if next_work:
        ...     queue.assign(next_work.id, "node-001")
    """

    def __init__(self, queue_dir: str | Path = ".autoflow/queue"):
        """
        Initialize the DistributedWorkQueue.

        Args:
            queue_dir: Directory for queue state storage
        """
        self.queue_dir = Path(queue_dir).resolve()
        self.backup_dir = self.queue_dir / "backups"

    @property
    def pending_dir(self) -> Path:
        """Path to pending work directory."""
        return self.queue_dir / "pending"

    @property
    def assigned_dir(self) -> Path:
        """Path to assigned work directory."""
        return self.queue_dir / "assigned"

    @property
    def running_dir(self) -> Path:
        """Path to running work directory."""
        return self.queue_dir / "running"

    @property
    def completed_dir(self) -> Path:
        """Path to completed work directory."""
        return self.queue_dir / "completed"

    @property
    def failed_dir(self) -> Path:
        """Path to failed work directory."""
        return self.queue_dir / "failed"

    def initialize(self) -> None:
        """
        Initialize the queue directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> queue = DistributedWorkQueue(".autoflow/queue")
            >>> queue.initialize()
            >>> assert queue.queue_dir.exists()
        """
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(exist_ok=True)
        self.assigned_dir.mkdir(exist_ok=True)
        self.running_dir.mkdir(exist_ok=True)
        self.completed_dir.mkdir(exist_ok=True)
        self.failed_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_work_path(self, work_id: str, status: WorkItemStatus) -> Path:
        """
        Get the file path for a work item based on its status.

        Args:
            work_id: Work item identifier
            status: Current work status

        Returns:
            Path to the work item file
        """
        if status == WorkItemStatus.PENDING:
            return self.pending_dir / f"{work_id}.json"
        elif status == WorkItemStatus.ASSIGNED:
            return self.assigned_dir / f"{work_id}.json"
        elif status == WorkItemStatus.RUNNING:
            return self.running_dir / f"{work_id}.json"
        elif status == WorkItemStatus.COMPLETED:
            return self.completed_dir / f"{work_id}.json"
        elif status == WorkItemStatus.FAILED:
            return self.failed_dir / f"{work_id}.json"
        else:
            # For other statuses (CANCELLED, RETRYING), use pending
            return self.pending_dir / f"{work_id}.json"

    def _write_work_item(
        self,
        work: WorkItem,
        file_path: Path,
    ) -> Path:
        """
        Write a work item to disk atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.

        Args:
            work: Work item to write
            file_path: Destination path

        Returns:
            Path to the written file
        """
        import json
        import tempfile

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
        )

        try:
            # Write work item data
            with open(temp_fd, "w", encoding="utf-8") as f:
                json.dump(work.model_dump(), f, indent=2, default=str)

            # Atomic rename
            import os
            os.replace(temp_path, file_path)
            return file_path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _read_work_item(self, file_path: Path) -> Optional[WorkItem]:
        """
        Read a work item from disk.

        Args:
            file_path: Path to the work item file

        Returns:
            WorkItem if found, None otherwise
        """
        import json

        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                return WorkItem(**data)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    def enqueue(
        self,
        work: WorkItem,
    ) -> Path:
        """
        Add a work item to the queue.

        The work item is stored in the pending directory. If a work item
        with the same ID already exists, it will be replaced.

        Args:
            work: Work item to add to the queue

        Returns:
            Path to the saved work item file

        Raises:
            OSError: If write operation fails

        Example:
            >>> work = WorkItem(id="work-001", task="Fix bug", priority=8)
            >>> path = queue.enqueue(work)
            >>> print(f"Work queued at: {path}")
        """
        # Ensure work is in pending state
        work.status = WorkItemStatus.PENDING
        work.assigned_node = None

        file_path = self._get_work_path(work.id, WorkItemStatus.PENDING)
        return self._write_work_item(work, file_path)

    def dequeue(
        self,
        limit: int = 1,
        priority_filter: Optional[int] = None,
    ) -> list[WorkItem]:
        """
        Get the next work item(s) from the queue.

        Returns work items sorted by priority (highest first) and creation time.
        Only returns work items with PENDING status.

        Args:
            limit: Maximum number of work items to return
            priority_filter: Optional minimum priority filter (only return
                           work items with this priority or higher)

        Returns:
            List of work items (empty if no pending work)

        Example:
            >>> # Get highest priority work item
            >>> work = queue.dequeue(limit=1)
            >>> if work:
            ...     print(f"Next work: {work[0].task}")

            >>> # Get all high-priority work
            >>> urgent_work = queue.dequeue(limit=10, priority_filter=8)
        """
        pending_work = []

        if not self.pending_dir.exists():
            return pending_work

        # Read all pending work items
        for work_file in self.pending_dir.glob("*.json"):
            work = self._read_work_item(work_file)
            if work and work.status == WorkItemStatus.PENDING:
                # Apply priority filter if specified
                if priority_filter is None or work.priority >= priority_filter:
                    pending_work.append(work)

        # Sort by priority (descending), then by creation time (ascending)
        pending_work.sort(
            key=lambda w: (-w.priority, w.created_at.timestamp())
        )

        return pending_work[:limit]

    def assign(
        self,
        work_id: str,
        node_id: str,
    ) -> Optional[WorkItem]:
        """
        Assign a work item to a node.

        Moves the work item from pending to assigned state and records
        the assignment. The work item is moved to the assigned directory.

        Args:
            work_id: ID of the work item to assign
            node_id: ID of the node to assign work to

        Returns:
            Updated work item if found and assigned, None if not found

        Example:
            >>> work = queue.assign("work-001", "node-001")
            >>> if work:
            ...     print(f"Assigned to {work.assigned_node}")
        """
        # Read the work item from pending
        old_path = self._get_work_path(work_id, WorkItemStatus.PENDING)
        work = self._read_work_item(old_path)

        if not work:
            return None

        # Update work item
        work.assign_to(node_id)

        # Move to assigned directory
        new_path = self._get_work_path(work_id, WorkItemStatus.ASSIGNED)
        self._write_work_item(work, new_path)

        # Remove from pending
        if old_path != new_path and old_path.exists():
            old_path.unlink()

        return work

    def get_work_item(self, work_id: str) -> Optional[WorkItem]:
        """
        Get a work item by ID from any queue directory.

        Searches all queue directories (pending, assigned, running, etc.)
        for the work item.

        Args:
            work_id: Work item identifier

        Returns:
            Work item if found, None otherwise

        Example:
            >>> work = queue.get_work_item("work-001")
            >>> if work:
            ...     print(f"Status: {work.status}")
        """
        # Search all directories
        for status in [
            WorkItemStatus.PENDING,
            WorkItemStatus.ASSIGNED,
            WorkItemStatus.RUNNING,
            WorkItemStatus.COMPLETED,
            WorkItemStatus.FAILED,
        ]:
            path = self._get_work_path(work_id, status)
            work = self._read_work_item(path)
            if work:
                return work

        return None

    def update_work_status(
        self,
        work_id: str,
        status: WorkItemStatus,
        error: Optional[str] = None,
    ) -> Optional[WorkItem]:
        """
        Update the status of a work item.

        Moves the work item to the appropriate directory based on its status.

        Args:
            work_id: ID of the work item to update
            status: New status
            error: Optional error message (for FAILED status)

        Returns:
            Updated work item if found, None otherwise

        Example:
            >>> work = queue.update_work_status("work-001", WorkItemStatus.RUNNING)
            >>> work = queue.update_work_status(
            ...     "work-001",
            ...     WorkItemStatus.FAILED,
            ...     error="Connection timeout"
            ... )
        """
        # Find the work item in any directory
        work = self.get_work_item(work_id)
        if not work:
            return None

        # Get old path
        old_path = self._get_work_path(work_id, work.status)

        # Update status
        work.status = status
        if error:
            work.error = error

        # Set timestamps based on status
        if status == WorkItemStatus.RUNNING and not work.started_at:
            work.started_at = datetime.utcnow()
        elif status in (WorkItemStatus.COMPLETED, WorkItemStatus.FAILED):
            if not work.completed_at:
                work.completed_at = datetime.utcnow()

        # Move to new directory
        new_path = self._get_work_path(work_id, status)
        self._write_work_item(work, new_path)

        # Remove old path if different
        if old_path != new_path and old_path.exists():
            old_path.unlink()

        return work

    def list_work(
        self,
        status: Optional[WorkItemStatus] = None,
        node_id: Optional[str] = None,
    ) -> list[WorkItem]:
        """
        List work items, optionally filtered.

        Args:
            status: Filter by work status
            node_id: Filter by assigned node

        Returns:
            List of work items matching the filters

        Example:
            >>> # Get all pending work
            >>> pending = queue.list_work(status=WorkItemStatus.PENDING)

            >>> # Get all work for a node
            >>> node_work = queue.list_work(node_id="node-001")
        """
        all_work = []

        # Determine which directories to search
        if status:
            directories = [self._get_work_path("", status).parent]
        else:
            directories = [
                self.pending_dir,
                self.assigned_dir,
                self.running_dir,
                self.completed_dir,
                self.failed_dir,
            ]

        # Read work items
        for directory in directories:
            if not directory.exists():
                continue
            for work_file in directory.glob("*.json"):
                work = self._read_work_item(work_file)
                if work:
                    # Apply filters
                    if status and work.status != status:
                        continue
                    if node_id and work.assigned_node != node_id:
                        continue
                    all_work.append(work)

        # Sort by created_at descending
        all_work.sort(key=lambda w: w.created_at, reverse=True)
        return all_work

    def retry_work(self, work_id: str) -> Optional[WorkItem]:
        """
        Retry a failed work item.

        Resets the work item to PENDING status and increments retry count.

        Args:
            work_id: ID of the work item to retry

        Returns:
            Updated work item if found and retryable, None otherwise

        Raises:
            ValueError: If max retries exceeded

        Example:
            >>> work = queue.retry_work("work-001")
            >>> if work:
            ...     print(f"Retry {work.retry_count}/{work.max_retries}")
        """
        work = self.get_work_item(work_id)
        if not work:
            return None

        if not work.can_retry:
            raise ValueError(
                f"Max retries ({work.max_retries}) exceeded for {work_id}"
            )

        # Retry the work item
        work.retry()

        # Move to pending directory
        old_path = self._get_work_path(work_id, work.status)
        new_path = self._get_work_path(work_id, WorkItemStatus.PENDING)
        self._write_work_item(work, new_path)

        if old_path != new_path and old_path.exists():
            old_path.unlink()

        return work

    def get_stats(self) -> dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue metrics

        Example:
            >>> stats = queue.get_stats()
            >>> print(f"Pending: {stats['pending']}")
            >>> print(f"Running: {stats['running']}")
        """
        return {
            "pending": len(list(self.pending_dir.glob("*.json")))
            if self.pending_dir.exists()
            else 0,
            "assigned": len(list(self.assigned_dir.glob("*.json")))
            if self.assigned_dir.exists()
            else 0,
            "running": len(list(self.running_dir.glob("*.json")))
            if self.running_dir.exists()
            else 0,
            "completed": len(list(self.completed_dir.glob("*.json")))
            if self.completed_dir.exists()
            else 0,
            "failed": len(list(self.failed_dir.glob("*.json")))
            if self.failed_dir.exists()
            else 0,
        }

    def clear(self, status: Optional[WorkItemStatus] = None) -> int:
        """
        Clear work items from the queue.

        Args:
            status: Only clear work items with this status.
                   If None, clears all work items.

        Returns:
            Number of work items removed

        Example:
            >>> # Clear all completed work
            >>> count = queue.clear(status=WorkItemStatus.COMPLETED)
            >>> print(f"Cleared {count} completed items")
        """
        removed = 0

        if status:
            # Clear specific status
            directory = self._get_work_path("", status).parent
            if directory.exists():
                for work_file in directory.glob("*.json"):
                    work_file.unlink()
                    removed += 1
        else:
            # Clear all directories
            for directory in [
                self.pending_dir,
                self.assigned_dir,
                self.running_dir,
                self.completed_dir,
                self.failed_dir,
            ]:
                if directory.exists():
                    for work_file in directory.glob("*.json"):
                        work_file.unlink()
                        removed += 1

        return removed
