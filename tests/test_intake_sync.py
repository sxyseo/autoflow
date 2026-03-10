"""
Unit Tests for Autoflow Intake Sync

Tests the sync manager for bidirectional synchronization between
Autoflow tasks and external issue trackers (GitHub, GitLab, Linear).

These tests use mocks to avoid requiring actual API calls or state persistence.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autoflow.core.state import Spec, StateManager, Task, TaskStatus
from autoflow.intake.client import (
    IssueClient,
    IssueClientConfig,
    IssueResult,
    IssueSourceType,
    IssueStatus,
)
from autoflow.intake.models import Issue, IssueSource, SourceType
from autoflow.intake.sync import (
    SyncDirection,
    SyncError,
    SyncManager,
    SyncManagerConfig,
    SyncStatus,
    SyncStats,
    SyncResult,
    TaskIssueMapping,
)


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
def mock_sync_config(temp_state_dir: Path) -> SyncManagerConfig:
    """Create a mock sync manager configuration."""
    return SyncManagerConfig(
        state_dir=temp_state_dir,
        direction=SyncDirection.PUSH,
        auto_sync=False,
        sync_comments=True,
        sync_status=True,
        sync_labels=True,
        dry_run=False,
        batch_size=10,
        max_concurrent_syncs=5,
    )


@pytest.fixture
def mock_state_manager(temp_state_dir: Path) -> StateManager:
    """Create a mock state manager."""
    state = StateManager(temp_state_dir)
    state.initialize()
    return state


@pytest.fixture
def mock_task() -> Task:
    """Create a mock task."""
    return Task(
        id="task-001",  # Task requires an id field
        title="Implement feature",
        description="Feature description",
        status=TaskStatus.IN_PROGRESS,
    )


@pytest.fixture
def mock_issue_client() -> IssueClient:
    """Create a mock issue client."""

    class MockIssueClient(IssueClient):
        def __init__(self) -> None:
            self.fetch_issue_result = IssueResult.from_success(
                data={
                    "id": 123,
                    "title": "Test Issue",
                    "body": "Issue description",
                    "state": "open",
                }
            )
            self.update_status_result = IssueResult.from_success(data={"state": "closed"})
            self.create_comment_result = IssueResult.from_success(
                data={"id": 456, "body": "Comment added"}
            )
            self.list_issues_result = IssueResult.from_success(data={"items": []})
            self.verify_webhook_result = True

        async def fetch_issue(self, issue_id, config):
            return self.fetch_issue_result

        async def list_issues(self, config, **filters):
            return self.list_issues_result

        async def create_comment(self, issue_id, comment, config):
            return self.create_comment_result

        async def update_status(self, issue_id, status, config):
            return self.update_status_result

        async def verify_webhook(self, payload, signature, config):
            return self.verify_webhook_result

    return MockIssueClient()


# ============================================================================
# SyncStatus Enum Tests
# ============================================================================


class TestSyncStatus:
    """Tests for SyncStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert SyncStatus.PENDING.value == "pending"
        assert SyncStatus.IN_PROGRESS.value == "in_progress"
        assert SyncStatus.SUCCESS.value == "success"
        assert SyncStatus.FAILED.value == "failed"
        assert SyncStatus.SKIPPED.value == "skipped"

    def test_status_is_string_enum(self) -> None:
        """Test that status is a string enum."""
        assert isinstance(SyncStatus.SUCCESS, str)


# ============================================================================
# SyncDirection Enum Tests
# ============================================================================


class TestSyncDirection:
    """Tests for SyncDirection enum."""

    def test_direction_values(self) -> None:
        """Test direction enum values."""
        assert SyncDirection.PUSH.value == "push"
        assert SyncDirection.PULL.value == "pull"
        assert SyncDirection.BIDIRECTIONAL.value == "bidirectional"

    def test_direction_is_string_enum(self) -> None:
        """Test that direction is a string enum."""
        assert isinstance(SyncDirection.PUSH, str)


# ============================================================================
# SyncError Tests
# ============================================================================


class TestSyncError:
    """Tests for SyncError exception."""

    def test_error_message(self) -> None:
        """Test error message."""
        error = SyncError("Sync failed")

        assert str(error) == "Sync failed"
        assert error.task_id is None
        assert error.source_id is None

    def test_error_with_task_id(self) -> None:
        """Test error with task ID."""
        error = SyncError("Task not found", task_id="task-001")

        assert str(error) == "Task not found"
        assert error.task_id == "task-001"
        assert error.source_id is None

    def test_error_with_source_id(self) -> None:
        """Test error with source ID."""
        error = SyncError("Issue not found", source_id="GH-123")

        assert str(error) == "Issue not found"
        assert error.task_id is None
        assert error.source_id == "GH-123"

    def test_error_with_both_ids(self) -> None:
        """Test error with both task and source IDs."""
        error = SyncError("Mapping not found", task_id="task-001", source_id="GH-123")

        assert str(error) == "Mapping not found"
        assert error.task_id == "task-001"
        assert error.source_id == "GH-123"


# ============================================================================
# TaskIssueMapping Tests
# ============================================================================


class TestTaskIssueMapping:
    """Tests for TaskIssueMapping dataclass."""

    def test_mapping_creation(self) -> None:
        """Test creating a mapping."""
        mapping = TaskIssueMapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
            source_url="https://github.com/owner/repo/issues/123",
        )

        assert mapping.task_id == "task-001"
        assert mapping.source_type == SourceType.GITHUB
        assert mapping.issue_id == "123"
        assert mapping.source_url == "https://github.com/owner/repo/issues/123"
        assert mapping.last_sync_at is None
        assert mapping.last_sync_status == SyncStatus.PENDING
        assert mapping.sync_count == 0
        assert mapping.metadata == {}

    def test_mapping_defaults(self) -> None:
        """Test default mapping values."""
        mapping = TaskIssueMapping(
            task_id="task-001",
            source_type=SourceType.GITLAB,
            issue_id="456",
        )

        assert mapping.source_url == ""
        assert mapping.last_sync_at is None
        assert mapping.last_sync_status == SyncStatus.PENDING
        assert mapping.sync_count == 0
        assert isinstance(mapping.created_at, datetime)
        assert mapping.metadata == {}

    def test_mark_synced_success(self) -> None:
        """Test marking mapping as successfully synced."""
        mapping = TaskIssueMapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
        )

        mapping.mark_synced(SyncStatus.SUCCESS)

        assert mapping.last_sync_status == SyncStatus.SUCCESS
        assert mapping.sync_count == 1
        assert isinstance(mapping.last_sync_at, datetime)

    def test_mark_synced_failed(self) -> None:
        """Test marking mapping as failed sync."""
        mapping = TaskIssueMapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
            sync_count=5,
        )

        mapping.mark_synced(SyncStatus.FAILED)

        assert mapping.last_sync_status == SyncStatus.FAILED
        assert mapping.sync_count == 5  # Should not increment on failure
        assert isinstance(mapping.last_sync_at, datetime)

    def test_to_dict(self) -> None:
        """Test converting mapping to dictionary."""
        mapping = TaskIssueMapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
            source_url="https://github.com/owner/repo/issues/123",
            metadata={"key": "value"},
        )

        mapping.mark_synced(SyncStatus.SUCCESS)

        data = mapping.to_dict()

        assert data["task_id"] == "task-001"
        assert data["source_type"] == "github"
        assert data["issue_id"] == "123"
        assert data["source_url"] == "https://github.com/owner/repo/issues/123"
        assert data["last_sync_status"] == "success"
        assert data["sync_count"] == 1
        assert data["metadata"] == {"key": "value"}

    def test_from_dict(self) -> None:
        """Test creating mapping from dictionary."""
        data = {
            "task_id": "task-002",
            "source_type": "gitlab",
            "issue_id": "456",
            "source_url": "https://gitlab.com/owner/repo/issues/456",
            "last_sync_at": "2024-01-01T00:00:00",
            "last_sync_status": "success",
            "sync_count": 3,
            "created_at": "2023-12-01T00:00:00",
            "metadata": {"custom": "field"},
        }

        mapping = TaskIssueMapping.from_dict(data)

        assert mapping.task_id == "task-002"
        assert mapping.source_type == SourceType.GITLAB
        assert mapping.issue_id == "456"
        assert mapping.source_url == "https://gitlab.com/owner/repo/issues/456"
        assert mapping.last_sync_status == SyncStatus.SUCCESS
        assert mapping.sync_count == 3
        assert mapping.metadata == {"custom": "field"}


# ============================================================================
# SyncResult Tests
# ============================================================================


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_result_creation(self) -> None:
        """Test creating a sync result."""
        result = SyncResult(
            sync_id="abc123",
            task_id="task-001",
            issue_id="123",
            direction=SyncDirection.PUSH,
        )

        assert result.sync_id == "abc123"
        assert result.task_id == "task-001"
        assert result.issue_id == "123"
        assert result.direction == SyncDirection.PUSH
        assert result.success is False
        assert result.status == SyncStatus.PENDING

    def test_result_defaults(self) -> None:
        """Test default result values."""
        result = SyncResult()

        assert len(result.sync_id) == 8  # UUID prefix
        assert result.task_id == ""
        assert result.issue_id == ""
        assert result.direction == SyncDirection.PUSH
        assert result.success is False
        assert result.status == SyncStatus.PENDING
        assert result.updates_pushed == 0
        assert result.updates_pulled == 0
        assert result.comments_added == 0
        assert result.errors == []
        assert isinstance(result.started_at, datetime)
        assert result.completed_at is None
        assert result.duration_seconds is None

    def test_mark_complete_success(self) -> None:
        """Test marking result as complete with success."""
        result = SyncResult(
            task_id="task-001",
            updates_pushed=2,
            comments_added=1,
        )

        result.mark_complete(success=True, status=SyncStatus.SUCCESS)

        assert result.success is True
        assert result.status == SyncStatus.SUCCESS
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0
        assert len(result.errors) == 0

    def test_mark_complete_failure(self) -> None:
        """Test marking result as complete with failure."""
        result = SyncResult(task_id="task-001")

        result.mark_complete(
            success=False,
            status=SyncStatus.FAILED,
            error="Network error",
        )

        assert result.success is False
        assert result.status == SyncStatus.FAILED
        assert result.completed_at is not None
        assert result.duration_seconds is not None
        assert len(result.errors) == 1
        assert result.errors[0] == "Network error"


# ============================================================================
# SyncStats Tests
# ============================================================================


class TestSyncStats:
    """Tests for SyncStats model."""

    def test_stats_creation(self) -> None:
        """Test creating sync statistics."""
        stats = SyncStats(
            total_syncs=10,
            successful_syncs=8,
            failed_syncs=1,
            skipped_syncs=1,
            total_updates_pushed=15,
            total_updates_pulled=5,
            total_comments_added=3,
        )

        assert stats.total_syncs == 10
        assert stats.successful_syncs == 8
        assert stats.failed_syncs == 1
        assert stats.skipped_syncs == 1
        assert stats.total_updates_pushed == 15
        assert stats.total_updates_pulled == 5
        assert stats.total_comments_added == 3

    def test_stats_defaults(self) -> None:
        """Test default statistics values."""
        stats = SyncStats()

        assert stats.total_syncs == 0
        assert stats.successful_syncs == 0
        assert stats.failed_syncs == 0
        assert stats.skipped_syncs == 0
        assert stats.total_updates_pushed == 0
        assert stats.total_updates_pulled == 0
        assert stats.total_comments_added == 0
        assert stats.average_duration == 0.0
        assert stats.last_sync_at is None
        assert isinstance(stats.started_at, datetime)


# ============================================================================
# SyncManagerConfig Tests
# ============================================================================


class TestSyncManagerConfig:
    """Tests for SyncManagerConfig model."""

    def test_config_creation(self, temp_state_dir: Path) -> None:
        """Test creating a sync manager configuration."""
        config = SyncManagerConfig(
            state_dir=temp_state_dir,
            direction=SyncDirection.BIDIRECTIONAL,
            auto_sync=True,
            dry_run=True,
            batch_size=20,
            max_concurrent_syncs=10,
        )

        assert config.state_dir == temp_state_dir
        assert config.direction == SyncDirection.BIDIRECTIONAL
        assert config.auto_sync is True
        assert config.dry_run is True
        assert config.batch_size == 20
        assert config.max_concurrent_syncs == 10

    def test_config_defaults(self) -> None:
        """Test default configuration values."""
        config = SyncManagerConfig()

        # Check state_dir is a Path
        assert isinstance(config.state_dir, Path)
        assert config.direction == SyncDirection.PUSH
        assert config.auto_sync is False
        assert config.sync_comments is True
        assert config.sync_status is True
        assert config.sync_labels is True
        assert config.dry_run is False
        assert config.batch_size == 10
        assert config.max_concurrent_syncs == 5
        assert config.retry_attempts == 3
        assert config.retry_delay_seconds == 2.0


# ============================================================================
# SyncManager Tests
# ============================================================================


class TestSyncManager:
    """Tests for SyncManager class."""

    def test_manager_creation(self, mock_sync_config: SyncManagerConfig) -> None:
        """Test creating a sync manager."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        assert manager.config == mock_sync_config
        assert manager.mappings == {}
        assert manager.stats.total_syncs == 0

    def test_initialize(self, mock_sync_config: SyncManagerConfig) -> None:
        """Test initializing the sync manager."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        manager.initialize()

        # Check that clients are initialized
        assert SourceType.GITHUB in manager._clients
        assert SourceType.GITLAB in manager._clients
        assert SourceType.LINEAR in manager._clients

    def test_track_mapping(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test tracking a task-issue mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        mapping = manager.track_mapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
            source_url="https://github.com/owner/repo/issues/123",
        )

        assert mapping.task_id == "task-001"
        assert mapping.source_type == SourceType.GITHUB
        assert mapping.issue_id == "123"
        assert "task-001" in manager.mappings

    def test_untrack_mapping(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test removing a task-issue mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        manager.track_mapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
        )

        assert "task-001" in manager.mappings

        removed = manager.untrack_mapping("task-001")

        assert removed is True
        assert "task-001" not in manager.mappings

    def test_untrack_mapping_not_found(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test removing a non-existent mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        removed = manager.untrack_mapping("task-999")

        assert removed is False

    def test_get_mapping(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test getting a mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        original = manager.track_mapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
        )

        retrieved = manager.get_mapping("task-001")

        assert retrieved is not None
        assert retrieved.task_id == original.task_id
        assert retrieved.issue_id == original.issue_id

    def test_get_mapping_not_found(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test getting a non-existent mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        retrieved = manager.get_mapping("task-999")

        assert retrieved is None

    async def test_sync_task_no_mapping(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test syncing a task with no mapping."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)
        manager.initialize()

        result = await manager.sync_task("task-001")

        assert result.success is False
        assert result.status == SyncStatus.FAILED
        assert "No mapping found" in result.errors[0]

    async def test_sync_task_success(
        self,
        mock_sync_config: SyncManagerConfig,
        mock_task: Task,
        mock_state_manager: StateManager,
        mock_issue_client: IssueClient,
    ) -> None:
        """Test successful task sync."""
        manager = SyncManager(
            config=mock_sync_config,
            state=mock_state_manager,
            auto_initialize=False,
        )
        manager.initialize()

        # Add mock client
        manager._clients[SourceType.GITHUB] = mock_issue_client

        # Track mapping
        manager.track_mapping(
            task_id="task-001",
            source_type=SourceType.GITHUB,
            issue_id="123",
        )

        # Save task to state (save_task takes task_id and task_data)
        # Use model_dump(mode='json') to serialize datetime fields
        task_data = mock_task.model_dump(mode='json')
        mock_state_manager.save_task("task-001", task_data)

        # Sync
        result = await manager.sync_task("task-001")

        assert result.success is True
        assert result.status == SyncStatus.SUCCESS
        assert result.task_id == "task-001"
        assert result.issue_id == "123"

    async def test_sync_all(
        self,
        mock_sync_config: SyncManagerConfig,
        mock_state_manager: StateManager,
        mock_issue_client: IssueClient,
    ) -> None:
        """Test syncing multiple tasks."""
        manager = SyncManager(
            config=mock_sync_config,
            state=mock_state_manager,
            auto_initialize=False,
        )
        manager.initialize()

        # Add mock client
        manager._clients[SourceType.GITHUB] = mock_issue_client

        # Track multiple mappings
        for i in range(3):
            task_id = f"task-{i:03d}"
            manager.track_mapping(
                task_id=task_id,
                source_type=SourceType.GITHUB,
                issue_id=str(i),
            )
            # Save task to state (Task requires 'id' field, not 'task_id')
            task = Task(
                id=task_id,
                title=f"Task {i}",
                status=TaskStatus.IN_PROGRESS,
            )
            # Use model_dump(mode='json') to serialize datetime fields
            task_data = task.model_dump(mode='json')
            mock_state_manager.save_task(task_id, task_data)

        # Sync all
        results = await manager.sync_all()

        assert len(results) == 3
        assert all(r.success for r in results)

    async def test_sync_all_with_task_ids(
        self,
        mock_sync_config: SyncManagerConfig,
        mock_state_manager: StateManager,
        mock_issue_client: IssueClient,
    ) -> None:
        """Test syncing specific tasks."""
        manager = SyncManager(
            config=mock_sync_config,
            state=mock_state_manager,
            auto_initialize=False,
        )
        manager.initialize()

        # Add mock client
        manager._clients[SourceType.GITHUB] = mock_issue_client

        # Track multiple mappings
        for i in range(5):
            task_id = f"task-{i:03d}"
            manager.track_mapping(
                task_id=task_id,
                source_type=SourceType.GITHUB,
                issue_id=str(i),
            )
            # Save task to state (Task requires 'id' field, not 'task_id')
            task = Task(
                id=task_id,
                title=f"Task {i}",
                status=TaskStatus.IN_PROGRESS,
            )
            # Use model_dump(mode='json') to serialize datetime fields
            task_data = task.model_dump(mode='json')
            mock_state_manager.save_task(task_id, task_data)

        # Sync only specific tasks
        results = await manager.sync_all(task_ids=["task-001", "task-003"])

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_get_stats(self, mock_sync_config: SyncManagerConfig) -> None:
        """Test getting sync statistics."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        stats = manager.get_stats()

        assert isinstance(stats, SyncStats)
        assert stats.total_syncs == 0

    def test_reset_stats(self, mock_sync_config: SyncManagerConfig) -> None:
        """Test resetting sync statistics."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        # Modify stats
        manager._stats.total_syncs = 10
        manager._stats.successful_syncs = 8

        assert manager.stats.total_syncs == 10

        # Reset
        manager.reset_stats()

        assert manager.stats.total_syncs == 0
        assert manager.stats.successful_syncs == 0

    def test_map_task_status_to_issue_status(
        self,
        mock_sync_config: SyncManagerConfig,
    ) -> None:
        """Test mapping task status to issue status."""
        manager = SyncManager(config=mock_sync_config, auto_initialize=False)

        status_map = {
            TaskStatus.PENDING: IssueStatus.OPEN,
            TaskStatus.IN_PROGRESS: IssueStatus.IN_PROGRESS,
            TaskStatus.COMPLETED: IssueStatus.CLOSED,
            TaskStatus.FAILED: IssueStatus.OPEN,
            TaskStatus.CANCELLED: IssueStatus.CANCELLED,
        }

        for task_status, expected_issue_status in status_map.items():
            issue_status = manager._map_task_status_to_issue_status(task_status)
            assert issue_status == expected_issue_status
