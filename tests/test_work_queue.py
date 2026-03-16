"""
Unit Tests for Autoflow Work Queue

Tests the WorkItem and DistributedWorkQueue classes for managing distributed work items.
These tests verify work item lifecycle, queue operations, and persistence.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.coordination.work_queue import (
    DistributedWorkQueue,
    WorkItem,
    WorkItemStatus,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_work_item() -> WorkItem:
    """Create a sample work item."""
    return WorkItem(
        id="work-001",
        task="Implement feature X",
        priority=8,
        max_retries=3,
    )


@pytest.fixture
def temp_queue_dir(tmp_path: Path) -> Path:
    """Create a temporary queue directory."""
    queue_dir = tmp_path / "queue"
    return queue_dir


@pytest.fixture
def initialized_queue(temp_queue_dir: Path) -> DistributedWorkQueue:
    """Create an initialized work queue."""
    queue = DistributedWorkQueue(queue_dir=temp_queue_dir)
    queue.initialize()
    return queue


# ============================================================================
# WorkItemStatus Enum Tests
# ============================================================================


class TestWorkItemStatus:
    """Tests for WorkItemStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert WorkItemStatus.PENDING.value == "pending"
        assert WorkItemStatus.ASSIGNED.value == "assigned"
        assert WorkItemStatus.RUNNING.value == "running"
        assert WorkItemStatus.COMPLETED.value == "completed"
        assert WorkItemStatus.FAILED.value == "failed"
        assert WorkItemStatus.CANCELLED.value == "cancelled"
        assert WorkItemStatus.RETRYING.value == "retrying"


# ============================================================================
# WorkItem Creation Tests
# ============================================================================


class TestWorkItemCreation:
    """Tests for WorkItem creation."""

    def test_create_work_item_with_defaults(self) -> None:
        """Test creating work item with default values."""
        work = WorkItem(id="work-001", task="Test task")
        assert work.id == "work-001"
        assert work.task == "Test task"
        assert work.status == WorkItemStatus.PENDING
        assert work.priority == 5
        assert work.max_retries == 3
        assert work.retry_count == 0
        assert work.assigned_node is None
        assert work.error is None

    def test_create_work_item_with_all_fields(self) -> None:
        """Test creating work item with all fields."""
        work = WorkItem(
            id="work-001",
            task="Test task",
            priority=8,
            max_retries=5,
            metadata={"key": "value"},
        )
        assert work.priority == 8
        assert work.max_retries == 5
        assert work.metadata["key"] == "value"

    def test_created_at_defaults_to_now(self) -> None:
        """Test that created_at defaults to current time."""
        before = datetime.utcnow()
        work = WorkItem(id="work-001", task="Test")
        after = datetime.utcnow()
        assert before <= work.created_at <= after


# ============================================================================
# WorkItem Properties Tests
# ============================================================================


class TestWorkItemProperties:
    """Tests for WorkItem properties."""

    def test_can_retry_true(self, sample_work_item: WorkItem) -> None:
        """Test can_retry returns True when retries available."""
        assert sample_work_item.can_retry is True

    def test_can_retry_false(self, sample_work_item: WorkItem) -> None:
        """Test can_retry returns False when max retries exceeded."""
        sample_work_item.retry_count = 3
        assert sample_work_item.can_retry is False

    def test_failed_property(self, sample_work_item: WorkItem) -> None:
        """Test failed property."""
        sample_work_item.status = WorkItemStatus.FAILED
        assert sample_work_item.failed is False  # Can still retry

        sample_work_item.retry_count = 3
        assert sample_work_item.failed is True  # No retries left


# ============================================================================
# WorkItem Assignment Tests
# ============================================================================


class TestWorkItemAssignment:
    """Tests for work item assignment."""

    def test_assign_to_node(self, sample_work_item: WorkItem) -> None:
        """Test assigning work to a node."""
        sample_work_item.assign_to("node-001")
        assert sample_work_item.assigned_node == "node-001"
        assert sample_work_item.status == WorkItemStatus.ASSIGNED
        assert sample_work_item.assigned_at is not None

    def test_start_work(self, sample_work_item: WorkItem) -> None:
        """Test starting work."""
        sample_work_item.start()
        assert sample_work_item.status == WorkItemStatus.RUNNING
        assert sample_work_item.started_at is not None

    def test_complete_work(self, sample_work_item: WorkItem) -> None:
        """Test completing work."""
        sample_work_item.start()
        sample_work_item.complete()
        assert sample_work_item.status == WorkItemStatus.COMPLETED
        assert sample_work_item.completed_at is not None

    def test_complete_work_with_failed_status(
        self, sample_work_item: WorkItem
    ) -> None:
        """Test completing work with failed status."""
        sample_work_item.start()
        sample_work_item.complete(status=WorkItemStatus.FAILED)
        assert sample_work_item.status == WorkItemStatus.FAILED
        assert sample_work_item.completed_at is not None

    def test_fail_work(self, sample_work_item: WorkItem) -> None:
        """Test failing work."""
        sample_work_item.fail("Connection timeout")
        assert sample_work_item.status == WorkItemStatus.FAILED
        assert sample_work_item.error == "Connection timeout"
        assert sample_work_item.completed_at is not None


# ============================================================================
# WorkItem Retry Tests
# ============================================================================


class TestWorkItemRetry:
    """Tests for work item retry logic."""

    def test_retry_work(self, sample_work_item: WorkItem) -> None:
        """Test retrying work."""
        sample_work_item.assign_to("node-001")
        sample_work_item.start()
        sample_work_item.fail("Error")

        initial_retry_count = sample_work_item.retry_count
        sample_work_item.retry()

        assert sample_work_item.retry_count == initial_retry_count + 1
        assert sample_work_item.status == WorkItemStatus.PENDING
        assert sample_work_item.assigned_node is None
        assert sample_work_item.started_at is None
        assert sample_work_item.completed_at is None
        assert sample_work_item.error is None

    def test_retry_exceeds_max_retries(self, sample_work_item: WorkItem) -> None:
        """Test retrying when max retries exceeded."""
        sample_work_item.retry_count = 3
        with pytest.raises(ValueError, match="Max retries"):
            sample_work_item.retry()


# ============================================================================
# WorkItem Duration Tests
# ============================================================================


class TestWorkItemDuration:
    """Tests for work item duration calculation."""

    def test_duration_seconds_completed(self, sample_work_item: WorkItem) -> None:
        """Test duration calculation for completed work."""
        sample_work_item.started_at = datetime.utcnow() - timedelta(seconds=10)
        sample_work_item.completed_at = datetime.utcnow()
        duration = sample_work_item.duration_seconds()
        assert duration is not None
        assert 9 <= duration <= 11  # Allow some tolerance

    def test_duration_seconds_not_completed(
        self, sample_work_item: WorkItem
    ) -> None:
        """Test duration calculation for incomplete work."""
        duration = sample_work_item.duration_seconds()
        assert duration is None

    def test_time_since_created(self, sample_work_item: WorkItem) -> None:
        """Test time since creation."""
        created_time = sample_work_item.created_at
        import time
        time.sleep(0.01)

        age = sample_work_item.time_since_created()
        assert age >= 0.01  # At least 10ms


# ============================================================================
# DistributedWorkQueue Initialization Tests
# ============================================================================


class TestDistributedWorkQueueInit:
    """Tests for DistributedWorkQueue initialization."""

    def test_create_queue_default_path(self) -> None:
        """Test creating queue with default path."""
        queue = DistributedWorkQueue()
        assert queue.queue_dir.name == "queue"

    def test_create_queue_custom_path(self, temp_queue_dir: Path) -> None:
        """Test creating queue with custom path."""
        queue = DistributedWorkQueue(queue_dir=temp_queue_dir)
        assert queue.queue_dir == temp_queue_dir

    def test_initialize_creates_directories(
        self, temp_queue_dir: Path
    ) -> None:
        """Test that initialize creates required directories."""
        queue = DistributedWorkQueue(queue_dir=temp_queue_dir)
        queue.initialize()

        assert queue.pending_dir.exists()
        assert queue.assigned_dir.exists()
        assert queue.running_dir.exists()
        assert queue.completed_dir.exists()
        assert queue.failed_dir.exists()
        assert queue.backup_dir.exists()

    def test_initialize_is_idempotent(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test that initialize can be called multiple times."""
        initialized_queue.initialize()
        assert initialized_queue.pending_dir.exists()


# ============================================================================
# DistributedWorkQueue Enqueue Tests
# ============================================================================


class TestDistributedWorkQueueEnqueue:
    """Tests for work item enqueue."""

    def test_enqueue_work_item(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test enqueuing a work item."""
        work = WorkItem(id="work-001", task="Test task")
        path = initialized_queue.enqueue(work)

        assert path.exists()
        assert path.name == "work-001.json"

    def test_enqueue_sets_pending_status(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test that enqueue sets status to PENDING."""
        work = WorkItem(id="work-001", task="Test", status=WorkItemStatus.RUNNING)
        initialized_queue.enqueue(work)

        retrieved = initialized_queue.get_work_item("work-001")
        assert retrieved is not None
        assert retrieved.status == WorkItemStatus.PENDING

    def test_enqueue_clears_assignment(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test that enqueue clears node assignment."""
        work = WorkItem(
            id="work-001",
            task="Test",
            assigned_node="node-001",
            status=WorkItemStatus.ASSIGNED,
        )
        initialized_queue.enqueue(work)

        retrieved = initialized_queue.get_work_item("work-001")
        assert retrieved is not None
        assert retrieved.assigned_node is None


# ============================================================================
# DistributedWorkQueue Dequeue Tests
# ============================================================================


class TestDistributedWorkQueueDequeue:
    """Tests for work item dequeue."""

    def test_dequeue_empty_queue(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test dequeuing from empty queue."""
        work = initialized_queue.dequeue()
        assert work == []

    def test_dequeue_single_item(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test dequeuing a single item."""
        work1 = WorkItem(id="work-001", task="Low priority", priority=1)
        work2 = WorkItem(id="work-002", task="High priority", priority=8)
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        items = initialized_queue.dequeue(limit=1)
        assert len(items) == 1
        assert items[0].id == "work-002"  # Higher priority

    def test_dequeue_priority_order(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test that dequeue returns items by priority."""
        work1 = WorkItem(id="work-001", task="Low", priority=1)
        work2 = WorkItem(id="work-002", task="High", priority=8)
        work3 = WorkItem(id="work-003", task="Medium", priority=5)
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)
        initialized_queue.enqueue(work3)

        items = initialized_queue.dequeue(limit=3)
        assert items[0].id == "work-002"
        assert items[1].id == "work-003"
        assert items[2].id == "work-001"

    def test_dequeue_with_priority_filter(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test dequeuing with priority filter."""
        work1 = WorkItem(id="work-001", task="Low", priority=1)
        work2 = WorkItem(id="work-002", task="High", priority=8)
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        items = initialized_queue.dequeue(priority_filter=5)
        assert len(items) == 1
        assert items[0].id == "work-002"


# ============================================================================
# DistributedWorkQueue Assign Tests
# ============================================================================


class TestDistributedWorkQueueAssign:
    """Tests for work item assignment."""

    def test_assign_work(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test assigning work to a node."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)

        assigned = initialized_queue.assign("work-001", "node-001")
        assert assigned is not None
        assert assigned.assigned_node == "node-001"
        assert assigned.status == WorkItemStatus.ASSIGNED

    def test_assign_nonexistent_work(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test assigning non-existent work."""
        result = initialized_queue.assign("nonexistent", "node-001")
        assert result is None

    def test_assign_moves_file(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test that assign moves work file."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)

        initialized_queue.assign("work-001", "node-001")

        # Should be in assigned directory
        assigned_path = initialized_queue.assigned_dir / "work-001.json"
        assert assigned_path.exists()

        # Should not be in pending directory
        pending_path = initialized_queue.pending_dir / "work-001.json"
        assert not pending_path.exists()


# ============================================================================
# DistributedWorkQueue Status Update Tests
# ============================================================================


class TestDistributedWorkQueueStatusUpdate:
    """Tests for work item status updates."""

    def test_update_status_to_running(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test updating status to RUNNING."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)

        updated = initialized_queue.update_work_status(
            "work-001", WorkItemStatus.RUNNING
        )
        assert updated is not None
        assert updated.status == WorkItemStatus.RUNNING
        assert updated.started_at is not None

    def test_update_status_to_completed(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test updating status to COMPLETED."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)

        updated = initialized_queue.update_work_status(
            "work-001", WorkItemStatus.COMPLETED
        )
        assert updated is not None
        assert updated.status == WorkItemStatus.COMPLETED
        assert updated.completed_at is not None

    def test_update_status_with_error(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test updating status with error message."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)

        updated = initialized_queue.update_work_status(
            "work-001", WorkItemStatus.FAILED, error="Connection error"
        )
        assert updated is not None
        assert updated.error == "Connection error"


# ============================================================================
# DistributedWorkQueue List Tests
# ============================================================================


class TestDistributedWorkQueueList:
    """Tests for listing work items."""

    def test_list_all_work(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test listing all work items."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        items = initialized_queue.list_work()
        assert len(items) == 2

    def test_list_work_by_status(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test listing work by status."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        # Update one to assigned
        initialized_queue.update_work_status("work-001", WorkItemStatus.ASSIGNED)

        pending = initialized_queue.list_work(status=WorkItemStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].id == "work-002"

    def test_list_work_by_node(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test listing work by assigned node."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        initialized_queue.assign("work-001", "node-001")
        initialized_queue.assign("work-002", "node-002")

        node1_work = initialized_queue.list_work(node_id="node-001")
        assert len(node1_work) == 1
        assert node1_work[0].id == "work-001"


# ============================================================================
# DistributedWorkQueue Statistics Tests
# ============================================================================


class TestDistributedWorkQueueStats:
    """Tests for queue statistics."""

    def test_get_stats(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test getting queue statistics."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        initialized_queue.assign("work-001", "node-001")
        initialized_queue.update_work_status("work-002", WorkItemStatus.RUNNING)

        stats = initialized_queue.get_stats()
        assert stats["pending"] == 0
        assert stats["assigned"] == 1
        assert stats["running"] == 1


# ============================================================================
# DistributedWorkQueue Retry Tests
# ============================================================================


class TestDistributedWorkQueueRetry:
    """Tests for work item retry."""

    def test_retry_work(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test retrying a failed work item."""
        work = WorkItem(id="work-001", task="Test", max_retries=3)
        initialized_queue.enqueue(work)
        initialized_queue.update_work_status("work-001", WorkItemStatus.FAILED)

        retried = initialized_queue.retry_work("work-001")
        assert retried is not None
        assert retried.status == WorkItemStatus.PENDING
        assert retried.retry_count == 1

    def test_retry_exceeds_max(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test retrying when max retries exceeded."""
        work = WorkItem(id="work-001", task="Test", max_retries=1)
        initialized_queue.enqueue(work)

        # Fail once
        initialized_queue.update_work_status("work-001", WorkItemStatus.FAILED)
        initialized_queue.retry_work("work-001")

        # Fail again
        initialized_queue.update_work_status("work-001", WorkItemStatus.FAILED)

        with pytest.raises(ValueError):
            initialized_queue.retry_work("work-001")


# ============================================================================
# DistributedWorkQueue Clear Tests
# ============================================================================


class TestDistributedWorkQueueClear:
    """Tests for clearing work items."""

    def test_clear_all(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test clearing all work items."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        count = initialized_queue.clear()
        assert count == 2

    def test_clear_by_status(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test clearing work items by status."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        initialized_queue.update_work_status("work-001", WorkItemStatus.COMPLETED)

        count = initialized_queue.clear(status=WorkItemStatus.COMPLETED)
        assert count == 1


# ============================================================================
# DistributedWorkQueue Reassign Tests
# ============================================================================


class TestDistributedWorkQueueReassign:
    """Tests for work item reassignment."""

    def test_reassign_work(self, initialized_queue: DistributedWorkQueue) -> None:
        """Test reassigning work to a different node."""
        work = WorkItem(id="work-001", task="Test")
        initialized_queue.enqueue(work)
        initialized_queue.assign("work-001", "node-001")

        reassigned = initialized_queue.reassign_work("work-001", "node-002")
        assert reassigned is not None
        assert reassigned.assigned_node == "node-002"

    def test_reassign_all_for_node(
        self, initialized_queue: DistributedWorkQueue
    ) -> None:
        """Test reassigning all work for a node."""
        work1 = WorkItem(id="work-001", task="Test 1")
        work2 = WorkItem(id="work-002", task="Test 2")
        initialized_queue.enqueue(work1)
        initialized_queue.enqueue(work2)

        initialized_queue.assign("work-001", "node-001")
        initialized_queue.assign("work-002", "node-001")

        reassigned = initialized_queue.reassign_all_work_for_node("node-001", "node-002")
        assert len(reassigned) == 2
        assert all(w.assigned_node == "node-002" for w in reassigned)
