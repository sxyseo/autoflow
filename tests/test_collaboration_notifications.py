"""
Unit Tests for Autoflow Collaboration Notification System

Tests the NotificationManager class and related models (Notification, NotificationStatus, NotificationType)
for persistent notification management with atomic writes.

These tests use temporary directories to avoid affecting real notification files.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.collaboration.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)
from autoflow.collaboration.notifications import NotificationManager


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
def notification_manager(temp_state_dir: Path) -> NotificationManager:
    """Create a NotificationManager instance with temporary directory."""
    manager = NotificationManager(temp_state_dir)
    manager.initialize()
    return manager


@pytest.fixture
def sample_notification_data() -> dict[str, Any]:
    """Return sample notification data for testing."""
    return {
        "id": "notif-001",
        "user_id": "user-001",
        "notification_type": NotificationType.REVIEW_REQUEST,
        "title": "Review Requested",
        "message": "Please review task-001",
        "workspace_id": "workspace-001",
        "team_id": "team-001",
        "status": NotificationStatus.PENDING,
        "metadata": {"task_id": "task-001"},
    }


# ============================================================================
# NotificationStatus Enum Tests
# ============================================================================


class TestNotificationStatus:
    """Tests for NotificationStatus enum."""

    def test_notification_status_values(self) -> None:
        """Test NotificationStatus enum values."""
        assert NotificationStatus.PENDING == "pending"
        assert NotificationStatus.SENT == "sent"
        assert NotificationStatus.DELIVERED == "delivered"
        assert NotificationStatus.READ == "read"
        assert NotificationStatus.DISMISSED == "dismissed"
        assert NotificationStatus.FAILED == "failed"

    def test_notification_status_is_string(self) -> None:
        """Test that NotificationStatus values are strings."""
        assert isinstance(NotificationStatus.PENDING.value, str)

    def test_notification_status_from_string(self) -> None:
        """Test creating NotificationStatus from string."""
        status = NotificationStatus("delivered")
        assert status == NotificationStatus.DELIVERED


# ============================================================================
# NotificationType Enum Tests
# ============================================================================


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_notification_type_values(self) -> None:
        """Test NotificationType enum values."""
        assert NotificationType.REVIEW_REQUEST == "review_request"
        assert NotificationType.REVIEW_APPROVED == "review_approved"
        assert NotificationType.REVIEW_REJECTED == "review_rejected"
        assert NotificationType.MENTION == "mention"
        assert NotificationType.WORKSPACE_UPDATE == "workspace_update"
        assert NotificationType.ROLE_CHANGED == "role_changed"
        assert NotificationType.TASK_ASSIGNED == "task_assigned"
        assert NotificationType.TASK_COMPLETED == "task_completed"

    def test_notification_type_is_string(self) -> None:
        """Test that NotificationType values are strings."""
        assert isinstance(NotificationType.REVIEW_REQUEST.value, str)


# ============================================================================
# Notification Model Tests
# ============================================================================


class TestNotification:
    """Tests for Notification model."""

    def test_notification_init_minimal(self) -> None:
        """Test Notification initialization with minimal fields."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        assert notification.id == "notif-001"
        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_REQUEST
        assert notification.title == "Review Requested"
        assert notification.message == "Please review task-001"
        assert notification.workspace_id is None
        assert notification.team_id is None
        assert notification.status == NotificationStatus.PENDING
        assert notification.read_at is None
        assert notification.expires_at is None
        assert notification.metadata == {}

    def test_notification_init_full(self) -> None:
        """Test Notification initialization with all fields."""
        expires = datetime.utcnow() + timedelta(days=7)
        notification = Notification(
            id="notif-002",
            user_id="user-002",
            notification_type=NotificationType.MENTION,
            title="You were mentioned",
            message="You were mentioned in a comment",
            workspace_id="workspace-001",
            team_id="team-001",
            status=NotificationStatus.DELIVERED,
            expires_at=expires,
            metadata={"comment_id": "comment-001"},
        )

        assert notification.id == "notif-002"
        assert notification.user_id == "user-002"
        assert notification.workspace_id == "workspace-001"
        assert notification.team_id == "team-001"
        assert notification.status == NotificationStatus.DELIVERED
        assert notification.expires_at == expires
        assert notification.metadata == {"comment_id": "comment-001"}

    def test_notification_mark_as_read(self) -> None:
        """Test Notification.mark_as_read() updates status and timestamp."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        assert notification.status == NotificationStatus.PENDING
        assert notification.read_at is None

        notification.mark_as_read()

        assert notification.status == NotificationStatus.READ
        assert notification.read_at is not None
        assert notification.read_at <= datetime.utcnow()

    def test_notification_is_expired_with_expiration(self) -> None:
        """Test Notification.is_expired() returns True when expired."""
        expired = datetime.utcnow() - timedelta(hours=1)
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
            expires_at=expired,
        )

        assert notification.is_expired() is True

    def test_notification_is_expired_not_expired(self) -> None:
        """Test Notification.is_expired() returns False when not expired."""
        future = datetime.utcnow() + timedelta(days=1)
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
            expires_at=future,
        )

        assert notification.is_expired() is False

    def test_notification_is_expired_no_expiration(self) -> None:
        """Test Notification.is_expired() returns False when no expiration."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        assert notification.is_expired() is False


# ============================================================================
# NotificationManager Init Tests
# ============================================================================


class TestNotificationManagerInit:
    """Tests for NotificationManager initialization."""

    def test_init_with_path(self, temp_state_dir: Path) -> None:
        """Test NotificationManager initialization with path."""
        manager = NotificationManager(temp_state_dir)

        assert manager.state_dir == temp_state_dir.resolve()
        assert manager.notifications_dir == temp_state_dir.resolve() / "notifications"

    def test_init_with_string(self, temp_state_dir: Path) -> None:
        """Test NotificationManager initialization with string path."""
        manager = NotificationManager(str(temp_state_dir))

        assert manager.state_dir == temp_state_dir.resolve()

    def test_properties(self, notification_manager: NotificationManager) -> None:
        """Test NotificationManager directory properties."""
        assert notification_manager.notifications_dir == notification_manager.state_dir / "notifications"
        assert notification_manager.backup_dir == notification_manager.notifications_dir / "backups"

    def test_initialize(self, temp_state_dir: Path) -> None:
        """Test NotificationManager.initialize() creates directories."""
        manager = NotificationManager(temp_state_dir)
        manager.initialize()

        assert manager.notifications_dir.exists()
        assert manager.backup_dir.exists()

    def test_initialize_idempotent(self, notification_manager: NotificationManager) -> None:
        """Test NotificationManager.initialize() is idempotent."""
        # Should not raise error when called again
        notification_manager.initialize()

        assert notification_manager.notifications_dir.exists()


# ============================================================================
# NotificationManager Create Tests
# ============================================================================


class TestNotificationManagerCreate:
    """Tests for NotificationManager create operations."""

    def test_create_notification_minimal(self, notification_manager: NotificationManager) -> None:
        """Test create_notification with minimal parameters."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_REQUEST
        assert notification.title == "Review Requested"
        assert notification.status == NotificationStatus.PENDING
        assert notification.id.startswith("notif-")

    def test_create_notification_full(self, notification_manager: NotificationManager) -> None:
        """Test create_notification with all parameters."""
        expires = datetime.utcnow() + timedelta(days=7)
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="You were mentioned",
            message="You were mentioned",
            workspace_id="workspace-001",
            team_id="team-001",
            expires_at=expires,
            metadata={"key": "value"},
        )

        assert notification.workspace_id == "workspace-001"
        assert notification.team_id == "team-001"
        assert notification.expires_at == expires
        assert notification.metadata == {"key": "value"}

    def test_create_notification_saves_to_disk(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test create_notification persists to disk."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        # File should exist
        notification_path = notification_manager._get_notification_path(notification.id, "user-001")
        assert notification_path.exists()

        # Load and verify
        loaded = notification_manager.get_notification(notification.id, "user-001")
        assert loaded.id == notification.id
        assert loaded.title == "Review Requested"


# ============================================================================
# NotificationManager Status Updates Tests
# ============================================================================


class TestNotificationManagerStatusUpdates:
    """Tests for NotificationManager status update operations."""

    def test_send_notification(self, notification_manager: NotificationManager) -> None:
        """Test send_notification updates status to sent."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        updated = notification_manager.send_notification(notification.id, "user-001")

        assert updated.status == NotificationStatus.SENT

    def test_deliver_notification(self, notification_manager: NotificationManager) -> None:
        """Test deliver_notification updates status to delivered."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        updated = notification_manager.deliver_notification(notification.id, "user-001")

        assert updated.status == NotificationStatus.DELIVERED

    def test_mark_as_read(self, notification_manager: NotificationManager) -> None:
        """Test mark_as_read updates status and read_at."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        updated = notification_manager.mark_as_read(notification.id, "user-001")

        assert updated.status == NotificationStatus.READ
        assert updated.read_at is not None

    def test_dismiss_notification(self, notification_manager: NotificationManager) -> None:
        """Test dismiss_notification updates status to dismissed."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        updated = notification_manager.dismiss_notification(notification.id, "user-001")

        assert updated.status == NotificationStatus.DISMISSED


# ============================================================================
# NotificationManager Get Tests
# ============================================================================


class TestNotificationManagerGet:
    """Tests for NotificationManager get operations."""

    def test_get_notification_existing(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_notification returns notification."""
        created = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        retrieved = notification_manager.get_notification(created.id, "user-001")

        assert retrieved.id == created.id
        assert retrieved.title == "Review Requested"

    def test_get_notification_nonexistent(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_notification raises for nonexistent notification."""
        with pytest.raises(FileNotFoundError):
            notification_manager.get_notification("notif-nonexistent", "user-001")

    def test_get_user_notifications_all(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications returns all notifications."""
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review 1",
            message="Message 1",
        )
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention 1",
            message="Message 2",
        )

        notifications = notification_manager.get_user_notifications("user-001")

        assert len(notifications) == 2

    def test_get_user_notifications_filter_by_status(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications filters by status."""
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review 1",
            message="Message 1",
        )
        notif2 = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention 1",
            message="Message 2",
        )
        notification_manager.mark_as_read(notif2.id, "user-001")

        pending = notification_manager.get_user_notifications(
            "user-001", status=NotificationStatus.PENDING
        )
        read = notification_manager.get_user_notifications(
            "user-001", status=NotificationStatus.READ
        )

        assert len(pending) == 1
        assert len(read) == 1

    def test_get_user_notifications_filter_by_type(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications filters by type."""
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review 1",
            message="Message 1",
        )
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention 1",
            message="Message 2",
        )

        mentions = notification_manager.get_user_notifications(
            "user-001", notification_type=NotificationType.MENTION
        )

        assert len(mentions) == 1
        assert mentions[0].notification_type == NotificationType.MENTION

    def test_get_user_notifications_exclude_expired(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications excludes expired by default."""
        expired = datetime.utcnow() - timedelta(hours=1)
        future = datetime.utcnow() + timedelta(days=1)

        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Expired",
            message="Expired message",
            expires_at=expired,
        )
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Valid",
            message="Valid message",
            expires_at=future,
        )

        notifications = notification_manager.get_user_notifications("user-001")

        assert len(notifications) == 1
        assert notifications[0].title == "Valid"

    def test_get_user_notifications_include_expired(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications can include expired."""
        expired = datetime.utcnow() - timedelta(hours=1)

        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Expired",
            message="Expired message",
            expires_at=expired,
        )

        notifications = notification_manager.get_user_notifications(
            "user-001", include_expired=True
        )

        assert len(notifications) == 1

    def test_get_user_notifications_sorted_newest_first(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications sorts by creation time (newest first)."""
        import time

        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="First",
            message="First message",
        )
        time.sleep(0.01)
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Second",
            message="Second message",
        )

        notifications = notification_manager.get_user_notifications("user-001")

        assert notifications[0].title == "Second"
        assert notifications[1].title == "First"

    def test_get_user_notifications_with_limit(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications respects limit."""
        for i in range(5):
            notification_manager.create_notification(
                user_id="user-001",
                notification_type=NotificationType.REVIEW_REQUEST,
                title=f"Review {i}",
                message=f"Message {i}",
            )

        notifications = notification_manager.get_user_notifications("user-001", limit=3)

        assert len(notifications) == 3

    def test_get_unread_notifications(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_unread_notifications returns delivered notifications."""
        notif1 = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review 1",
            message="Message 1",
        )
        notification_manager.deliver_notification(notif1.id, "user-001")

        notif2 = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention 1",
            message="Message 2",
        )
        notification_manager.mark_as_read(notif2.id, "user-001")

        unread = notification_manager.get_unread_notifications("user-001")

        assert len(unread) == 1
        assert unread[0].status == NotificationStatus.DELIVERED


# ============================================================================
# NotificationManager Delete Tests
# ============================================================================


class TestNotificationManagerDelete:
    """Tests for NotificationManager delete operations."""

    def test_delete_notification_existing(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test delete_notification removes notification."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        success = notification_manager.delete_notification(notification.id, "user-001")

        assert success is True
        with pytest.raises(FileNotFoundError):
            notification_manager.get_notification(notification.id, "user-001")

    def test_delete_notification_nonexistent(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test delete_notification returns False for nonexistent."""
        success = notification_manager.delete_notification("notif-nonexistent", "user-001")

        assert success is False

    def test_delete_expired_notifications(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test delete_expired_notifications removes expired."""
        expired = datetime.utcnow() - timedelta(hours=1)
        future = datetime.utcnow() + timedelta(days=1)

        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Expired",
            message="Expired message",
            expires_at=expired,
        )
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Valid",
            message="Valid message",
            expires_at=future,
        )

        count = notification_manager.delete_expired_notifications("user-001")

        assert count == 1

    def test_cleanup_old_notifications(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test cleanup_old_notifications removes old read/dismissed."""
        old_date = datetime.utcnow() - timedelta(days=40)

        # Create notification and manually set old timestamp
        notif1 = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Old Read",
            message="Old message",
        )
        notification_manager.mark_as_read(notif1.id, "user-001")

        # Manually update file with old timestamp
        notif_path = notification_manager._get_notification_path(notif1.id, "user-001")
        data = notification_manager._read_json(notif_path)
        data["created_at"] = old_date.isoformat()
        notification_manager._write_json(notif_path, data)

        # Create recent notification
        notif2 = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Recent",
            message="Recent message",
        )
        notification_manager.mark_as_read(notif2.id, "user-001")

        count = notification_manager.cleanup_old_notifications("user-001", older_than_days=30)

        assert count == 1


# ============================================================================
# NotificationManager Helper Methods Tests
# ============================================================================


class TestNotificationManagerHelpers:
    """Tests for NotificationManager helper notification methods."""

    def test_notify_review_request(self, notification_manager: NotificationManager) -> None:
        """Test notify_review_request creates and sends notification."""
        notification = notification_manager.notify_review_request(
            user_id="user-001",
            reviewer_id="user-002",
            task_id="task-001",
            task_title="Fix authentication bug",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-002"  # Reviewer is notified
        assert notification.notification_type == NotificationType.REVIEW_REQUEST
        assert notification.title == "Review Requested"
        # Note: The method creates and sends, but returns the original notification
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-002")
        assert saved.status == NotificationStatus.SENT
        assert notification.metadata["task_id"] == "task-001"

    def test_notify_review_approved(self, notification_manager: NotificationManager) -> None:
        """Test notify_review_approved creates and sends notification."""
        notification = notification_manager.notify_review_approved(
            user_id="user-001",
            reviewer_id="user-002",
            task_id="task-001",
            task_title="Fix authentication bug",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_APPROVED
        assert notification.title == "Review Approved"
        # Note: The method creates and sends, but returns the original notification
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_review_rejected(self, notification_manager: NotificationManager) -> None:
        """Test notify_review_rejected creates and sends notification."""
        notification = notification_manager.notify_review_rejected(
            user_id="user-001",
            reviewer_id="user-002",
            task_id="task-001",
            task_title="Fix authentication bug",
            reason="Tests failing",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_REJECTED
        assert notification.title == "Review Rejected"
        assert "Tests failing" in notification.message
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_mention(self, notification_manager: NotificationManager) -> None:
        """Test notify_mention creates and sends notification."""
        notification = notification_manager.notify_mention(
            user_id="user-001",
            mentioned_by="user-002",
            content="Can you review this?",
            workspace_id="workspace-001",
            entity_type="comment",
            entity_id="comment-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.MENTION
        assert notification.title == "You were mentioned"
        # Note: The method creates and sends, but returns the original notification
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_mention_truncates_long_content(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test notify_mention truncates long content."""
        long_content = "x" * 200

        notification = notification_manager.notify_mention(
            user_id="user-001",
            mentioned_by="user-002",
            content=long_content,
            workspace_id="workspace-001",
            entity_type="comment",
            entity_id="comment-001",
        )

        assert len(notification.message) < 200
        assert "..." in notification.message

    def test_notify_workspace_update(self, notification_manager: NotificationManager) -> None:
        """Test notify_workspace_update creates and sends notification."""
        notification = notification_manager.notify_workspace_update(
            user_id="user-001",
            workspace_id="workspace-001",
            workspace_name="Project X",
            update_type="settings_changed",
            description="Settings have been updated",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.WORKSPACE_UPDATE
        assert notification.title == "Workspace Update"
        assert "Project X" in notification.message
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_role_changed(self, notification_manager: NotificationManager) -> None:
        """Test notify_role_changed creates and sends notification."""
        notification = notification_manager.notify_role_changed(
            user_id="user-001",
            changed_by="user-002",
            new_role="admin",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.ROLE_CHANGED
        assert notification.title == "Role Changed"
        assert "admin" in notification.message
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_task_assigned(self, notification_manager: NotificationManager) -> None:
        """Test notify_task_assigned creates and sends notification."""
        notification = notification_manager.notify_task_assigned(
            user_id="user-001",
            assigned_by="user-002",
            task_id="task-001",
            task_title="Fix authentication bug",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.TASK_ASSIGNED
        assert notification.title == "Task Assigned"
        assert "Fix authentication bug" in notification.message
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT

    def test_notify_task_completed(self, notification_manager: NotificationManager) -> None:
        """Test notify_task_completed creates and sends notification."""
        notification = notification_manager.notify_task_completed(
            user_id="user-001",
            completed_by="user-002",
            task_id="task-001",
            task_title="Fix authentication bug",
            workspace_id="workspace-001",
        )

        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.TASK_COMPLETED
        assert notification.title == "Task Completed"
        assert "completed by user-002" in notification.message
        # Verify it was sent by loading from disk
        saved = notification_manager.get_notification(notification.id, "user-001")
        assert saved.status == NotificationStatus.SENT


# ============================================================================
# NotificationManager Edge Cases Tests
# ============================================================================


class TestNotificationManagerEdgeCases:
    """Tests for NotificationManager edge cases."""

    def test_get_notifications_for_nonexistent_user(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications returns empty list for nonexistent user."""
        notifications = notification_manager.get_user_notifications("user-nonexistent")

        assert notifications == []

    def test_multiple_users_notifications(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test notifications are separated by user."""
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="User 1 Notif",
            message="Message 1",
        )
        notification_manager.create_notification(
            user_id="user-002",
            notification_type=NotificationType.MENTION,
            title="User 2 Notif",
            message="Message 2",
        )

        user1_notifs = notification_manager.get_user_notifications("user-001")
        user2_notifs = notification_manager.get_user_notifications("user-002")

        assert len(user1_notifs) == 1
        assert len(user2_notifs) == 1
        assert user1_notifs[0].title == "User 1 Notif"
        assert user2_notifs[0].title == "User 2 Notif"

    def test_notification_persistence_across_instances(
        self, temp_state_dir: Path
    ) -> None:
        """Test notifications persist across NotificationManager instances."""
        # Create notification with first instance
        manager1 = NotificationManager(temp_state_dir)
        manager1.initialize()
        notif = manager1.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review",
        )

        # Create second instance and verify
        manager2 = NotificationManager(temp_state_dir)
        manager2.initialize()
        retrieved = manager2.get_notification(notif.id, "user-001")

        assert retrieved.id == notif.id
        assert retrieved.title == "Review Requested"

    def test_invalid_notification_data_skipped(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test get_user_notifications skips invalid notification files."""
        import tempfile

        # Create valid notification
        notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Valid",
            message="Valid message",
        )

        # Create invalid file
        user_dir = notification_manager._get_user_dir("user-001")
        invalid_file = user_dir / "invalid-notif.json"
        invalid_file.write_text("not valid json")

        notifications = notification_manager.get_user_notifications("user-001")

        # Should only return valid notification
        assert len(notifications) == 1
        assert notifications[0].title == "Valid"

    def test_write_json_atomic(self, notification_manager: NotificationManager) -> None:
        """Test _write_json uses atomic write pattern."""
        test_file = notification_manager.notifications_dir / "test-atomic.json"

        notification_manager._write_json(test_file, {"version": 1})
        notification_manager._write_json(test_file, {"version": 2})

        # Should have new content
        result = notification_manager._read_json(test_file)
        assert result == {"version": 2}

    def test_backup_created_on_delete(
        self, notification_manager: NotificationManager
    ) -> None:
        """Test backup is created when notification is deleted."""
        notification = notification_manager.create_notification(
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review",
        )

        notification_manager.delete_notification(notification.id, "user-001")

        # Backup should exist
        backup_path = notification_manager._get_backup_path(
            notification_manager._get_notification_path(notification.id, "user-001")
        )
        assert backup_path.exists()
