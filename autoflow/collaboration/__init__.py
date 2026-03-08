"""
Autoflow Collaboration Module

Provides team collaboration features including shared workspaces, role-based
permissions, and collaborative review workflows. Enables multiple developers
to work with shared Autoflow state.

Usage:
    from autoflow.collaboration.models import User, Team, Workspace
    from autoflow.collaboration.permissions import PermissionManager
    from autoflow.collaboration.workspace import WorkspaceManager

    # Create a user
    user = User(id="user-001", username="alice", email="alice@example.com")

    # Create a team
    team = Team(id="team-001", name="Engineering", description="Core engineering team")
"""

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
]
