#!/usr/bin/env python3
"""
Autoflow Permission Manager Module

Provides role-based permission checking for team collaboration features.
Controls who can perform actions like dispatching tasks, reviewing code,
modifying specs, and managing team members.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from autoflow.collaboration.models import Permission, Role, RoleType


@dataclass
class PermissionConfig:
    """
    Configuration for permission checking.

    Args:
        default_allow: Whether to allow actions by default if no role found
        respect_expiry: Whether to check role expiration
        workspace_inheritance: Whether workspace roles inherit from team roles
        require_explicit: Whether to require explicit role assignments
    """
    default_allow: bool = False
    respect_expiry: bool = True
    workspace_inheritance: bool = True
    require_explicit: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "default_allow": self.default_allow,
            "respect_expiry": self.respect_expiry,
            "workspace_inheritance": self.workspace_inheritance,
            "require_explicit": self.require_explicit
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PermissionConfig':
        """Create config from dictionary."""
        return cls(
            default_allow=data.get("default_allow", False),
            respect_expiry=data.get("respect_expiry", True),
            workspace_inheritance=data.get("workspace_inheritance", True),
            require_explicit=data.get("require_explicit", False)
        )


class PermissionManager:
    """
    Role-based permission manager for team collaboration.

    Checks if users have permission to perform specific actions based on
    their roles within teams and workspaces. Supports role hierarchies,
    permission inheritance, and role expiration.
    """

    # Role permission mappings
    ROLE_PERMISSIONS: Dict[RoleType, Set[Permission]] = {
        RoleType.OWNER: {
            # All permissions
            Permission.DISPATCH_TASK,
            Permission.MODIFY_TASK,
            Permission.DELETE_TASK,
            Permission.CREATE_SPEC,
            Permission.MODIFY_SPEC,
            Permission.DELETE_SPEC,
            Permission.REQUEST_REVIEW,
            Permission.REVIEW_TASK,
            Permission.APPROVE_TASK,
            Permission.REJECT_TASK,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_SETTINGS,
            Permission.DELETE_WORKSPACE,
            Permission.VIEW_ACTIVITY,
            Permission.MANAGE_NOTIFICATIONS,
        },
        RoleType.ADMIN: {
            # Most permissions except deleting workspace
            Permission.DISPATCH_TASK,
            Permission.MODIFY_TASK,
            Permission.DELETE_TASK,
            Permission.CREATE_SPEC,
            Permission.MODIFY_SPEC,
            Permission.DELETE_SPEC,
            Permission.REQUEST_REVIEW,
            Permission.REVIEW_TASK,
            Permission.APPROVE_TASK,
            Permission.REJECT_TASK,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_SETTINGS,
            Permission.VIEW_ACTIVITY,
            Permission.MANAGE_NOTIFICATIONS,
        },
        RoleType.MEMBER: {
            # Basic participation permissions
            Permission.DISPATCH_TASK,
            Permission.MODIFY_TASK,
            Permission.CREATE_SPEC,
            Permission.MODIFY_SPEC,
            Permission.REQUEST_REVIEW,
            Permission.VIEW_ACTIVITY,
        },
        RoleType.REVIEWER: {
            # Review-specific permissions
            Permission.REVIEW_TASK,
            Permission.APPROVE_TASK,
            Permission.REJECT_TASK,
            Permission.VIEW_ACTIVITY,
        },
        RoleType.VIEWER: {
            # Read-only permissions
            Permission.VIEW_ACTIVITY,
        },
    }

    def __init__(
        self,
        config: Optional[PermissionConfig] = None
    ):
        """
        Initialize permission manager.

        Args:
            config: Permission manager configuration
        """
        self.config = config or PermissionConfig()

    def _get_user_roles(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> List[Role]:
        """
        Get user's roles in a specific context.

        Args:
            user_id: User ID to get roles for
            workspace_id: Workspace ID (optional)
            team_id: Team ID (optional)
            roles: List of all roles to search

        Returns:
            List of Role objects matching the criteria
        """
        if roles is None:
            return []

        matching_roles = []

        for role in roles:
            # Skip if user doesn't match
            if role.user_id != user_id:
                continue

            # Check if role matches the context
            if workspace_id and role.workspace_id == workspace_id:
                matching_roles.append(role)
            elif team_id and role.team_id == team_id:
                matching_roles.append(role)

        return matching_roles

    def _get_effective_role_type(
        self,
        user_roles: List[Role],
        workspace_id: Optional[str] = None
    ) -> Optional[RoleType]:
        """
        Get the effective role type for a user.

        Workspace-specific roles take precedence over team-level roles.
        If workspace inheritance is enabled, team roles are considered.

        Args:
            user_roles: List of user's roles
            workspace_id: Workspace ID for context

        Returns:
            Most relevant RoleType or None
        """
        if not user_roles:
            return None

        # Check for expired roles if configured
        if self.config.respect_expiry:
            user_roles = [r for r in user_roles if not r.is_expired()]

        if not user_roles:
            return None

        # Prioritize workspace-specific roles
        if workspace_id and self.config.workspace_inheritance:
            workspace_roles = [r for r in user_roles if r.workspace_id == workspace_id]
            if workspace_roles:
                # Return highest priority workspace role
                return self._highest_priority_role(workspace_roles)

        # Fall back to team-level roles
        team_roles = [r for r in user_roles if r.team_id and not r.workspace_id]
        if team_roles:
            return self._highest_priority_role(team_roles)

        # If no team/workspace specific roles, use first valid role
        return user_roles[0].role_type if user_roles else None

    def _highest_priority_role(self, roles: List[Role]) -> RoleType:
        """
        Get the highest priority role from a list of roles.

        Priority order: OWNER > ADMIN > MEMBER > REVIEWER > VIEWER

        Args:
            roles: List of roles to prioritize

        Returns:
            Highest priority RoleType
        """
        priority_order = [
            RoleType.OWNER,
            RoleType.ADMIN,
            RoleType.MEMBER,
            RoleType.REVIEWER,
            RoleType.VIEWER
        ]

        for role_type in priority_order:
            for role in roles:
                if role.role_type == role_type:
                    return role_type

        # Default to first role's type if no match
        return roles[0].role_type

    def has_permission(
        self,
        user_id: str,
        permission: Permission,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User ID to check
            permission: Permission to check for
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user has permission, False otherwise
        """
        # Get user's roles in context
        user_roles = self._get_user_roles(
            user_id=user_id,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

        # Get effective role type
        role_type = self._get_effective_role_type(
            user_roles=user_roles,
            workspace_id=workspace_id
        )

        # No role found
        if role_type is None:
            return self.config.default_allow

        # Check if role has permission
        role_permissions = self.ROLE_PERMISSIONS.get(role_type, set())
        return permission in role_permissions

    def can_dispatch(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can dispatch tasks.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can dispatch tasks, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.DISPATCH_TASK,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def can_review(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can review tasks.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can review tasks, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.REVIEW_TASK,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def can_modify_spec(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can modify specs.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can modify specs, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.MODIFY_SPEC,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def can_approve(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can approve tasks.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can approve tasks, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.APPROVE_TASK,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def can_manage_members(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can manage team/workspace members.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can manage members, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.MANAGE_MEMBERS,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def can_delete_workspace(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> bool:
        """
        Check if user can delete workspace.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            True if user can delete workspace, False otherwise
        """
        return self.has_permission(
            user_id=user_id,
            permission=Permission.DELETE_WORKSPACE,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

    def get_user_permissions(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> Set[Permission]:
        """
        Get all permissions for a user in a specific context.

        Args:
            user_id: User ID to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            Set of Permission objects the user has
        """
        # Get user's roles in context
        user_roles = self._get_user_roles(
            user_id=user_id,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

        # Get effective role type
        role_type = self._get_effective_role_type(
            user_roles=user_roles,
            workspace_id=workspace_id
        )

        # No role found
        if role_type is None:
            return set()

        # Return permissions for role
        return self.ROLE_PERMISSIONS.get(role_type, set()).copy()

    def check_permissions(
        self,
        user_id: str,
        required_permissions: List[Permission],
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        roles: Optional[List[Role]] = None
    ) -> tuple[bool, List[Permission]]:
        """
        Check if user has all required permissions.

        Args:
            user_id: User ID to check
            required_permissions: List of permissions to check
            workspace_id: Workspace ID for context
            team_id: Team ID for context
            roles: List of all roles to search

        Returns:
            Tuple of (has_all, missing_permissions)
        """
        user_permissions = self.get_user_permissions(
            user_id=user_id,
            workspace_id=workspace_id,
            team_id=team_id,
            roles=roles
        )

        missing = [
            perm for perm in required_permissions
            if perm not in user_permissions
        ]

        return len(missing) == 0, missing
