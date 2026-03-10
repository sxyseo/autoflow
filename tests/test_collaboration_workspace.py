"""
Unit Tests for Workspace Management

Tests the WorkspaceManager class for managing workspaces in the collaboration system.
Provides CRUD operations for workspaces with role-based access control.

These tests use temporary directories to avoid affecting real workspace files.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.collaboration.models import Role, RoleType, Workspace
from autoflow.collaboration.workspace import WorkspaceManager


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_workspace_dir(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    workspace_dir = tmp_path / ".autoflow"
    workspace_dir.mkdir()
    return workspace_dir


@pytest.fixture
def workspace_manager(temp_workspace_dir: Path) -> WorkspaceManager:
    """Create a WorkspaceManager instance with temporary directory."""
    manager = WorkspaceManager(temp_workspace_dir)
    manager.initialize()
    return manager


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


# ============================================================================
# WorkspaceManager Init Tests
# ============================================================================


class TestWorkspaceManagerInit:
    """Tests for WorkspaceManager initialization."""

    def test_init_with_path(self, temp_workspace_dir: Path) -> None:
        """Test WorkspaceManager initialization with path."""
        manager = WorkspaceManager(temp_workspace_dir)

        assert manager.state_dir == temp_workspace_dir.resolve()
        assert manager.workspaces_dir == temp_workspace_dir.resolve() / "workspaces"
        assert manager.roles_dir == temp_workspace_dir.resolve() / "workspace_roles"
        assert manager.backup_dir == temp_workspace_dir.resolve() / "backups"

    def test_init_with_string(self, temp_workspace_dir: Path) -> None:
        """Test WorkspaceManager initialization with string path."""
        manager = WorkspaceManager(str(temp_workspace_dir))

        assert manager.state_dir == temp_workspace_dir.resolve()

    def test_initialize(self, temp_workspace_dir: Path) -> None:
        """Test WorkspaceManager.initialize() creates directories."""
        manager = WorkspaceManager(temp_workspace_dir)
        manager.initialize()

        assert manager.state_dir.exists()
        assert manager.workspaces_dir.exists()
        assert manager.roles_dir.exists()
        assert manager.backup_dir.exists()

    def test_initialize_idempotent(self, workspace_manager: WorkspaceManager) -> None:
        """Test WorkspaceManager.initialize() is idempotent."""
        # Should not raise error when called again
        workspace_manager.initialize()

        assert workspace_manager.state_dir.exists()


# ============================================================================
# Workspace Creation Tests
# ============================================================================


class TestWorkspaceCreation:
    """Tests for workspace creation."""

    def test_create_workspace_minimal(self, workspace_manager: WorkspaceManager) -> None:
        """Test creating a workspace with minimal fields."""
        workspace = workspace_manager.create_workspace(
            workspace_id="workspace-001",
            name="Project X",
            team_id="team-001",
        )

        assert workspace.id == "workspace-001"
        assert workspace.name == "Project X"
        assert workspace.description == ""
        assert workspace.team_id == "team-001"
        assert workspace.settings == {}
        assert workspace.metadata == {}

    def test_create_workspace_full(self, workspace_manager: WorkspaceManager) -> None:
        """Test creating a workspace with all fields."""
        workspace = workspace_manager.create_workspace(
            workspace_id="workspace-001",
            name="Project X",
            team_id="team-001",
            description="Main project workspace",
            settings={"visibility": "team"},
            metadata={"project_code": "PROJ-X"},
        )

        assert workspace.description == "Main project workspace"
        assert workspace.settings == {"visibility": "team"}
        assert workspace.metadata == {"project_code": "PROJ-X"}

    def test_create_workspace_persists(
        self, workspace_manager: WorkspaceManager, sample_workspace_data: dict
    ) -> None:
        """Test creating a workspace persists to disk."""
        workspace = workspace_manager.create_workspace(
            workspace_id=sample_workspace_data["id"],
            name=sample_workspace_data["name"],
            team_id=sample_workspace_data["team_id"],
            description=sample_workspace_data["description"],
            settings=sample_workspace_data["settings"],
        )

        # Verify file exists
        file_path = workspace_manager.workspaces_dir / f"{workspace.id}.json"
        assert file_path.exists()

        # Verify file contents
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["id"] == "workspace-001"
        assert data["name"] == "Project X"

    def test_create_workspace_duplicate(
        self, workspace_manager: WorkspaceManager, sample_workspace_data: dict
    ) -> None:
        """Test creating duplicate workspace raises error."""
        workspace_manager.create_workspace(
            workspace_id=sample_workspace_data["id"],
            name=sample_workspace_data["name"],
            team_id=sample_workspace_data["team_id"],
            description=sample_workspace_data["description"],
            settings=sample_workspace_data["settings"],
        )

        with pytest.raises(ValueError, match="already exists"):
            workspace_manager.create_workspace(
                workspace_id=sample_workspace_data["id"],
                name=sample_workspace_data["name"],
                team_id=sample_workspace_data["team_id"],
                description=sample_workspace_data["description"],
                settings=sample_workspace_data["settings"],
            )

    def test_create_workspace_with_timestamps(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test workspace creation includes timestamps."""
        workspace = workspace_manager.create_workspace(
            workspace_id="workspace-001",
            name="Project X",
            team_id="team-001",
        )

        assert isinstance(workspace.created_at, datetime)
        assert isinstance(workspace.updated_at, datetime)


# ============================================================================
# Workspace Retrieval Tests
# ============================================================================


class TestWorkspaceRetrieval:
    """Tests for workspace retrieval."""

    def test_get_workspace_existing(
        self, workspace_manager: WorkspaceManager, sample_workspace_data: dict
    ) -> None:
        """Test getting an existing workspace."""
        created = workspace_manager.create_workspace(
            workspace_id=sample_workspace_data["id"],
            name=sample_workspace_data["name"],
            team_id=sample_workspace_data["team_id"],
            description=sample_workspace_data["description"],
            settings=sample_workspace_data["settings"],
        )
        retrieved = workspace_manager.get_workspace("workspace-001")

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name
        assert retrieved.team_id == created.team_id

    def test_get_workspace_nonexistent(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting a nonexistent workspace returns None."""
        result = workspace_manager.get_workspace("nonexistent")

        assert result is None

    def test_get_workspace_after_update(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test getting workspace returns updated data."""
        workspace_manager.create_workspace(
            workspace_id="workspace-001",
            name="Project X",
            team_id="team-001",
        )

        workspace_manager.update_workspace("workspace-001", description="Updated description")

        retrieved = workspace_manager.get_workspace("workspace-001")
        assert retrieved is not None
        assert retrieved.description == "Updated description"


# ============================================================================
# Workspace Listing Tests
# ============================================================================


class TestWorkspaceListing:
    """Tests for workspace listing."""

    def test_list_workspaces_all(self, workspace_manager: WorkspaceManager) -> None:
        """Test listing all workspaces."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.create_workspace("workspace-002", "Project Y", "team-001")
        workspace_manager.create_workspace("workspace-003", "Project Z", "team-002")

        workspaces = workspace_manager.list_workspaces()

        assert len(workspaces) == 3

    def test_list_workspaces_filter_by_team(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test listing workspaces filtered by team."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.create_workspace("workspace-002", "Project Y", "team-001")
        workspace_manager.create_workspace("workspace-003", "Project Z", "team-002")

        team1_workspaces = workspace_manager.list_workspaces(team_id="team-001")
        team2_workspaces = workspace_manager.list_workspaces(team_id="team-002")

        assert len(team1_workspaces) == 2
        assert len(team2_workspaces) == 1

    def test_list_workspaces_with_limit(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test listing workspaces with limit."""
        for i in range(10):
            workspace_manager.create_workspace(
                f"workspace-{i:03d}", f"Project {i}", "team-001"
            )

        workspaces = workspace_manager.list_workspaces(limit=5)

        assert len(workspaces) == 5

    def test_list_workspaces_sorted_by_created_at(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test listing workspaces sorts by created_at descending."""
        import time

        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        time.sleep(0.01)  # Ensure different timestamps
        workspace_manager.create_workspace("workspace-002", "Project Y", "team-001")

        workspaces = workspace_manager.list_workspaces()

        # Most recent first
        assert workspaces[0].id == "workspace-002"
        assert workspaces[1].id == "workspace-001"

    def test_list_workspaces_empty(self, workspace_manager: WorkspaceManager) -> None:
        """Test listing workspaces when none exist."""
        workspaces = workspace_manager.list_workspaces()

        assert workspaces == []

    def test_get_workspace_count(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting workspace count."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.create_workspace("workspace-002", "Project Y", "team-001")
        workspace_manager.create_workspace("workspace-003", "Project Z", "team-002")

        total_count = workspace_manager.get_workspace_count()
        team1_count = workspace_manager.get_workspace_count(team_id="team-001")

        assert total_count == 3
        assert team1_count == 2


# ============================================================================
# Workspace Update Tests
# ============================================================================


class TestWorkspaceUpdate:
    """Tests for workspace updates."""

    def test_update_workspace_name(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating workspace name."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        updated = workspace_manager.update_workspace("workspace-001", name="Updated Project")

        assert updated is not None
        assert updated.name == "Updated Project"

    def test_update_workspace_description(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating workspace description."""
        workspace_manager.create_workspace(
            "workspace-001", "Project X", "team-001", description="Original"
        )

        updated = workspace_manager.update_workspace(
            "workspace-001", description="Updated description"
        )

        assert updated is not None
        assert updated.description == "Updated description"

    def test_update_workspace_settings(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating workspace settings."""
        workspace_manager.create_workspace(
            "workspace-001", "Project X", "team-001", settings={"visibility": "private"}
        )

        updated = workspace_manager.update_workspace(
            "workspace-001", settings={"visibility": "public", "allow_guests": True}
        )

        assert updated is not None
        assert updated.settings == {"visibility": "public", "allow_guests": True}

    def test_update_workspace_metadata(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating workspace metadata."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        updated = workspace_manager.update_workspace(
            "workspace-001", metadata={"project_code": "PROJ-X", "phase": "planning"}
        )

        assert updated is not None
        assert updated.metadata == {"project_code": "PROJ-X", "phase": "planning"}

    def test_update_workspace_multiple_fields(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating multiple workspace fields at once."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        updated = workspace_manager.update_workspace(
            "workspace-001",
            name="Updated Project",
            description="Updated description",
            settings={"visibility": "public"},
        )

        assert updated is not None
        assert updated.name == "Updated Project"
        assert updated.description == "Updated description"
        assert updated.settings == {"visibility": "public"}

    def test_update_workspace_updates_timestamp(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test updating workspace updates timestamp."""
        workspace = workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        original_updated = workspace.updated_at

        import time

        time.sleep(0.01)
        updated = workspace_manager.update_workspace("workspace-001", name="Updated")

        assert updated is not None
        assert updated.updated_at > original_updated

    def test_update_workspace_nonexistent(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating nonexistent workspace returns None."""
        result = workspace_manager.update_workspace("nonexistent", name="New Name")

        assert result is None

    def test_update_workspace_partial(self, workspace_manager: WorkspaceManager) -> None:
        """Test partial workspace update doesn't affect other fields."""
        workspace_manager.create_workspace(
            "workspace-001",
            "Project X",
            "team-001",
            description="Original description",
            settings={"visibility": "private"},
        )

        updated = workspace_manager.update_workspace("workspace-001", name="Updated Project")

        assert updated is not None
        assert updated.name == "Updated Project"
        assert updated.description == "Original description"
        assert updated.settings == {"visibility": "private"}


# ============================================================================
# Workspace Deletion Tests
# ============================================================================


class TestWorkspaceDeletion:
    """Tests for workspace deletion."""

    def test_delete_workspace_existing(self, workspace_manager: WorkspaceManager) -> None:
        """Test deleting an existing workspace."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        result = workspace_manager.delete_workspace("workspace-001")

        assert result is True
        assert workspace_manager.get_workspace("workspace-001") is None

    def test_delete_workspace_nonexistent(self, workspace_manager: WorkspaceManager) -> None:
        """Test deleting a nonexistent workspace returns False."""
        result = workspace_manager.delete_workspace("nonexistent")

        assert result is False

    def test_delete_workspace_creates_backup(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test deleting workspace creates backup."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        workspace_manager.delete_workspace("workspace-001")

        # Backup should exist
        backups = list(workspace_manager.backup_dir.glob("**/*.bak"))
        assert len(backups) > 0

    def test_workspace_exists(self, workspace_manager: WorkspaceManager) -> None:
        """Test workspace_exists method."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        assert workspace_manager.workspace_exists("workspace-001") is True
        assert workspace_manager.workspace_exists("nonexistent") is False

    def test_workspace_exists_after_delete(self, workspace_manager: WorkspaceManager) -> None:
        """Test workspace_exists returns False after deletion."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        workspace_manager.delete_workspace("workspace-001")

        assert workspace_manager.workspace_exists("workspace-001") is False


# ============================================================================
# Member Management Tests
# ============================================================================


class TestMemberManagement:
    """Tests for workspace member management."""

    def test_add_member(self, workspace_manager: WorkspaceManager) -> None:
        """Test adding a member to workspace."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        role = workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        assert role.user_id == "user-001"
        assert role.role_type == RoleType.MEMBER
        assert role.workspace_id == "workspace-001"

    def test_add_member_with_role(self, workspace_manager: WorkspaceManager) -> None:
        """Test adding member with specific role."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        role = workspace_manager.add_member(
            "workspace-001", "user-001", RoleType.ADMIN, granted_by="user-002"
        )

        assert role.role_type == RoleType.ADMIN
        assert role.granted_by == "user-002"

    def test_add_member_with_expiration(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test adding member with expiration."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        expires = datetime.utcnow() + timedelta(days=30)

        role = workspace_manager.add_member(
            "workspace-001", "user-001", RoleType.REVIEWER, expires_at=expires
        )

        assert role.expires_at == expires

    def test_add_member_duplicate(self, workspace_manager: WorkspaceManager) -> None:
        """Test adding duplicate member raises error."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        with pytest.raises(ValueError, match="already a member"):
            workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)

    def test_add_member_nonexistent_workspace(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test adding member to nonexistent workspace raises error."""
        with pytest.raises(ValueError, match="does not exist"):
            workspace_manager.add_member("nonexistent", "user-001", RoleType.MEMBER)

    def test_remove_member(self, workspace_manager: WorkspaceManager) -> None:
        """Test removing a member from workspace."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        result = workspace_manager.remove_member("workspace-001", "user-001")

        assert result is True
        assert workspace_manager.get_member_role("workspace-001", "user-001") is None

    def test_remove_member_nonexistent(self, workspace_manager: WorkspaceManager) -> None:
        """Test removing nonexistent member returns False."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        result = workspace_manager.remove_member("workspace-001", "user-999")

        assert result is False

    def test_update_member_role(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating member role."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        updated = workspace_manager.update_member_role(
            "workspace-001", "user-001", RoleType.ADMIN, granted_by="user-002"
        )

        assert updated is not None
        assert updated.role_type == RoleType.ADMIN
        assert updated.granted_by == "user-002"

    def test_update_member_role_nonexistent(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test updating nonexistent member role returns None."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        result = workspace_manager.update_member_role(
            "workspace-001", "user-999", RoleType.ADMIN
        )

        assert result is None

    def test_get_member_role(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting member role."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)

        role = workspace_manager.get_member_role("workspace-001", "user-001")

        assert role is not None
        assert role.user_id == "user-001"
        assert role.role_type == RoleType.ADMIN

    def test_get_member_role_nonexistent(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting nonexistent member role returns None."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        role = workspace_manager.get_member_role("workspace-001", "user-999")

        assert role is None

    def test_list_members(self, workspace_manager: WorkspaceManager) -> None:
        """Test listing workspace members."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-001", "user-002", RoleType.MEMBER)
        workspace_manager.add_member("workspace-001", "user-003", RoleType.REVIEWER)

        members = workspace_manager.list_members("workspace-001")

        assert len(members) == 3

    def test_list_members_filter_by_role(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test listing members filtered by role."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-001", "user-002", RoleType.MEMBER)
        workspace_manager.add_member("workspace-001", "user-003", RoleType.ADMIN)

        admins = workspace_manager.list_members("workspace-001", RoleType.ADMIN)

        assert len(admins) == 2
        assert all(r.role_type == RoleType.ADMIN for r in admins)

    def test_list_members_excludes_expired(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test listing members excludes expired roles."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        # Add expired member
        expired_time = datetime.utcnow() - timedelta(days=1)
        workspace_manager.add_member(
            "workspace-001", "user-002", RoleType.MEMBER, expires_at=expired_time
        )

        members = workspace_manager.list_members("workspace-001")

        # Only non-expired member should be listed
        assert len(members) == 1
        assert members[0].user_id == "user-001"

    def test_is_member(self, workspace_manager: WorkspaceManager) -> None:
        """Test checking if user is a member."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        assert workspace_manager.is_member("workspace-001", "user-001") is True
        assert workspace_manager.is_member("workspace-001", "user-999") is False

    def test_is_member_expired(self, workspace_manager: WorkspaceManager) -> None:
        """Test is_member returns False for expired members."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        expired_time = datetime.utcnow() - timedelta(days=1)
        workspace_manager.add_member(
            "workspace-001", "user-001", RoleType.MEMBER, expires_at=expired_time
        )

        assert workspace_manager.is_member("workspace-001", "user-001") is False

    def test_get_member_count(self, workspace_manager: WorkspaceManager) -> None:
        """Test getting member count."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-001", "user-002", RoleType.MEMBER)

        count = workspace_manager.get_member_count("workspace-001")

        assert count == 2


# ============================================================================
# Backup and Recovery Tests
# ============================================================================


class TestBackupRecovery:
    """Tests for backup and recovery functionality."""

    def test_workspace_update_creates_backup(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test updating workspace creates backup."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        # Update to create backup
        workspace_manager.update_workspace("workspace-001", name="Updated")

        # Backup should exist
        backups = list(workspace_manager.backup_dir.glob("**/*.bak"))
        assert len(backups) > 0

    def test_role_update_creates_backup(self, workspace_manager: WorkspaceManager) -> None:
        """Test updating role creates backup."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.MEMBER)

        # Update role to create backup
        workspace_manager.update_member_role("workspace-001", "user-001", RoleType.ADMIN)

        # Backup should exist
        backups = list(workspace_manager.backup_dir.glob("**/*.bak"))
        assert len(backups) > 0


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_workspace_with_unicode(self, workspace_manager: WorkspaceManager) -> None:
        """Test workspace with unicode characters."""
        workspace = workspace_manager.create_workspace(
            "workspace-001",
            "项目 X",
            "team-001",
            description="中文描述",
            metadata={"emoji": "🎉"},
        )

        assert "项目" in workspace.name
        assert "中文" in workspace.description
        assert workspace.metadata["emoji"] == "🎉"

    def test_workspace_with_complex_settings(self, workspace_manager: WorkspaceManager) -> None:
        """Test workspace with complex nested settings."""
        settings = {
            "permissions": {
                "members": ["read", "write", "delete"],
                "guests": ["read"],
            },
            "notifications": {
                "enabled": True,
                "types": ["all"],
            },
        }
        workspace = workspace_manager.create_workspace(
            "workspace-001",
            "Project X",
            "team-001",
            settings=settings,
        )

        assert workspace.settings["permissions"]["members"] == ["read", "write", "delete"]

    def test_many_workspaces(self, workspace_manager: WorkspaceManager) -> None:
        """Test handling many workspaces."""
        for i in range(50):
            workspace_manager.create_workspace(
                f"workspace-{i:03d}",
                f"Project {i}",
                f"team-{i % 5}",
            )

        count = workspace_manager.get_workspace_count()
        assert count == 50

    def test_many_members(self, workspace_manager: WorkspaceManager) -> None:
        """Test handling many members in a workspace."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        for i in range(100):
            workspace_manager.add_member(
                "workspace-001", f"user-{i:03d}", RoleType.MEMBER
            )

        count = workspace_manager.get_member_count("workspace-001")
        assert count == 100

    def test_workspace_with_special_id(self, workspace_manager: WorkspaceManager) -> None:
        """Test workspace with special characters in ID."""
        workspace = workspace_manager.create_workspace(
            "workspace-001-special",
            "Project X",
            "team-001",
        )

        assert workspace.id == "workspace-001-special"
        assert workspace_manager.workspace_exists("workspace-001-special") is True

    def test_member_persistence(self, workspace_manager: WorkspaceManager) -> None:
        """Test member roles persist across workspace retrieval."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)

        # Get workspace again
        role = workspace_manager.get_member_role("workspace-001", "user-001")

        assert role is not None
        assert role.role_type == RoleType.ADMIN

    def test_workspace_and_members_independent(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test that workspaces and members are independent."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")
        workspace_manager.create_workspace("workspace-002", "Project Y", "team-001")

        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-002", "user-001", RoleType.MEMBER)

        role1 = workspace_manager.get_member_role("workspace-001", "user-001")
        role2 = workspace_manager.get_member_role("workspace-002", "user-001")

        assert role1 is not None
        assert role2 is not None
        assert role1.role_type == RoleType.ADMIN
        assert role2.role_type == RoleType.MEMBER

    def test_role_with_metadata(self, workspace_manager: WorkspaceManager) -> None:
        """Test role with metadata."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        role = workspace_manager.add_member(
            "workspace-001",
            "user-001",
            RoleType.ADMIN,
            metadata={"reason": "project lead", "approved_by": "manager"},
        )

        assert role.metadata["reason"] == "project lead"
        assert role.metadata["approved_by"] == "manager"

    def test_workspace_metadata_persistence(
        self, workspace_manager: WorkspaceManager
    ) -> None:
        """Test workspace metadata persists."""
        workspace_manager.create_workspace(
            "workspace-001",
            "Project X",
            "team-001",
            metadata={"project_code": "PROJ-X"},
        )

        workspace = workspace_manager.get_workspace("workspace-001")

        assert workspace is not None
        assert workspace.metadata == {"project_code": "PROJ-X"}

    def test_empty_workspace_list(self, workspace_manager: WorkspaceManager) -> None:
        """Test listing members when workspace has no members."""
        workspace_manager.create_workspace("workspace-001", "Project X", "team-001")

        members = workspace_manager.list_members("workspace-001")

        assert members == []

    def test_workspace_settings_replacement(self, workspace_manager: WorkspaceManager) -> None:
        """Test that updating settings replaces entire dict."""
        workspace_manager.create_workspace(
            "workspace-001",
            "Project X",
            "team-001",
            settings={"visibility": "private", "feature_x": True},
        )

        workspace_manager.update_workspace(
            "workspace-001", settings={"visibility": "public"}
        )

        workspace = workspace_manager.get_workspace("workspace-001")
        assert workspace is not None
        assert workspace.settings == {"visibility": "public"}
        assert "feature_x" not in workspace.settings


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for workspace workflows."""

    def test_full_workspace_lifecycle(self, workspace_manager: WorkspaceManager) -> None:
        """Test complete workspace lifecycle."""
        # Create workspace
        workspace = workspace_manager.create_workspace(
            "workspace-001",
            "Project X",
            "team-001",
            description="Initial description",
        )

        # Add members
        workspace_manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-001", "user-002", RoleType.MEMBER)
        workspace_manager.add_member("workspace-001", "user-003", RoleType.REVIEWER)

        # Verify members
        members = workspace_manager.list_members("workspace-001")
        assert len(members) == 3

        # Update workspace
        updated = workspace_manager.update_workspace(
            "workspace-001", description="Updated description"
        )
        assert updated is not None
        assert updated.description == "Updated description"

        # Update member role
        role = workspace_manager.update_member_role(
            "workspace-001", "user-002", RoleType.ADMIN
        )
        assert role is not None
        assert role.role_type == RoleType.ADMIN

        # Remove member
        removed = workspace_manager.remove_member("workspace-001", "user-003")
        assert removed is True

        # Verify removal
        members = workspace_manager.list_members("workspace-001")
        assert len(members) == 2

        # Delete workspace
        deleted = workspace_manager.delete_workspace("workspace-001")
        assert deleted is True

        # Verify deletion
        assert workspace_manager.get_workspace("workspace-001") is None

    def test_multi_workspace_scenario(self, workspace_manager: WorkspaceManager) -> None:
        """Test managing multiple workspaces."""
        # Create multiple workspaces
        for i in range(3):
            workspace_manager.create_workspace(
                f"workspace-{i:03d}",
                f"Project {i}",
                "team-001",
            )

        # Add different members to each
        workspace_manager.add_member("workspace-000", "user-001", RoleType.ADMIN)
        workspace_manager.add_member("workspace-001", "user-002", RoleType.ADMIN)
        workspace_manager.add_member("workspace-002", "user-003", RoleType.ADMIN)

        # Verify each workspace has correct members
        for i in range(3):
            workspace_id = f"workspace-{i:03d}"
            members = workspace_manager.list_members(workspace_id)
            assert len(members) == 1
            assert members[0].user_id == f"user-{i+1:03d}"
