"""
Autoflow Collaboration Type Definitions Module

Provides TypedDict definitions for collaboration data structures used throughout
the Autoflow collaboration system. These types enable better IDE support, static
analysis, and type safety while working with JSON metadata for activities and
notifications.

Usage:
    from autoflow.collaboration.types import (
        ActivityMetadata,
        NotificationMetadata,
        TaskActivityMetadata,
        ReviewActivityMetadata,
        ReviewNotificationMetadata,
    )

    # Type checking works
    activity_meta: TaskActivityMetadata = {
        "task_id": "task-001",
        "task_title": "Fix bug",
        "changes": ["description", "status"]
    }

    # JSON loading with type safety
    notification_meta: ReviewNotificationMetadata = load_json("notification_metadata.json")
"""

from __future__ import annotations

from typing import Any, TypedDict


# === Activity Metadata Types ===


class TaskActivityMetadata(TypedDict, total=False):
    """
    Metadata for task-related activity events.

    Used in ActivityEvent.metadata for tracking task changes,
    assignments, and completion events.
    """

    task_id: str
    task_title: str
    old_status: str
    new_status: str
    assigned_to: str
    assigned_by: str
    changes: list[str]
    priority: str
    slice_size: str


class SpecActivityMetadata(TypedDict, total=False):
    """
    Metadata for spec-related activity events.

    Used in ActivityEvent.metadata for tracking spec creation,
    updates, and deletion events.
    """

    spec_id: str
    spec_slug: str
    spec_title: str
    change_summary: str
    artifacts_changed: list[str]


class ReviewActivityMetadata(TypedDict, total=False):
    """
    Metadata for review-related activity events.

    Used in ActivityEvent.metadata for tracking review requests,
    submissions, approvals, and rejections.
    """

    review_id: str
    task_id: str
    task_title: str
    reviewer_id: str
    requester_id: str
    review_result: str  # "approved", "rejected", "needs_changes"
    findings_count: int
    changes_requested: int


class MemberActivityMetadata(TypedDict, total=False):
    """
    Metadata for team member activity events.

    Used in ActivityEvent.metadata for tracking member additions,
    removals, and role changes.
    """

    member_id: str
    member_name: str
    added_by: str
    removed_by: str
    old_role: str
    new_role: str
    team_id: str
    team_name: str


class WorkspaceActivityMetadata(TypedDict, total=False):
    """
    Metadata for workspace activity events.

    Used in ActivityEvent.metadata for tracking workspace creation,
    updates, and deletion events.
    """

    workspace_id: str
    workspace_name: str
    update_type: str  # "settings_changed", "member_added", etc.
    changes: list[str]
    created_by: str


class ActivityMetadata(TypedDict, total=False):
    """
    Generic activity metadata dictionary.

    Provides a flexible structure for activity event metadata that can
    include specific metadata types or custom fields.
    """

    # Common fields
    entity_id: str
    entity_title: str
    action: str
    reason: str

    # Type-specific fields (union of all metadata types)
    task_id: str
    task_title: str
    spec_id: str
    spec_slug: str
    reviewer_id: str
    requester_id: str
    member_id: str
    workspace_id: str
    workspace_name: str

    # Additional context
    changes: list[str]
    custom_fields: dict[str, Any]


# === Notification Metadata Types ===


class ReviewNotificationMetadata(TypedDict, total=False):
    """
    Metadata for review-related notifications.

    Used in Notification.metadata for review requests, approvals,
    and rejections.
    """

    task_id: str
    task_title: str
    reviewer_id: str
    requester_id: str
    review_id: str
    reason: str  # For rejection notifications
    findings_count: int


class MentionNotificationMetadata(TypedDict, total=False):
    """
    Metadata for mention notifications.

    Used in Notification.metadata when users are mentioned in
    comments, tasks, or specs.
    """

    mentioned_by: str
    entity_type: str  # "comment", "task", "spec", etc.
    entity_id: str
    entity_title: str
    content: str  # Full content where mention occurred
    context_url: str  # Link to the mention context


class WorkspaceNotificationMetadata(TypedDict, total=False):
    """
    Metadata for workspace update notifications.

    Used in Notification.metadata for workspace changes.
    """

    workspace_name: str
    update_type: str  # "settings_changed", "member_added", "archived", etc.
    changed_by: str
    settings_changed: list[str]


class RoleChangeNotificationMetadata(TypedDict, total=False):
    """
    Metadata for role change notifications.

    Used in Notification.metadata when user roles are changed.
    """

    changed_by: str
    new_role: str
    old_role: str
    context: str  # Description of where role was changed
    team_id: str
    workspace_id: str


class TaskAssignmentNotificationMetadata(TypedDict, total=False):
    """
    Metadata for task assignment notifications.

    Used in Notification.metadata for task assignments and completions.
    """

    assigned_by: str
    completed_by: str
    task_id: str
    task_title: str
    priority: str
    due_date: str  # ISO timestamp


class NotificationMetadata(TypedDict, total=False):
    """
    Generic notification metadata dictionary.

    Provides a flexible structure for notification metadata that can
    include specific notification types or custom fields.
    """

    # Common fields
    entity_id: str
    entity_title: str
    entity_type: str
    action: str
    reason: str

    # Actor information
    actor_id: str
    actor_name: str

    # Type-specific fields (union of all metadata types)
    task_id: str
    task_title: str
    reviewer_id: str
    requester_id: str
    mentioned_by: str
    workspace_name: str
    new_role: str
    old_role: str

    # Additional context
    changes: list[str]
    findings_count: int
    custom_fields: dict[str, Any]


# === Type Aliases for Common Patterns ===


# Activity event types
ActivityEventType = str  # Literal["task_created", "task_updated", "review_approved", ...]

# Notification types
NotificationType = str  # Literal["review_request", "review_approved", "mention", ...]

# Notification status
NotificationStatus = str  # Literal["pending", "sent", "delivered", "read", "dismissed", "failed"]

# User/Team identifiers
UserId = str
TeamId = str
WorkspaceId = str

# Role identifiers
RoleId = str
RoleType = str  # Literal["owner", "admin", "member", "reviewer", "viewer"]

# Timestamp in ISO 8601 format
Timestamp = str
