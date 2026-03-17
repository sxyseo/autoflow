"""
Collaboration Data Models

Defines Pydantic models for team collaboration features including users, teams,
workspaces, roles, permissions, activity tracking, and notifications.

These models provide the foundation for team-oriented features in Autoflow,
enabling shared workspaces, role-based access control, and collaborative workflows.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """
    Represents a user in the collaboration system.

    A user can be a member of multiple teams and workspaces, with different roles
    and permissions in each context.

    Attributes:
        id: Unique user identifier
        username: User's display name or handle
        email: User's email address (optional)
        full_name: User's full name (optional)
        created_at: Timestamp when user was created
        updated_at: Timestamp when user was last updated
        metadata: Additional user data

    Example:
        >>> user = User(id="user-001", username="alice", email="alice@example.com")
        >>> print(user.username)
        alice
    """

    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class Team(BaseModel):
    """
    Represents a team in the collaboration system.

    A team is a group of users who collaborate on shared workspaces and tasks.
    Teams can have multiple members with different roles.

    Attributes:
        id: Unique team identifier
        name: Team name
        description: Team description (optional)
        member_ids: List of user IDs who are members of this team
        created_at: Timestamp when team was created
        updated_at: Timestamp when team was last updated
        metadata: Additional team data

    Example:
        >>> team = Team(
        ...     id="team-001",
        ...     name="Engineering",
        ...     description="Core engineering team",
        ...     member_ids=["user-001", "user-002"]
        ... )
        >>> print(team.name)
        Engineering
    """

    id: str
    name: str
    description: str = ""
    member_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_member(self, user_id: str) -> None:
        """
        Add a member to the team.

        Args:
            user_id: User ID to add as a member
        """
        if user_id not in self.member_ids:
            self.member_ids.append(user_id)
            self.touch()

    def remove_member(self, user_id: str) -> bool:
        """
        Remove a member from the team.

        Args:
            user_id: User ID to remove

        Returns:
            True if member was removed, False if not found
        """
        if user_id in self.member_ids:
            self.member_ids.remove(user_id)
            self.touch()
            return True
        return False

    def has_member(self, user_id: str) -> bool:
        """
        Check if a user is a member of the team.

        Args:
            user_id: User ID to check

        Returns:
            True if user is a member, False otherwise
        """
        return user_id in self.member_ids

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class Workspace(BaseModel):
    """
    Represents a shared workspace for team collaboration.

    A workspace is a shared environment where team members can collaborate on
    specs, tasks, and runs. Workspaces are associated with a team and have
    their own access control settings.

    Attributes:
        id: Unique workspace identifier
        name: Workspace name
        description: Workspace description
        team_id: Team ID that owns this workspace
        settings: Workspace configuration settings
        created_at: Timestamp when workspace was created
        updated_at: Timestamp when workspace was last updated
        metadata: Additional workspace data

    Example:
        >>> workspace = Workspace(
        ...     id="workspace-001",
        ...     name="Project X",
        ...     team_id="team-001"
        ... )
        >>> print(workspace.name)
        Project X
    """

    id: str
    name: str
    description: str = ""
    team_id: str
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class RoleType(str, Enum):
    """Role types for users in teams/workspaces."""

    OWNER = "owner"  # Full control, can manage members and settings
    ADMIN = "admin"  # Can manage most settings and members
    MEMBER = "member"  # Can participate but not manage
    REVIEWER = "reviewer"  # Can review and approve
    VIEWER = "viewer"  # Read-only access


class Role(BaseModel):
    """
    Represents a user's role within a team or workspace.

    Roles determine what actions a user can perform within a specific context.
    A user can have different roles in different teams/workspaces.

    Attributes:
        user_id: User ID for this role assignment
        role_type: Type of role (owner, admin, member, reviewer, viewer)
        team_id: Team ID (optional, for team-level roles)
        workspace_id: Workspace ID (optional, for workspace-level roles)
        granted_by: User ID who granted this role (optional)
        granted_at: Timestamp when role was granted
        expires_at: Optional expiration timestamp
        metadata: Additional role data

    Example:
        >>> role = Role(
        ...     user_id="user-001",
        ...     role_type=RoleType.ADMIN,
        ...     team_id="team-001"
        ... )
        >>> print(role.role_type)
        admin
    """

    user_id: str
    role_type: RoleType
    team_id: Optional[str] = None
    workspace_id: Optional[str] = None
    granted_by: Optional[str] = None
    granted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        """
        Check if this role assignment has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class Permission(str, Enum):
    """Specific permissions that can be granted to users."""

    # Task permissions
    DISPATCH_TASK = "dispatch_task"
    MODIFY_TASK = "modify_task"
    DELETE_TASK = "delete_task"

    # Spec permissions
    CREATE_SPEC = "create_spec"
    MODIFY_SPEC = "modify_spec"
    DELETE_SPEC = "delete_spec"

    # Review permissions
    REQUEST_REVIEW = "request_review"
    REVIEW_TASK = "review_task"
    APPROVE_TASK = "approve_task"
    REJECT_TASK = "reject_task"

    # Team/Workspace permissions
    MANAGE_MEMBERS = "manage_members"
    MANAGE_SETTINGS = "manage_settings"
    DELETE_WORKSPACE = "delete_workspace"

    # General permissions
    VIEW_ACTIVITY = "view_activity"
    MANAGE_NOTIFICATIONS = "manage_notifications"


class ActivityEventType(str, Enum):
    """Types of activity events that can be tracked."""

    # Task events
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_DELETED = "task_deleted"
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Spec events
    SPEC_CREATED = "spec_created"
    SPEC_UPDATED = "spec_updated"
    SPEC_DELETED = "spec_deleted"

    # Review events
    REVIEW_REQUESTED = "review_requested"
    REVIEW_SUBMITTED = "review_submitted"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"

    # Team/Workspace events
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    ROLE_CHANGED = "role_changed"
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_UPDATED = "workspace_updated"
    WORKSPACE_DELETED = "workspace_deleted"


class ActivityEvent(BaseModel):
    """
    Represents an activity event in the collaboration system.

    Activity events track all important actions performed by team members,
    providing an audit trail and activity feed.

    Attributes:
        id: Unique event identifier
        event_type: Type of event that occurred
        user_id: User ID who performed the action
        workspace_id: Workspace ID where the action occurred
        team_id: Team ID associated with the action
        entity_type: Type of entity affected (task, spec, review, etc.)
        entity_id: ID of the entity affected
        description: Human-readable description of the event
        metadata: Additional event data
        created_at: Timestamp when the event occurred

    Example:
        >>> event = ActivityEvent(
        ...     id="event-001",
        ...     event_type=ActivityEventType.TASK_CREATED,
        ...     user_id="user-001",
        ...     workspace_id="workspace-001",
        ...     entity_type="task",
        ...     entity_id="task-001",
        ...     description="Created new task"
        ... )
        >>> print(event.event_type)
        task_created
    """

    id: str
    event_type: ActivityEventType
    user_id: str
    workspace_id: Optional[str] = None
    team_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NotificationStatus(str, Enum):
    """Status of a notification."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    DISMISSED = "dismissed"
    FAILED = "failed"


class NotificationType(str, Enum):
    """Types of notifications that can be sent."""

    REVIEW_REQUEST = "review_request"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    MENTION = "mention"
    WORKSPACE_UPDATE = "workspace_update"
    ROLE_CHANGED = "role_changed"
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"


class Notification(BaseModel):
    """
    Represents a notification to a user.

    Notifications alert team members about relevant events such as review
    requests, mentions, and workspace updates.

    Attributes:
        id: Unique notification identifier
        user_id: User ID to notify
        notification_type: Type of notification
        title: Notification title
        message: Notification message
        workspace_id: Workspace ID associated with notification
        team_id: Team ID associated with notification
        status: Notification status
        created_at: Timestamp when notification was created
        read_at: Timestamp when notification was read (optional)
        expires_at: Optional expiration timestamp
        metadata: Additional notification data

    Example:
        >>> notification = Notification(
        ...     id="notif-001",
        ...     user_id="user-001",
        ...     notification_type=NotificationType.REVIEW_REQUEST,
        ...     title="Review Requested",
        ...     message="Please review task-001"
        ... )
        >>> print(notification.title)
        Review Requested
    """

    id: str
    user_id: str
    notification_type: NotificationType
    title: str
    message: str
    workspace_id: Optional[str] = None
    team_id: Optional[str] = None
    status: NotificationStatus = NotificationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_as_read(self) -> None:
        """Mark the notification as read."""
        self.status = NotificationStatus.READ
        self.read_at = datetime.utcnow()

    def is_expired(self) -> bool:
        """
        Check if this notification has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class PresenceStatus(str, Enum):
    """Presence status for users in real-time collaboration."""

    ONLINE = "online"  # User is actively online
    AWAY = "away"  # User is away from keyboard
    BUSY = "busy"  # User is busy and should not be disturbed
    OFFLINE = "offline"  # User is offline


class UserPresence(BaseModel):
    """
    Represents a user's real-time presence information.

    UserPresence tracks the online status and activity of users within
    workspaces, enabling real-time collaboration features like showing
    who is currently active, away, or busy.

    Attributes:
        user_id: User ID for this presence record
        status: Current presence status (online, away, busy, offline)
        workspace_id: Workspace ID where the user is present (optional)
        team_id: Team ID associated with the user (optional)
        last_seen: Timestamp when the user was last active
        status_message: Custom status message (optional)
        metadata: Additional presence data

    Example:
        >>> presence = UserPresence(
        ...     user_id="user-001",
        ...     status=PresenceStatus.ONLINE,
        ...     workspace_id="workspace-001",
        ...     last_seen=datetime.utcnow()
        ... )
        >>> print(presence.status)
        online
    """

    user_id: str
    status: PresenceStatus = PresenceStatus.OFFLINE
    workspace_id: Optional[str] = None
    team_id: Optional[str] = None
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    status_message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def update_status(self, status: PresenceStatus) -> None:
        """
        Update the user's presence status.

        Args:
            status: New presence status
        """
        self.status = status
        self.last_seen = datetime.utcnow()

    def set_online(self, workspace_id: Optional[str] = None) -> None:
        """
        Set the user's status to online.

        Args:
            workspace_id: Optional workspace ID where user is active
        """
        self.status = PresenceStatus.ONLINE
        self.last_seen = datetime.utcnow()
        if workspace_id:
            self.workspace_id = workspace_id

    def set_away(self) -> None:
        """Set the user's status to away."""
        self.status = PresenceStatus.AWAY
        self.last_seen = datetime.utcnow()

    def set_busy(self) -> None:
        """Set the user's status to busy."""
        self.status = PresenceStatus.BUSY
        self.last_seen = datetime.utcnow()

    def set_offline(self) -> None:
        """Set the user's status to offline."""
        self.status = PresenceStatus.OFFLINE
        self.last_seen = datetime.utcnow()

    def is_online(self) -> bool:
        """
        Check if the user is currently online.

        Returns:
            True if user is online, False otherwise
        """
        return self.status == PresenceStatus.ONLINE

    def is_active(self, timeout_seconds: int = 300) -> bool:
        """
        Check if the user was recently active.

        Args:
            timeout_seconds: Seconds of inactivity before considering user inactive

        Returns:
            True if user was active within timeout, False otherwise
        """
        if self.status == PresenceStatus.OFFLINE:
            return False
        time_since_last_seen = datetime.utcnow() - self.last_seen
        return time_since_last_seen.total_seconds() <= timeout_seconds
