"""
Unit Tests for Collaboration Data Models

Tests the collaboration models (User, Team, Workspace, Role, ActivityEvent, Notification)
for team collaboration features including role-based access control and activity tracking.

These tests ensure all models work correctly with Pydantic validation and methods.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from autoflow.collaboration.models import (
    ActivityEvent,
    ActivityEventType,
    Notification,
    NotificationStatus,
    NotificationType,
    Permission,
    Role,
    RoleType,
    Team,
    User,
    Workspace,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    """Return sample user data for testing."""
    return {
        "id": "user-001",
        "username": "alice",
        "email": "alice@example.com",
        "full_name": "Alice Johnson",
    }


@pytest.fixture
def sample_team_data() -> dict[str, Any]:
    """Return sample team data for testing."""
    return {
        "id": "team-001",
        "name": "Engineering",
        "description": "Core engineering team",
        "member_ids": ["user-001", "user-002"],
    }


@pytest.fixture
def sample_workspace_data() -> dict[str, Any]:
    """Return sample workspace data for testing."""
    return {
        "id": "workspace-001",
        "name": "Project X",
        "description": "Main project workspace",
        "team_id": "team-001",
        "settings": {"visibility": "team"},
    }


@pytest.fixture
def sample_role_data() -> dict[str, Any]:
    """Return sample role data for testing."""
    return {
        "user_id": "user-001",
        "role_type": RoleType.ADMIN,
        "team_id": "team-001",
        "granted_by": "user-002",
    }


@pytest.fixture
def sample_activity_data() -> dict[str, Any]:
    """Return sample activity event data for testing."""
    return {
        "id": "event-001",
        "event_type": ActivityEventType.TASK_CREATED,
        "user_id": "user-001",
        "workspace_id": "workspace-001",
        "team_id": "team-001",
        "entity_type": "task",
        "entity_id": "task-001",
        "description": "Created new task for feature X",
    }


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
    }


# ============================================================================
# RoleType Enum Tests
# ============================================================================


class TestRoleType:
    """Tests for RoleType enum."""

    def test_role_type_values(self) -> None:
        """Test RoleType enum values."""
        assert RoleType.OWNER == "owner"
        assert RoleType.ADMIN == "admin"
        assert RoleType.MEMBER == "member"
        assert RoleType.REVIEWER == "reviewer"
        assert RoleType.VIEWER == "viewer"

    def test_role_type_is_string(self) -> None:
        """Test that RoleType values are strings."""
        assert isinstance(RoleType.ADMIN.value, str)

    def test_role_type_from_string(self) -> None:
        """Test creating RoleType from string."""
        role = RoleType("admin")
        assert role == RoleType.ADMIN


# ============================================================================
# Permission Enum Tests
# ============================================================================


class TestPermission:
    """Tests for Permission enum."""

    def test_task_permissions(self) -> None:
        """Test task-related permissions."""
        assert Permission.DISPATCH_TASK == "dispatch_task"
        assert Permission.MODIFY_TASK == "modify_task"
        assert Permission.DELETE_TASK == "delete_task"

    def test_spec_permissions(self) -> None:
        """Test spec-related permissions."""
        assert Permission.CREATE_SPEC == "create_spec"
        assert Permission.MODIFY_SPEC == "modify_spec"
        assert Permission.DELETE_SPEC == "delete_spec"

    def test_review_permissions(self) -> None:
        """Test review-related permissions."""
        assert Permission.REQUEST_REVIEW == "request_review"
        assert Permission.REVIEW_TASK == "review_task"
        assert Permission.APPROVE_TASK == "approve_task"
        assert Permission.REJECT_TASK == "reject_task"

    def test_team_permissions(self) -> None:
        """Test team/workspace permissions."""
        assert Permission.MANAGE_MEMBERS == "manage_members"
        assert Permission.MANAGE_SETTINGS == "manage_settings"
        assert Permission.DELETE_WORKSPACE == "delete_workspace"

    def test_general_permissions(self) -> None:
        """Test general permissions."""
        assert Permission.VIEW_ACTIVITY == "view_activity"
        assert Permission.MANAGE_NOTIFICATIONS == "manage_notifications"


# ============================================================================
# ActivityEventType Enum Tests
# ============================================================================


class TestActivityEventType:
    """Tests for ActivityEventType enum."""

    def test_task_events(self) -> None:
        """Test task-related event types."""
        assert ActivityEventType.TASK_CREATED == "task_created"
        assert ActivityEventType.TASK_UPDATED == "task_updated"
        assert ActivityEventType.TASK_DELETED == "task_deleted"
        assert ActivityEventType.TASK_ASSIGNED == "task_assigned"
        assert ActivityEventType.TASK_COMPLETED == "task_completed"
        assert ActivityEventType.TASK_FAILED == "task_failed"

    def test_spec_events(self) -> None:
        """Test spec-related event types."""
        assert ActivityEventType.SPEC_CREATED == "spec_created"
        assert ActivityEventType.SPEC_UPDATED == "spec_updated"
        assert ActivityEventType.SPEC_DELETED == "spec_deleted"

    def test_review_events(self) -> None:
        """Test review-related event types."""
        assert ActivityEventType.REVIEW_REQUESTED == "review_requested"
        assert ActivityEventType.REVIEW_SUBMITTED == "review_submitted"
        assert ActivityEventType.REVIEW_APPROVED == "review_approved"
        assert ActivityEventType.REVIEW_REJECTED == "review_rejected"

    def test_team_events(self) -> None:
        """Test team/workspace event types."""
        assert ActivityEventType.MEMBER_ADDED == "member_added"
        assert ActivityEventType.MEMBER_REMOVED == "member_removed"
        assert ActivityEventType.ROLE_CHANGED == "role_changed"
        assert ActivityEventType.WORKSPACE_CREATED == "workspace_created"
        assert ActivityEventType.WORKSPACE_UPDATED == "workspace_updated"
        assert ActivityEventType.WORKSPACE_DELETED == "workspace_deleted"


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


# ============================================================================
# NotificationType Enum Tests
# ============================================================================


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_review_notifications(self) -> None:
        """Test review-related notification types."""
        assert NotificationType.REVIEW_REQUEST == "review_request"
        assert NotificationType.REVIEW_APPROVED == "review_approved"
        assert NotificationType.REVIEW_REJECTED == "review_rejected"

    def test_other_notifications(self) -> None:
        """Test other notification types."""
        assert NotificationType.MENTION == "mention"
        assert NotificationType.WORKSPACE_UPDATE == "workspace_update"
        assert NotificationType.ROLE_CHANGED == "role_changed"
        assert NotificationType.TASK_ASSIGNED == "task_assigned"
        assert NotificationType.TASK_COMPLETED == "task_completed"


# ============================================================================
# User Model Tests
# ============================================================================


class TestUser:
    """Tests for User model."""

    def test_user_init_minimal(self) -> None:
        """Test User initialization with minimal fields."""
        user = User(id="user-001", username="alice")

        assert user.id == "user-001"
        assert user.username == "alice"
        assert user.email is None
        assert user.full_name is None
        assert user.metadata == {}
        assert isinstance(user.created_at, datetime)
        assert isinstance(user.updated_at, datetime)

    def test_user_init_full(self, sample_user_data: dict) -> None:
        """Test User initialization with all fields."""
        user = User(**sample_user_data)

        assert user.id == "user-001"
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert user.full_name == "Alice Johnson"

    def test_user_with_metadata(self) -> None:
        """Test User with metadata."""
        user = User(
            id="user-001",
            username="alice",
            metadata={"department": "Engineering", "location": "SF"},
        )

        assert user.metadata["department"] == "Engineering"
        assert user.metadata["location"] == "SF"

    def test_user_touch(self) -> None:
        """Test User.touch() updates timestamp."""
        user = User(id="user-001", username="alice")
        original_updated = user.updated_at

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)
        user.touch()

        assert user.updated_at > original_updated


# ============================================================================
# Team Model Tests
# ============================================================================


class TestTeam:
    """Tests for Team model."""

    def test_team_init_minimal(self) -> None:
        """Test Team initialization with minimal fields."""
        team = Team(id="team-001", name="Engineering")

        assert team.id == "team-001"
        assert team.name == "Engineering"
        assert team.description == ""
        assert team.member_ids == []
        assert team.metadata == {}
        assert isinstance(team.created_at, datetime)
        assert isinstance(team.updated_at, datetime)

    def test_team_init_full(self, sample_team_data: dict) -> None:
        """Test Team initialization with all fields."""
        team = Team(**sample_team_data)

        assert team.id == "team-001"
        assert team.name == "Engineering"
        assert team.description == "Core engineering team"
        assert team.member_ids == ["user-001", "user-002"]

    def test_team_add_member(self) -> None:
        """Test Team.add_member() adds a member."""
        team = Team(id="team-001", name="Engineering")

        team.add_member("user-001")

        assert "user-001" in team.member_ids

    def test_team_add_member_duplicate(self) -> None:
        """Test Team.add_member() doesn't add duplicates."""
        team = Team(id="team-001", name="Engineering", member_ids=["user-001"])
        original_updated = team.updated_at

        # Adding duplicate should not increase list size
        team.add_member("user-001")

        assert team.member_ids.count("user-001") == 1
        # Should not update timestamp for no-op
        assert team.updated_at == original_updated

    def test_team_remove_member(self) -> None:
        """Test Team.remove_member() removes a member."""
        team = Team(id="team-001", name="Engineering", member_ids=["user-001", "user-002"])

        result = team.remove_member("user-001")

        assert result is True
        assert "user-001" not in team.member_ids
        assert "user-002" in team.member_ids

    def test_team_remove_member_not_found(self) -> None:
        """Test Team.remove_member() returns False for non-member."""
        team = Team(id="team-001", name="Engineering", member_ids=["user-001"])
        original_updated = team.updated_at

        result = team.remove_member("user-999")

        assert result is False
        # Should not update timestamp for no-op
        assert team.updated_at == original_updated

    def test_team_has_member(self) -> None:
        """Test Team.has_member() checks membership."""
        team = Team(id="team-001", name="Engineering", member_ids=["user-001", "user-002"])

        assert team.has_member("user-001") is True
        assert team.has_member("user-003") is False

    def test_team_touch(self) -> None:
        """Test Team.touch() updates timestamp."""
        team = Team(id="team-001", name="Engineering")
        original_updated = team.updated_at

        import time

        time.sleep(0.01)
        team.touch()

        assert team.updated_at > original_updated

    def test_team_add_member_updates_timestamp(self) -> None:
        """Test Team.add_member() updates timestamp."""
        team = Team(id="team-001", name="Engineering")
        original_updated = team.updated_at

        import time

        time.sleep(0.01)
        team.add_member("user-001")

        assert team.updated_at > original_updated

    def test_team_remove_member_updates_timestamp(self) -> None:
        """Test Team.remove_member() updates timestamp."""
        team = Team(id="team-001", name="Engineering", member_ids=["user-001"])
        original_updated = team.updated_at

        import time

        time.sleep(0.01)
        team.remove_member("user-001")

        assert team.updated_at > original_updated


# ============================================================================
# Workspace Model Tests
# ============================================================================


class TestWorkspace:
    """Tests for Workspace model."""

    def test_workspace_init_minimal(self) -> None:
        """Test Workspace initialization with minimal fields."""
        workspace = Workspace(id="workspace-001", name="Project X", team_id="team-001")

        assert workspace.id == "workspace-001"
        assert workspace.name == "Project X"
        assert workspace.description == ""
        assert workspace.team_id == "team-001"
        assert workspace.settings == {}
        assert workspace.metadata == {}
        assert isinstance(workspace.created_at, datetime)
        assert isinstance(workspace.updated_at, datetime)

    def test_workspace_init_full(self, sample_workspace_data: dict) -> None:
        """Test Workspace initialization with all fields."""
        workspace = Workspace(**sample_workspace_data)

        assert workspace.id == "workspace-001"
        assert workspace.name == "Project X"
        assert workspace.description == "Main project workspace"
        assert workspace.team_id == "team-001"
        assert workspace.settings == {"visibility": "team"}

    def test_workspace_with_settings(self) -> None:
        """Test Workspace with complex settings."""
        settings = {
            "visibility": "team",
            "allow_public_specs": False,
            "default_role": "member",
            "notification_level": "all",
        }
        workspace = Workspace(
            id="workspace-001", name="Project X", team_id="team-001", settings=settings
        )

        assert workspace.settings["visibility"] == "team"
        assert workspace.settings["allow_public_specs"] is False
        assert workspace.settings["default_role"] == "member"

    def test_workspace_touch(self) -> None:
        """Test Workspace.touch() updates timestamp."""
        workspace = Workspace(id="workspace-001", name="Project X", team_id="team-001")
        original_updated = workspace.updated_at

        import time

        time.sleep(0.01)
        workspace.touch()

        assert workspace.updated_at > original_updated


# ============================================================================
# Role Model Tests
# ============================================================================


class TestRole:
    """Tests for Role model."""

    def test_role_init_team(self) -> None:
        """Test Role initialization for team-level role."""
        role = Role(user_id="user-001", role_type=RoleType.ADMIN, team_id="team-001")

        assert role.user_id == "user-001"
        assert role.role_type == RoleType.ADMIN
        assert role.team_id == "team-001"
        assert role.workspace_id is None
        assert role.granted_by is None
        assert isinstance(role.granted_at, datetime)
        assert role.expires_at is None

    def test_role_init_workspace(self) -> None:
        """Test Role initialization for workspace-level role."""
        role = Role(
            user_id="user-001",
            role_type=RoleType.MEMBER,
            workspace_id="workspace-001",
        )

        assert role.workspace_id == "workspace-001"
        assert role.team_id is None

    def test_role_init_full(self, sample_role_data: dict) -> None:
        """Test Role initialization with all fields."""
        role = Role(**sample_role_data)

        assert role.user_id == "user-001"
        assert role.role_type == RoleType.ADMIN
        assert role.team_id == "team-001"
        assert role.granted_by == "user-002"

    def test_role_with_expiration(self) -> None:
        """Test Role with expiration date."""
        expires = datetime.utcnow() + timedelta(days=30)
        role = Role(
            user_id="user-001",
            role_type=RoleType.REVIEWER,
            team_id="team-001",
            expires_at=expires,
        )

        assert role.expires_at == expires

    def test_role_is_expired_false(self) -> None:
        """Test Role.is_expired() returns False for non-expired role."""
        expires = datetime.utcnow() + timedelta(days=30)
        role = Role(
            user_id="user-001",
            role_type=RoleType.ADMIN,
            team_id="team-001",
            expires_at=expires,
        )

        assert role.is_expired() is False

    def test_role_is_expired_true(self) -> None:
        """Test Role.is_expired() returns True for expired role."""
        expired = datetime.utcnow() - timedelta(days=1)
        role = Role(
            user_id="user-001",
            role_type=RoleType.ADMIN,
            team_id="team-001",
            expires_at=expired,
        )

        assert role.is_expired() is True

    def test_role_is_expired_none(self) -> None:
        """Test Role.is_expired() returns False when no expiration."""
        role = Role(user_id="user-001", role_type=RoleType.ADMIN, team_id="team-001")

        assert role.is_expired() is False

    def test_role_with_metadata(self) -> None:
        """Test Role with metadata."""
        role = Role(
            user_id="user-001",
            role_type=RoleType.ADMIN,
            team_id="team-001",
            metadata={"reason": "project lead", "approved_by": "manager"},
        )

        assert role.metadata["reason"] == "project lead"
        assert role.metadata["approved_by"] == "manager"


# ============================================================================
# ActivityEvent Model Tests
# ============================================================================


class TestActivityEvent:
    """Tests for ActivityEvent model."""

    def test_activity_event_init_minimal(self) -> None:
        """Test ActivityEvent initialization with minimal fields."""
        event = ActivityEvent(
            id="event-001",
            event_type=ActivityEventType.TASK_CREATED,
            user_id="user-001",
        )

        assert event.id == "event-001"
        assert event.event_type == ActivityEventType.TASK_CREATED
        assert event.user_id == "user-001"
        assert event.workspace_id is None
        assert event.team_id is None
        assert event.entity_type is None
        assert event.entity_id is None
        assert event.description == ""
        assert event.metadata == {}
        assert isinstance(event.created_at, datetime)

    def test_activity_event_init_full(self, sample_activity_data: dict) -> None:
        """Test ActivityEvent initialization with all fields."""
        event = ActivityEvent(**sample_activity_data)

        assert event.id == "event-001"
        assert event.event_type == ActivityEventType.TASK_CREATED
        assert event.user_id == "user-001"
        assert event.workspace_id == "workspace-001"
        assert event.team_id == "team-001"
        assert event.entity_type == "task"
        assert event.entity_id == "task-001"
        assert event.description == "Created new task for feature X"

    def test_activity_event_with_metadata(self) -> None:
        """Test ActivityEvent with metadata."""
        event = ActivityEvent(
            id="event-001",
            event_type=ActivityEventType.TASK_COMPLETED,
            user_id="user-001",
            metadata={
                "duration_seconds": 120,
                "agent_used": "claude-code",
                "success": True,
            },
        )

        assert event.metadata["duration_seconds"] == 120
        assert event.metadata["agent_used"] == "claude-code"
        assert event.metadata["success"] is True

    def test_activity_event_all_event_types(self) -> None:
        """Test ActivityEvent works with all event types."""
        event_types = [
            ActivityEventType.TASK_CREATED,
            ActivityEventType.TASK_UPDATED,
            ActivityEventType.TASK_DELETED,
            ActivityEventType.SPEC_CREATED,
            ActivityEventType.REVIEW_REQUESTED,
            ActivityEventType.MEMBER_ADDED,
            ActivityEventType.WORKSPACE_CREATED,
        ]

        for event_type in event_types:
            event = ActivityEvent(
                id=f"event-{event_type}", event_type=event_type, user_id="user-001"
            )
            assert event.event_type == event_type


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
            title="Review Request",
            message="Please review this task",
        )

        assert notification.id == "notif-001"
        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_REQUEST
        assert notification.title == "Review Request"
        assert notification.message == "Please review this task"
        assert notification.workspace_id is None
        assert notification.team_id is None
        assert notification.status == NotificationStatus.PENDING
        assert notification.read_at is None
        assert notification.expires_at is None
        assert notification.metadata == {}
        assert isinstance(notification.created_at, datetime)

    def test_notification_init_full(self, sample_notification_data: dict) -> None:
        """Test Notification initialization with all fields."""
        notification = Notification(**sample_notification_data)

        assert notification.id == "notif-001"
        assert notification.user_id == "user-001"
        assert notification.notification_type == NotificationType.REVIEW_REQUEST
        assert notification.title == "Review Requested"
        assert notification.message == "Please review task-001"
        assert notification.workspace_id == "workspace-001"
        assert notification.team_id == "team-001"

    def test_notification_mark_as_read(self) -> None:
        """Test Notification.mark_as_read() updates status and timestamp."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review",
            message="Please review",
        )

        assert notification.status == NotificationStatus.PENDING
        assert notification.read_at is None

        notification.mark_as_read()

        assert notification.status == NotificationStatus.READ
        assert isinstance(notification.read_at, datetime)

    def test_notification_is_expired_false(self) -> None:
        """Test Notification.is_expired() returns False for non-expired."""
        expires = datetime.utcnow() + timedelta(hours=24)
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention",
            message="You were mentioned",
            expires_at=expires,
        )

        assert notification.is_expired() is False

    def test_notification_is_expired_true(self) -> None:
        """Test Notification.is_expired() returns True for expired."""
        expired = datetime.utcnow() - timedelta(hours=1)
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention",
            message="You were mentioned",
            expires_at=expired,
        )

        assert notification.is_expired() is True

    def test_notification_is_expired_none(self) -> None:
        """Test Notification.is_expired() returns False when no expiration."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention",
            message="You were mentioned",
        )

        assert notification.is_expired() is False

    def test_notification_with_custom_status(self) -> None:
        """Test Notification with custom status."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.TASK_COMPLETED,
            title="Task Completed",
            message="Your task is done",
            status=NotificationStatus.DELIVERED,
        )

        assert notification.status == NotificationStatus.DELIVERED

    def test_notification_with_metadata(self) -> None:
        """Test Notification with metadata."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review",
            message="Please review",
            metadata={
                "task_id": "task-001",
                "priority": "high",
                "deadline": "2024-12-31",
            },
        )

        assert notification.metadata["task_id"] == "task-001"
        assert notification.metadata["priority"] == "high"
        assert notification.metadata["deadline"] == "2024-12-31"

    def test_notification_all_types(self) -> None:
        """Test Notification works with all notification types."""
        notification_types = [
            NotificationType.REVIEW_REQUEST,
            NotificationType.REVIEW_APPROVED,
            NotificationType.REVIEW_REJECTED,
            NotificationType.MENTION,
            NotificationType.WORKSPACE_UPDATE,
            NotificationType.ROLE_CHANGED,
            NotificationType.TASK_ASSIGNED,
            NotificationType.TASK_COMPLETED,
        ]

        for notif_type in notification_types:
            notification = Notification(
                id=f"notif-{notif_type}",
                user_id="user-001",
                notification_type=notif_type,
                title="Test",
                message="Test message",
            )
            assert notification.notification_type == notif_type


# ============================================================================
# Integration Tests
# ============================================================================


class TestModelIntegration:
    """Integration tests for collaboration models working together."""

    def test_user_team_workspace_relationship(self) -> None:
        """Test User, Team, and Workspace relationship."""
        # Create users
        user1 = User(id="user-001", username="alice", email="alice@example.com")
        user2 = User(id="user-002", username="bob", email="bob@example.com")

        # Create team
        team = Team(id="team-001", name="Engineering")
        team.add_member(user1.id)
        team.add_member(user2.id)

        # Create workspace
        workspace = Workspace(id="workspace-001", name="Project X", team_id=team.id)

        # Verify relationships
        assert team.has_member(user1.id) is True
        assert team.has_member(user2.id) is True
        assert workspace.team_id == team.id

    def test_role_assignment_workflow(self) -> None:
        """Test role assignment workflow."""
        user = User(id="user-001", username="alice")
        team = Team(id="team-001", name="Engineering")
        team.add_member(user.id)

        # Assign admin role
        role = Role(
            user_id=user.id,
            role_type=RoleType.ADMIN,
            team_id=team.id,
            granted_by="system",
        )

        assert role.user_id == user.id
        assert role.team_id == team.id
        assert role.is_expired() is False

    def test_activity_tracking_workflow(self) -> None:
        """Test activity event tracking."""
        user = User(id="user-001", username="alice")
        workspace = Workspace(id="workspace-001", name="Project X", team_id="team-001")

        # Track task creation
        event = ActivityEvent(
            id="event-001",
            event_type=ActivityEventType.TASK_CREATED,
            user_id=user.id,
            workspace_id=workspace.id,
            entity_type="task",
            entity_id="task-001",
            description=f"{user.username} created a new task",
        )

        assert event.user_id == user.id
        assert event.workspace_id == workspace.id
        assert event.event_type == ActivityEventType.TASK_CREATED

    def test_notification_workflow(self) -> None:
        """Test notification creation and reading."""
        user = User(id="user-001", username="alice")

        # Create notification
        notification = Notification(
            id="notif-001",
            user_id=user.id,
            notification_type=NotificationType.REVIEW_REQUEST,
            title="Review Requested",
            message="Please review task-001",
        )

        assert notification.status == NotificationStatus.PENDING
        assert notification.is_expired() is False

        # Mark as read
        notification.mark_as_read()

        assert notification.status == NotificationStatus.READ
        assert notification.read_at is not None


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_user_with_empty_username(self) -> None:
        """Test User with empty username (should work with Pydantic)."""
        user = User(id="user-001", username="")
        assert user.username == ""

    def test_team_with_many_members(self) -> None:
        """Test Team with many members."""
        member_ids = [f"user-{i:03d}" for i in range(100)]
        team = Team(id="team-001", name="Large Team", member_ids=member_ids)

        assert len(team.member_ids) == 100
        assert team.has_member("user-050") is True

    def test_workspace_with_complex_settings(self) -> None:
        """Test Workspace with complex nested settings."""
        settings = {
            "permissions": {
                "members": ["read", "write"],
                "guests": ["read"],
            },
            "notifications": {
                "enabled": True,
                "types": ["all"],
            },
        }
        workspace = Workspace(
            id="workspace-001", name="Project X", team_id="team-001", settings=settings
        )

        assert workspace.settings["permissions"]["members"] == ["read", "write"]

    def test_role_temporary_assignment(self) -> None:
        """Test temporary role assignment with expiration."""
        # Create role that expires in 1 hour
        expires = datetime.utcnow() + timedelta(hours=1)
        role = Role(
            user_id="user-001",
            role_type=RoleType.REVIEWER,
            team_id="team-001",
            expires_at=expires,
        )

        assert role.is_expired() is False

        # Simulate time passing (in real test, would use mocking)
        # For now, just verify the method exists and works with None
        role_no_expiration = Role(
            user_id="user-001", role_type=RoleType.MEMBER, team_id="team-001"
        )
        assert role_no_expiration.is_expired() is False

    def test_notification_mark_as_read_idempotent(self) -> None:
        """Test marking notification as read multiple times."""
        notification = Notification(
            id="notif-001",
            user_id="user-001",
            notification_type=NotificationType.MENTION,
            title="Mention",
            message="You were mentioned",
        )

        original_read_at = None
        notification.mark_as_read()
        first_read_at = notification.read_at

        # Mark as read again
        notification.mark_as_read()
        second_read_at = notification.read_at

        # Should update timestamp on each call
        assert first_read_at is not None
        assert second_read_at is not None
        assert notification.status == NotificationStatus.READ

    def test_team_member_operations_case_sensitive(self) -> None:
        """Test team member operations are case-sensitive."""
        team = Team(id="team-001", name="Engineering")
        team.add_member("user-001")

        assert team.has_member("user-001") is True
        assert team.has_member("USER-001") is False
        assert team.has_member("User-001") is False

    def test_models_with_unicode(self) -> None:
        """Test models handle unicode characters correctly."""
        user = User(
            id="user-001", username="alice", full_name="Alice Müller", metadata={"emoji": "🎉"}
        )
        team = Team(id="team-001", name="Engineering", description="团队协作")

        assert "Müller" in user.full_name
        assert "团队" in team.description
        assert user.metadata["emoji"] == "🎉"

    def test_activity_event_various_entities(self) -> None:
        """Test ActivityEvent with various entity types."""
        entity_types = ["task", "spec", "review", "workspace", "team", "user"]

        for entity_type in entity_types:
            event = ActivityEvent(
                id=f"event-{entity_type}",
                event_type=ActivityEventType.TASK_UPDATED,
                user_id="user-001",
                entity_type=entity_type,
                entity_id=f"{entity_type}-001",
            )
            assert event.entity_type == entity_type
