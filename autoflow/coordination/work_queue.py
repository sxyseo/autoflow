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
from typing import Any, Optional

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
