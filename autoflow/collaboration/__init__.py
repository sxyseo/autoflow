"""
Autoflow Collaboration Module

Provides team collaboration features including shared workspaces, role-based
permissions, and collaborative review workflows. Enables multiple developers
to work with shared Autoflow state.

Usage:
    from autoflow.collaboration.models import User, Team, Workspace
    from autoflow.collaboration.permissions import PermissionManager
    from autoflow.collaboration.workspace import WorkspaceManager
    from autoflow.collaboration.activity import ActivityTracker

    # Create a user
    user = User(id="user-001", username="alice", email="alice@example.com")

    # Create a team
    team = Team(id="team-001", name="Engineering", description="Core engineering team")

    # Create a workspace
    manager = WorkspaceManager()
    workspace = manager.create_workspace(
        workspace_id="workspace-001",
        name="Project X",
        team_id="team-001"
    )

    # Track activity
    tracker = ActivityTracker(".autoflow")
    tracker.log_task_created(
        user_id="user-001",
        task_id="task-001",
        workspace_id="workspace-001",
        description="Created new task for bug fix"
    )
"""

from autoflow.collaboration.activity import ActivityTracker
from autoflow.collaboration.models import (
    ActivityEvent,
    Notification,
    NotificationStatus,
    Permission,
    Role,
    RoleType,
    Team,
    User,
    Workspace,
)
from autoflow.collaboration.workspace import WorkspaceManager

__all__ = [
    "User",
    "Team",
    "Workspace",
    "Role",
    "RoleType",
    "Permission",
    "ActivityEvent",
    "Notification",
    "NotificationStatus",
    "WorkspaceManager",
    "ActivityTracker",
]
