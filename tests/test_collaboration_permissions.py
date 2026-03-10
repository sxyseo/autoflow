"""
Unit Tests for Collaboration Permission System

Tests the PermissionManager and PermissionConfig classes for role-based
access control in team collaboration features.

These tests ensure permission checking works correctly with role hierarchies,
workspace inheritance, role expiration, and permission lookup.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.collaboration.models import Permission, Role, RoleType
from autoflow.collaboration.permissions import (
    PermissionConfig,
    PermissionManager,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def base_time() -> datetime:
    """Return a base time for testing."""
    return datetime(2024, 1, 1, 12, 0, 0)


@pytest.fixture
def sample_roles() -> list[Role]:
    """Return sample roles for testing."""
    return [
        # User 1: Owner at workspace level
        Role(
            user_id="user-001",
            role_type=RoleType.OWNER,
            workspace_id="workspace-001",
            team_id="team-001",
        ),
        # User 2: Admin at team level
        Role(
            user_id="user-002",
            role_type=RoleType.ADMIN,
            team_id="team-001",
        ),
        # User 3: Member at workspace level
        Role(
            user_id="user-003",
            role_type=RoleType.MEMBER,
            workspace_id="workspace-001",
        ),
        # User 4: Reviewer with expiration
        Role(
            user_id="user-004",
            role_type=RoleType.REVIEWER,
            team_id="team-001",
            expires_at=datetime.utcnow() + timedelta(days=30),
        ),
        # User 5: Viewer
        Role(
            user_id="user-005",
            role_type=RoleType.VIEWER,
            workspace_id="workspace-001",
        ),
        # User 6: Multiple roles (team + workspace)
        Role(
            user_id="user-006",
            role_type=RoleType.MEMBER,
            team_id="team-001",
        ),
        Role(
            user_id="user-006",
            role_type=RoleType.ADMIN,
            workspace_id="workspace-002",
        ),
        # User 7: Expired role
        Role(
            user_id="user-007",
            role_type=RoleType.ADMIN,
            team_id="team-001",
            expires_at=datetime.utcnow() - timedelta(days=1),
        ),
    ]


# ============================================================================
# PermissionConfig Tests
# ============================================================================


class TestPermissionConfig:
    """Tests for PermissionConfig dataclass."""

    def test_config_default_values(self) -> None:
        """Test PermissionConfig initialization with defaults."""
        config = PermissionConfig()

        assert config.default_allow is False
        assert config.respect_expiry is True
        assert config.workspace_inheritance is True
        assert config.require_explicit is False

    def test_config_custom_values(self) -> None:
        """Test PermissionConfig with custom values."""
        config = PermissionConfig(
            default_allow=True,
            respect_expiry=False,
            workspace_inheritance=False,
            require_explicit=True,
        )

        assert config.default_allow is True
        assert config.respect_expiry is False
        assert config.workspace_inheritance is False
        assert config.require_explicit is True

    def test_config_to_dict(self) -> None:
        """Test PermissionConfig.to_dict() conversion."""
        config = PermissionConfig(
            default_allow=True,
            respect_expiry=False,
            workspace_inheritance=True,
            require_explicit=False,
        )

        config_dict = config.to_dict()

        assert config_dict == {
            "default_allow": True,
            "respect_expiry": False,
            "workspace_inheritance": True,
            "require_explicit": False,
        }

    def test_config_from_dict(self) -> None:
        """Test PermissionConfig.from_dict() creation."""
        config_dict = {
            "default_allow": True,
            "respect_expiry": False,
            "workspace_inheritance": True,
            "require_explicit": False,
        }

        config = PermissionConfig.from_dict(config_dict)

        assert config.default_allow is True
        assert config.respect_expiry is False
        assert config.workspace_inheritance is True
        assert config.require_explicit is False

    def test_config_from_dict_defaults(self) -> None:
        """Test PermissionConfig.from_dict() with missing values."""
        config_dict = {"default_allow": True}

        config = PermissionConfig.from_dict(config_dict)

        assert config.default_allow is True
        assert config.respect_expiry is True  # default
        assert config.workspace_inheritance is True  # default
        assert config.require_explicit is False  # default

    def test_config_roundtrip(self) -> None:
        """Test PermissionConfig to_dict and from_dict roundtrip."""
        original = PermissionConfig(
            default_allow=True,
            respect_expiry=False,
            workspace_inheritance=True,
            require_explicit=False,
        )

        config_dict = original.to_dict()
        restored = PermissionConfig.from_dict(config_dict)

        assert restored.default_allow == original.default_allow
        assert restored.respect_expiry == original.respect_expiry
        assert restored.workspace_inheritance == original.workspace_inheritance
        assert restored.require_explicit == original.require_explicit


# ============================================================================
# PermissionManager Initialization Tests
# ============================================================================


class TestPermissionManagerInit:
    """Tests for PermissionManager initialization."""

    def test_manager_default_config(self) -> None:
        """Test PermissionManager with default config."""
        manager = PermissionManager()

        assert manager.config.default_allow is False
        assert manager.config.respect_expiry is True
        assert manager.config.workspace_inheritance is True

    def test_manager_custom_config(self) -> None:
        """Test PermissionManager with custom config."""
        config = PermissionConfig(default_allow=True, respect_expiry=False)
        manager = PermissionManager(config=config)

        assert manager.config.default_allow is True
        assert manager.config.respect_expiry is False

    def test_manager_role_permissions_constant(self) -> None:
        """Test that ROLE_PERMISSIONS is properly defined."""
        manager = PermissionManager()

        # Check OWNER has all permissions
        owner_perms = manager.ROLE_PERMISSIONS[RoleType.OWNER]
        assert Permission.DISPATCH_TASK in owner_perms
        assert Permission.DELETE_WORKSPACE in owner_perms
        assert Permission.VIEW_ACTIVITY in owner_perms

        # Check VIEWER has minimal permissions
        viewer_perms = manager.ROLE_PERMISSIONS[RoleType.VIEWER]
        assert Permission.VIEW_ACTIVITY in viewer_perms
        assert Permission.DISPATCH_TASK not in viewer_perms

        # Check ADMIN has most but not all permissions
        admin_perms = manager.ROLE_PERMISSIONS[RoleType.ADMIN]
        assert Permission.DISPATCH_TASK in admin_perms
        assert Permission.DELETE_WORKSPACE not in admin_perms


# ============================================================================
# User Role Retrieval Tests
# ============================================================================


class TestGetUserRoles:
    """Tests for PermissionManager._get_user_roles()."""

    def test_get_user_roles_by_workspace(self, sample_roles: list[Role]) -> None:
        """Test getting user roles filtered by workspace."""
        manager = PermissionManager()

        roles = manager._get_user_roles(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert len(roles) == 1
        assert roles[0].user_id == "user-001"
        assert roles[0].workspace_id == "workspace-001"

    def test_get_user_roles_by_team(self, sample_roles: list[Role]) -> None:
        """Test getting user roles filtered by team."""
        manager = PermissionManager()

        roles = manager._get_user_roles(
            user_id="user-002",
            team_id="team-001",
            roles=sample_roles,
        )

        assert len(roles) == 1
        assert roles[0].user_id == "user-002"
        assert roles[0].team_id == "team-001"

    def test_get_user_roles_multiple(self, sample_roles: list[Role]) -> None:
        """Test getting user with multiple roles."""
        manager = PermissionManager()

        roles = manager._get_user_roles(
            user_id="user-006",
            workspace_id="workspace-002",
            roles=sample_roles,
        )

        assert len(roles) == 1
        assert roles[0].role_type == RoleType.ADMIN

    def test_get_user_roles_no_match(self, sample_roles: list[Role]) -> None:
        """Test getting roles for user with no roles."""
        manager = PermissionManager()

        roles = manager._get_user_roles(
            user_id="user-999",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert len(roles) == 0

    def test_get_user_roles_none_list(self) -> None:
        """Test getting roles with None role list."""
        manager = PermissionManager()

        roles = manager._get_user_roles(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=None,
        )

        assert len(roles) == 0

    def test_get_user_roles_wrong_context(self, sample_roles: list[Role]) -> None:
        """Test getting roles in wrong context returns empty."""
        manager = PermissionManager()

        # user-001 has role in workspace-001, not workspace-999
        roles = manager._get_user_roles(
            user_id="user-001",
            workspace_id="workspace-999",
            roles=sample_roles,
        )

        assert len(roles) == 0


# ============================================================================
# Effective Role Type Tests
# ============================================================================


class TestGetEffectiveRoleType:
    """Tests for PermissionManager._get_effective_role_type()."""

    def test_effective_role_single(self, sample_roles: list[Role]) -> None:
        """Test effective role with single role."""
        manager = PermissionManager()

        user_roles = [r for r in sample_roles if r.user_id == "user-001"]
        role_type = manager._get_effective_role_type(
            user_roles=user_roles,
            workspace_id="workspace-001",
        )

        assert role_type == RoleType.OWNER

    def test_effective_role_workspace_priority(self, sample_roles: list[Role]) -> None:
        """Test workspace role takes priority over team role."""
        manager = PermissionManager()

        user_roles = [r for r in sample_roles if r.user_id == "user-006"]
        role_type = manager._get_effective_role_type(
            user_roles=user_roles,
            workspace_id="workspace-002",
        )

        # Workspace ADMIN role should take priority
        assert role_type == RoleType.ADMIN

    def test_effective_role_expired_filtered(self, sample_roles: list[Role]) -> None:
        """Test expired roles are filtered out."""
        manager = PermissionManager()

        user_roles = [r for r in sample_roles if r.user_id == "user-007"]
        role_type = manager._get_effective_role_type(
            user_roles=user_roles,
        )

        # User 007 has expired admin role, should return None
        assert role_type is None

    def test_effective_role_expiry_disabled(self, sample_roles: list[Role]) -> None:
        """Test expired roles are kept when expiry disabled."""
        config = PermissionConfig(respect_expiry=False)
        manager = PermissionManager(config=config)

        user_roles = [r for r in sample_roles if r.user_id == "user-007"]
        role_type = manager._get_effective_role_type(
            user_roles=user_roles,
        )

        # With expiry disabled, admin role should be valid
        assert role_type == RoleType.ADMIN

    def test_effective_role_no_roles(self) -> None:
        """Test effective role with empty role list."""
        manager = PermissionManager()

        role_type = manager._get_effective_role_type(
            user_roles=[],
        )

        assert role_type is None

    def test_effective_role_team_fallback(self, sample_roles: list[Role]) -> None:
        """Test team-level role when no workspace role."""
        manager = PermissionManager()

        user_roles = [r for r in sample_roles if r.user_id == "user-002"]
        role_type = manager._get_effective_role_type(
            user_roles=user_roles,
            workspace_id="workspace-001",
        )

        # User 002 has team-level admin role
        assert role_type == RoleType.ADMIN


# ============================================================================
# Highest Priority Role Tests
# ============================================================================


class TestHighestPriorityRole:
    """Tests for PermissionManager._highest_priority_role()."""

    def test_highest_priority_owner(self) -> None:
        """Test owner is highest priority."""
        manager = PermissionManager()

        roles = [
            Role(user_id="user-001", role_type=RoleType.MEMBER),
            Role(user_id="user-001", role_type=RoleType.OWNER),
            Role(user_id="user-001", role_type=RoleType.ADMIN),
        ]

        role_type = manager._highest_priority_role(roles)

        assert role_type == RoleType.OWNER

    def test_highest_priority_admin(self) -> None:
        """Test admin is priority when no owner."""
        manager = PermissionManager()

        roles = [
            Role(user_id="user-001", role_type=RoleType.MEMBER),
            Role(user_id="user-001", role_type=RoleType.ADMIN),
        ]

        role_type = manager._highest_priority_role(roles)

        assert role_type == RoleType.ADMIN

    def test_highest_priority_full_order(self) -> None:
        """Test full priority order."""
        manager = PermissionManager()

        # Add in reverse priority order
        roles = [
            Role(user_id="user-001", role_type=RoleType.VIEWER),
            Role(user_id="user-001", role_type=RoleType.REVIEWER),
            Role(user_id="user-001", role_type=RoleType.MEMBER),
            Role(user_id="user-001", role_type=RoleType.ADMIN),
            Role(user_id="user-001", role_type=RoleType.OWNER),
        ]

        role_type = manager._highest_priority_role(roles)

        assert role_type == RoleType.OWNER

    def test_highest_priority_single_role(self) -> None:
        """Test with single role."""
        manager = PermissionManager()

        roles = [Role(user_id="user-001", role_type=RoleType.MEMBER)]

        role_type = manager._highest_priority_role(roles)

        assert role_type == RoleType.MEMBER


# ============================================================================
# Permission Checking Tests
# ============================================================================


class TestHasPermission:
    """Tests for PermissionManager.has_permission()."""

    def test_owner_has_all_permissions(self, sample_roles: list[Role]) -> None:
        """Test owner has all permissions."""
        manager = PermissionManager()

        # Check various permissions
        assert manager.has_permission(
            user_id="user-001",
            permission=Permission.DELETE_WORKSPACE,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert manager.has_permission(
            user_id="user-001",
            permission=Permission.DISPATCH_TASK,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert manager.has_permission(
            user_id="user-001",
            permission=Permission.MANAGE_MEMBERS,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_admin_lacks_workspace_delete(self, sample_roles: list[Role]) -> None:
        """Test admin cannot delete workspace."""
        manager = PermissionManager()

        can_delete = manager.has_permission(
            user_id="user-002",
            permission=Permission.DELETE_WORKSPACE,
            team_id="team-001",
            roles=sample_roles,
        )

        assert can_delete is False

    def test_admin_has_most_permissions(self, sample_roles: list[Role]) -> None:
        """Test admin has most other permissions."""
        manager = PermissionManager()

        assert manager.has_permission(
            user_id="user-002",
            permission=Permission.DISPATCH_TASK,
            team_id="team-001",
            roles=sample_roles,
        )

        assert manager.has_permission(
            user_id="user-002",
            permission=Permission.MANAGE_MEMBERS,
            team_id="team-001",
            roles=sample_roles,
        )

    def test_member_has_basic_permissions(self, sample_roles: list[Role]) -> None:
        """Test member has basic permissions."""
        manager = PermissionManager()

        # Can dispatch and modify
        assert manager.has_permission(
            user_id="user-003",
            permission=Permission.DISPATCH_TASK,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Cannot manage members
        assert not manager.has_permission(
            user_id="user-003",
            permission=Permission.MANAGE_MEMBERS,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_reviewer_has_review_permissions(self, sample_roles: list[Role]) -> None:
        """Test reviewer has review-specific permissions."""
        manager = PermissionManager()

        # Can review
        assert manager.has_permission(
            user_id="user-004",
            permission=Permission.REVIEW_TASK,
            team_id="team-001",
            roles=sample_roles,
        )

        # Cannot dispatch
        assert not manager.has_permission(
            user_id="user-004",
            permission=Permission.DISPATCH_TASK,
            team_id="team-001",
            roles=sample_roles,
        )

    def test_viewer_read_only(self, sample_roles: list[Role]) -> None:
        """Test viewer only has read permissions."""
        manager = PermissionManager()

        # Can view activity
        assert manager.has_permission(
            user_id="user-005",
            permission=Permission.VIEW_ACTIVITY,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Cannot dispatch
        assert not manager.has_permission(
            user_id="user-005",
            permission=Permission.DISPATCH_TASK,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_no_role_default_deny(self, sample_roles: list[Role]) -> None:
        """Test users without roles are denied by default."""
        manager = PermissionManager()

        can_dispatch = manager.has_permission(
            user_id="user-999",
            permission=Permission.DISPATCH_TASK,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert can_dispatch is False

    def test_no_role_default_allow(self, sample_roles: list[Role]) -> None:
        """Test users without roles allowed with default_allow=True."""
        config = PermissionConfig(default_allow=True)
        manager = PermissionManager(config=config)

        can_dispatch = manager.has_permission(
            user_id="user-999",
            permission=Permission.DISPATCH_TASK,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert can_dispatch is True

    def test_expired_role_denied(self, sample_roles: list[Role]) -> None:
        """Test expired role denies permission."""
        manager = PermissionManager()

        # User 007 has expired admin role
        can_dispatch = manager.has_permission(
            user_id="user-007",
            permission=Permission.DISPATCH_TASK,
            team_id="team-001",
            roles=sample_roles,
        )

        assert can_dispatch is False

    def test_workspace_role_priority(self, sample_roles: list[Role]) -> None:
        """Test workspace role takes priority over team role."""
        manager = PermissionManager()

        # User 006 has team MEMBER but workspace ADMIN in workspace-002
        can_manage = manager.has_permission(
            user_id="user-006",
            permission=Permission.MANAGE_MEMBERS,
            workspace_id="workspace-002",
            roles=sample_roles,
        )

        assert can_manage is True


# ============================================================================
# Convenience Method Tests
# ============================================================================


class TestConvenienceMethods:
    """Tests for PermissionManager convenience methods."""

    def test_can_dispatch(self, sample_roles: list[Role]) -> None:
        """Test can_dispatch() convenience method."""
        manager = PermissionManager()

        # Member can dispatch
        assert manager.can_dispatch(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Viewer cannot dispatch
        assert not manager.can_dispatch(
            user_id="user-005",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_can_review(self, sample_roles: list[Role]) -> None:
        """Test can_review() convenience method."""
        manager = PermissionManager()

        # Reviewer can review
        assert manager.can_review(
            user_id="user-004",
            team_id="team-001",
            roles=sample_roles,
        )

        # Member cannot review
        assert not manager.can_review(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_can_modify_spec(self, sample_roles: list[Role]) -> None:
        """Test can_modify_spec() convenience method."""
        manager = PermissionManager()

        # Admin can modify spec
        assert manager.can_modify_spec(
            user_id="user-002",
            team_id="team-001",
            roles=sample_roles,
        )

        # Viewer cannot modify spec
        assert not manager.can_modify_spec(
            user_id="user-005",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_can_approve(self, sample_roles: list[Role]) -> None:
        """Test can_approve() convenience method."""
        manager = PermissionManager()

        # Reviewer can approve
        assert manager.can_approve(
            user_id="user-004",
            team_id="team-001",
            roles=sample_roles,
        )

        # Member cannot approve
        assert not manager.can_approve(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_can_manage_members(self, sample_roles: list[Role]) -> None:
        """Test can_manage_members() convenience method."""
        manager = PermissionManager()

        # Admin can manage members
        assert manager.can_manage_members(
            user_id="user-002",
            team_id="team-001",
            roles=sample_roles,
        )

        # Member cannot manage members
        assert not manager.can_manage_members(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_can_delete_workspace(self, sample_roles: list[Role]) -> None:
        """Test can_delete_workspace() convenience method."""
        manager = PermissionManager()

        # Owner can delete workspace
        assert manager.can_delete_workspace(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Admin cannot delete workspace
        assert not manager.can_delete_workspace(
            user_id="user-002",
            team_id="team-001",
            roles=sample_roles,
        )


# ============================================================================
# User Permissions Retrieval Tests
# ============================================================================


class TestGetUserPermissions:
    """Tests for PermissionManager.get_user_permissions()."""

    def test_get_owner_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting all permissions for owner."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Owner should have all permissions
        assert Permission.DISPATCH_TASK in permissions
        assert Permission.DELETE_WORKSPACE in permissions
        assert Permission.MANAGE_MEMBERS in permissions
        assert Permission.VIEW_ACTIVITY in permissions

        # Should have 13 permissions total
        assert len(permissions) > 10

    def test_get_admin_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting permissions for admin."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-002",
            team_id="team-001",
            roles=sample_roles,
        )

        # Admin should have most but not delete workspace
        assert Permission.DISPATCH_TASK in permissions
        assert Permission.MANAGE_MEMBERS in permissions
        assert Permission.DELETE_WORKSPACE not in permissions

    def test_get_member_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting permissions for member."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Member has basic permissions
        assert Permission.DISPATCH_TASK in permissions
        assert Permission.MODIFY_TASK in permissions
        assert Permission.MANAGE_MEMBERS not in permissions

    def test_get_viewer_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting permissions for viewer."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-005",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Viewer only has view activity
        assert Permission.VIEW_ACTIVITY in permissions
        assert len(permissions) == 1

    def test_get_no_role_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting permissions for user with no role."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-999",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Should return empty set
        assert len(permissions) == 0

    def test_get_expired_role_permissions(self, sample_roles: list[Role]) -> None:
        """Test getting permissions for expired role."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-007",
            team_id="team-001",
            roles=sample_roles,
        )

        # Expired role should return empty set
        assert len(permissions) == 0


# ============================================================================
# Multiple Permission Checking Tests
# ============================================================================


class TestCheckPermissions:
    """Tests for PermissionManager.check_permissions()."""

    def test_check_all_present(self, sample_roles: list[Role]) -> None:
        """Test checking when user has all required permissions."""
        manager = PermissionManager()

        has_all, missing = manager.check_permissions(
            user_id="user-001",
            required_permissions=[
                Permission.DISPATCH_TASK,
                Permission.MODIFY_SPEC,
                Permission.VIEW_ACTIVITY,
            ],
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert has_all is True
        assert len(missing) == 0

    def test_check_some_missing(self, sample_roles: list[Role]) -> None:
        """Test checking when user lacks some permissions."""
        manager = PermissionManager()

        has_all, missing = manager.check_permissions(
            user_id="user-003",
            required_permissions=[
                Permission.DISPATCH_TASK,
                Permission.MANAGE_MEMBERS,  # Member doesn't have this
                Permission.VIEW_ACTIVITY,
            ],
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert has_all is False
        assert Permission.MANAGE_MEMBERS in missing

    def test_check_all_missing(self, sample_roles: list[Role]) -> None:
        """Test checking when user has none of the permissions."""
        manager = PermissionManager()

        has_all, missing = manager.check_permissions(
            user_id="user-005",
            required_permissions=[
                Permission.DISPATCH_TASK,
                Permission.MANAGE_MEMBERS,
            ],
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert has_all is False
        assert len(missing) == 2

    def test_check_empty_list(self, sample_roles: list[Role]) -> None:
        """Test checking with empty permission list."""
        manager = PermissionManager()

        has_all, missing = manager.check_permissions(
            user_id="user-001",
            required_permissions=[],
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert has_all is True
        assert len(missing) == 0

    def test_check_no_role(self, sample_roles: list[Role]) -> None:
        """Test checking for user with no role."""
        manager = PermissionManager()

        has_all, missing = manager.check_permissions(
            user_id="user-999",
            required_permissions=[Permission.VIEW_ACTIVITY],
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert has_all is False
        assert Permission.VIEW_ACTIVITY in missing


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_workspace_inheritance_disabled(self, sample_roles: list[Role]) -> None:
        """Test permission checking with workspace inheritance disabled."""
        config = PermissionConfig(workspace_inheritance=False)
        manager = PermissionManager(config=config)

        # User 002 has team-level admin role
        # With inheritance disabled, workspace check won't find it
        can_manage = manager.has_permission(
            user_id="user-002",
            permission=Permission.MANAGE_MEMBERS,
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        assert can_manage is False

    def test_multiple_users_same_workspace(self, sample_roles: list[Role]) -> None:
        """Test multiple users with different roles in same workspace."""
        manager = PermissionManager()

        # Owner can do everything
        assert manager.can_delete_workspace(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Member cannot
        assert not manager.can_delete_workspace(
            user_id="user-003",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_user_different_workspaces(self, sample_roles: list[Role]) -> None:
        """Test same user with different roles in different workspaces."""
        manager = PermissionManager()

        # User 006 is admin in workspace-002
        assert manager.can_manage_members(
            user_id="user-006",
            workspace_id="workspace-002",
            roles=sample_roles,
        )

        # But not in workspace-001 (has team-level member role there)
        assert not manager.can_manage_members(
            user_id="user-006",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

    def test_role_priority_with_mixed_roles(self, sample_roles: list[Role]) -> None:
        """Test role priority when user has mixed team and workspace roles."""
        manager = PermissionManager()

        # User 006: team MEMBER + workspace ADMIN
        # In workspace-002, should use ADMIN role
        permissions = manager.get_user_permissions(
            user_id="user-006",
            workspace_id="workspace-002",
            roles=sample_roles,
        )

        assert Permission.MANAGE_MEMBERS in permissions

    def test_all_permission_types(self, sample_roles: list[Role]) -> None:
        """Test checking all defined permission types."""
        manager = PermissionManager()

        # Get all permissions for owner
        permissions = manager.get_user_permissions(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Verify we have permissions from all categories
        # Task permissions
        assert Permission.DISPATCH_TASK in permissions
        assert Permission.MODIFY_TASK in permissions
        assert Permission.DELETE_TASK in permissions

        # Spec permissions
        assert Permission.CREATE_SPEC in permissions
        assert Permission.MODIFY_SPEC in permissions
        assert Permission.DELETE_SPEC in permissions

        # Review permissions
        assert Permission.REQUEST_REVIEW in permissions
        assert Permission.REVIEW_TASK in permissions
        assert Permission.APPROVE_TASK in permissions
        assert Permission.REJECT_TASK in permissions

        # Team/Workspace permissions
        assert Permission.MANAGE_MEMBERS in permissions
        assert Permission.MANAGE_SETTINGS in permissions
        assert Permission.DELETE_WORKSPACE in permissions

        # General permissions
        assert Permission.VIEW_ACTIVITY in permissions
        assert Permission.MANAGE_NOTIFICATIONS in permissions

    def test_role_without_expiration(self) -> None:
        """Test role without expiration date."""
        manager = PermissionManager()

        roles = [
            Role(
                user_id="user-001",
                role_type=RoleType.ADMIN,
                team_id="team-001",
                expires_at=None,
            )
        ]

        # Should have permissions
        assert manager.has_permission(
            user_id="user-001",
            permission=Permission.DISPATCH_TASK,
            team_id="team-001",
            roles=roles,
        )

    def test_permission_immutability(self, sample_roles: list[Role]) -> None:
        """Test that returned permission sets don't affect internal state."""
        manager = PermissionManager()

        permissions = manager.get_user_permissions(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Verify the returned set is a copy (modifying it shouldn't affect anything)
        original_len = len(permissions)
        permissions.clear()  # Clear the returned set

        # Get permissions again - should still work
        permissions2 = manager.get_user_permissions(
            user_id="user-001",
            workspace_id="workspace-001",
            roles=sample_roles,
        )

        # Should be unchanged from original
        assert len(permissions2) == original_len
