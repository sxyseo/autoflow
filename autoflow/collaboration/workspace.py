"""
Workspace Management Module

Provides CRUD operations for managing workspaces in the collaboration system.
Workspaces are shared environments where team members can collaborate on
specs, tasks, and runs with role-based access control.

Usage:
    from autoflow.collaboration.workspace import WorkspaceManager

    # Create a workspace manager
    manager = WorkspaceManager(".autoflow")
    manager.initialize()

    # Create a workspace
    workspace = manager.create_workspace(
        workspace_id="workspace-001",
        name="Project X",
        team_id="team-001",
        description="Main project workspace"
    )

    # Get a workspace
    workspace = manager.get_workspace("workspace-001")

    # List workspaces
    workspaces = manager.list_workspaces(team_id="team-001")

    # Update a workspace
    manager.update_workspace("workspace-001", description="Updated description")

    # Manage workspace members
    role = manager.add_member("workspace-001", "user-001", RoleType.ADMIN)
    members = manager.list_members("workspace-001")
    manager.update_member_role("workspace-001", "user-001", RoleType.MEMBER)
    manager.remove_member("workspace-001", "user-001")

    # Delete a workspace
    manager.delete_workspace("workspace-001")
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import ValidationError

from autoflow.collaboration.models import Role, RoleType, Workspace


class WorkspaceManager:
    """
    Manages workspaces for team collaboration.

    Provides CRUD operations for workspaces with persistent storage.
    Workspaces are shared environments where team members collaborate on
    specs, tasks, and runs with role-based access control.

    The WorkspaceManager uses the StateManager for persistent storage,
    storing workspace data in the workspaces/ directory within the state directory.

    Attributes:
        state_dir: Root directory for state storage
        workspaces_dir: Directory for workspace files
        state_manager: StateManager instance for low-level operations

    Example:
        >>> manager = WorkspaceManager(".autoflow")
        >>> manager.initialize()
        >>> workspace = manager.create_workspace(
        ...     workspace_id="workspace-001",
        ...     name="Project X",
        ...     team_id="team-001"
        ... )
        >>> print(workspace.name)
        Project X
    """

    def __init__(self, state_dir: Union[str, Path] = ".autoflow"):
        """
        Initialize the WorkspaceManager.

        Args:
            state_dir: Root directory for state storage.
                       Will be created if it doesn't exist.
        """
        self.state_dir = Path(state_dir).resolve()
        self.workspaces_dir = self.state_dir / "workspaces"
        self.roles_dir = self.state_dir / "workspace_roles"
        self.backup_dir = self.state_dir / "backups"

    def initialize(self) -> None:
        """
        Initialize the workspace directory structure.

        Creates the workspaces and roles directories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> manager = WorkspaceManager(".autoflow")
            >>> manager.initialize()
            >>> assert manager.workspaces_dir.exists()
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(exist_ok=True)
        self.roles_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

    def create_workspace(
        self,
        workspace_id: str,
        name: str,
        team_id: str,
        description: str = "",
        settings: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Workspace:
        """
        Create a new workspace.

        Args:
            workspace_id: Unique workspace identifier
            name: Workspace name
            team_id: Team ID that owns this workspace
            description: Workspace description
            settings: Workspace configuration settings
            metadata: Additional workspace data

        Returns:
            Created Workspace object

        Raises:
            ValueError: If workspace already exists or validation fails

        Example:
            >>> workspace = manager.create_workspace(
            ...     workspace_id="workspace-001",
            ...     name="Project X",
            ...     team_id="team-001",
            ...     description="Main project workspace"
            ... )
            >>> print(workspace.id)
            workspace-001
        """
        # Check if workspace already exists
        if self.get_workspace(workspace_id) is not None:
            raise ValueError(f"Workspace {workspace_id} already exists")

        # Create workspace object
        workspace = Workspace(
            id=workspace_id,
            name=name,
            description=description,
            team_id=team_id,
            settings=settings or {},
            metadata=metadata or {},
        )

        # Save to file
        self._save_workspace(workspace)
        return workspace

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """
        Get a workspace by ID.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Workspace object or None if not found

        Example:
            >>> workspace = manager.get_workspace("workspace-001")
            >>> if workspace:
            ...     print(workspace.name)
        """
        file_path = self.workspaces_dir / f"{workspace_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return Workspace(**data)
        except (json.JSONDecodeError, ValidationError, FileNotFoundError):
            return None

    def list_workspaces(
        self,
        team_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Workspace]:
        """
        List workspaces, optionally filtered by team.

        Args:
            team_id: Filter by team ID
            limit: Maximum number of workspaces to return

        Returns:
            List of Workspace objects

        Example:
            >>> workspaces = manager.list_workspaces(team_id="team-001")
            >>> for workspace in workspaces:
            ...     print(workspace.name)
        """
        workspaces = []
        if not self.workspaces_dir.exists():
            return workspaces

        for workspace_file in self.workspaces_dir.glob("*.json"):
            try:
                with open(workspace_file, encoding="utf-8") as f:
                    data = json.load(f)
                workspace = Workspace(**data)

                # Filter by team_id if provided
                if team_id and workspace.team_id != team_id:
                    continue

                workspaces.append(workspace)
            except (json.JSONDecodeError, ValidationError):
                continue

        # Sort by created_at descending
        workspaces.sort(key=lambda w: w.created_at, reverse=True)
        return workspaces[:limit]

    def update_workspace(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[Workspace]:
        """
        Update an existing workspace.

        Only updates the fields that are provided (partial update).
        The updated_at timestamp is automatically updated.

        Args:
            workspace_id: Workspace identifier
            name: New workspace name (optional)
            description: New description (optional)
            settings: New settings dict (optional)
            metadata: New metadata dict (optional)

        Returns:
            Updated Workspace object or None if not found

        Raises:
            ValueError: If validation fails

        Example:
            >>> workspace = manager.update_workspace(
            ...     "workspace-001",
            ...     description="Updated description"
            ... )
            >>> print(workspace.description)
            Updated description
        """
        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            return None

        # Update fields if provided
        if name is not None:
            workspace.name = name
        if description is not None:
            workspace.description = description
        if settings is not None:
            workspace.settings = settings
        if metadata is not None:
            workspace.metadata = metadata

        # Update timestamp
        workspace.touch()

        # Save changes
        self._save_workspace(workspace)
        return workspace

    def delete_workspace(self, workspace_id: str) -> bool:
        """
        Delete a workspace.

        Args:
            workspace_id: Workspace identifier

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = manager.delete_workspace("workspace-001")
            >>> if deleted:
            ...     print("Workspace deleted")
        """
        file_path = self.workspaces_dir / f"{workspace_id}.json"
        if file_path.exists():
            # Create backup before deletion
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    def workspace_exists(self, workspace_id: str) -> bool:
        """
        Check if a workspace exists.

        Args:
            workspace_id: Workspace identifier

        Returns:
            True if workspace exists, False otherwise

        Example:
            >>> if manager.workspace_exists("workspace-001"):
            ...     print("Workspace found")
        """
        return (self.workspaces_dir / f"{workspace_id}.json").exists()

    def get_workspace_count(self, team_id: Optional[str] = None) -> int:
        """
        Get the count of workspaces, optionally filtered by team.

        Args:
            team_id: Filter by team ID (optional)

        Returns:
            Number of workspaces

        Example:
            >>> count = manager.get_workspace_count(team_id="team-001")
            >>> print(f"Team has {count} workspaces")
        """
        return len(self.list_workspaces(team_id=team_id))

    def add_member(
        self,
        workspace_id: str,
        user_id: str,
        role_type: RoleType = RoleType.MEMBER,
        granted_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Role:
        """
        Add a member to a workspace with a specific role.

        Args:
            workspace_id: Workspace identifier
            user_id: User ID to add as a member
            role_type: Role to assign (default: MEMBER)
            granted_by: User ID who is granting this role (optional)
            expires_at: Optional expiration timestamp for the role
            metadata: Additional role data

        Returns:
            Created Role object

        Raises:
            ValueError: If workspace doesn't exist or user is already a member

        Example:
            >>> role = manager.add_member(
            ...     "workspace-001",
            ...     "user-001",
            ...     role_type=RoleType.ADMIN
            ... )
            >>> print(role.role_type)
            admin
        """
        # Check if workspace exists
        if not self.workspace_exists(workspace_id):
            raise ValueError(f"Workspace {workspace_id} does not exist")

        # Check if user is already a member
        if self.get_member_role(workspace_id, user_id) is not None:
            raise ValueError(
                f"User {user_id} is already a member of workspace {workspace_id}"
            )

        # Create role
        role = Role(
            user_id=user_id,
            role_type=role_type,
            workspace_id=workspace_id,
            granted_by=granted_by,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        # Save role
        self._save_role(role)
        return role

    def remove_member(self, workspace_id: str, user_id: str) -> bool:
        """
        Remove a member from a workspace.

        Args:
            workspace_id: Workspace identifier
            user_id: User ID to remove

        Returns:
            True if member was removed, False if not found

        Example:
            >>> removed = manager.remove_member("workspace-001", "user-001")
            >>> if removed:
            ...     print("Member removed")
        """
        role_file = self.roles_dir / f"{workspace_id}_{user_id}.json"
        if role_file.exists():
            # Create backup before deletion
            self._create_backup(role_file)
            role_file.unlink()
            return True
        return False

    def update_member_role(
        self,
        workspace_id: str,
        user_id: str,
        role_type: RoleType,
        granted_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Optional[Role]:
        """
        Update a member's role in a workspace.

        Args:
            workspace_id: Workspace identifier
            user_id: User ID whose role to update
            role_type: New role type
            granted_by: User ID who is granting this role (optional)
            expires_at: Optional expiration timestamp for the role

        Returns:
            Updated Role object or None if member not found

        Example:
            >>> role = manager.update_member_role(
            ...     "workspace-001",
            ...     "user-001",
            ...     role_type=RoleType.ADMIN
            ... )
            >>> print(role.role_type)
            admin
        """
        role = self.get_member_role(workspace_id, user_id)
        if role is None:
            return None

        # Update role
        role.role_type = role_type
        role.granted_by = granted_by
        role.expires_at = expires_at

        # Save changes
        self._save_role(role)
        return role

    def get_member_role(self, workspace_id: str, user_id: str) -> Optional[Role]:
        """
        Get a member's role in a workspace.

        Args:
            workspace_id: Workspace identifier
            user_id: User ID

        Returns:
            Role object or None if not found

        Example:
            >>> role = manager.get_member_role("workspace-001", "user-001")
            >>> if role:
            ...     print(role.role_type)
        """
        role_file = self.roles_dir / f"{workspace_id}_{user_id}.json"
        if not role_file.exists():
            return None

        try:
            with open(role_file, encoding="utf-8") as f:
                data = json.load(f)
            return Role(**data)
        except (json.JSONDecodeError, ValidationError, FileNotFoundError):
            return None

    def list_members(
        self,
        workspace_id: str,
        role_type: Optional[RoleType] = None,
    ) -> list[Role]:
        """
        List all members of a workspace, optionally filtered by role.

        Args:
            workspace_id: Workspace identifier
            role_type: Filter by role type (optional)

        Returns:
            List of Role objects representing workspace members

        Example:
            >>> members = manager.list_members("workspace-001")
            >>> for role in members:
            ...     print(f"{role.user_id}: {role.role_type}")
        """
        members = []
        if not self.roles_dir.exists():
            return members

        # Filter role files for this workspace
        pattern = f"{workspace_id}_*.json"
        for role_file in self.roles_dir.glob(pattern):
            try:
                with open(role_file, encoding="utf-8") as f:
                    data = json.load(f)
                role = Role(**data)

                # Filter by role_type if provided
                if role_type and role.role_type != role_type:
                    continue

                # Skip expired roles
                if role.is_expired():
                    continue

                members.append(role)
            except (json.JSONDecodeError, ValidationError):
                continue

        # Sort by granted_at descending
        members.sort(key=lambda r: r.granted_at, reverse=True)
        return members

    def is_member(self, workspace_id: str, user_id: str) -> bool:
        """
        Check if a user is a member of a workspace.

        Args:
            workspace_id: Workspace identifier
            user_id: User ID to check

        Returns:
            True if user is a member, False otherwise

        Example:
            >>> if manager.is_member("workspace-001", "user-001"):
            ...     print("User is a member")
        """
        role = self.get_member_role(workspace_id, user_id)
        return role is not None and not role.is_expired()

    def get_member_count(self, workspace_id: str) -> int:
        """
        Get the count of members in a workspace.

        Args:
            workspace_id: Workspace identifier

        Returns:
            Number of members in the workspace

        Example:
            >>> count = manager.get_member_count("workspace-001")
            >>> print(f"Workspace has {count} members")
        """
        return len(self.list_members(workspace_id))

    def _save_workspace(self, workspace: Workspace) -> Path:
        """
        Save a workspace to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.

        Args:
            workspace: Workspace object to save

        Returns:
            Path to the saved workspace file

        Raises:
            OSError: If write operation fails
        """
        file_path = self.workspaces_dir / f"{workspace.id}.json"

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(file_path)

        # Convert to dict for JSON serialization
        data = workspace.model_dump(mode="json")

        # Write to temporary file in same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, file_path)
            return file_path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _save_role(self, role: Role) -> Path:
        """
        Save a role to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.

        Args:
            role: Role object to save

        Returns:
            Path to the saved role file

        Raises:
            OSError: If write operation fails
        """
        file_path = self.roles_dir / f"{role.workspace_id}_{role.user_id}.json"

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(file_path)

        # Convert to dict for JSON serialization
        data = role.model_dump(mode="json")

        # Write to temporary file in same directory
        temp_fd, temp_path = tempfile.mkstemp(
            dir=file_path.parent,
            prefix=f".{file_path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, file_path)
            return file_path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.state_dir)
        return self.backup_dir / f"{relative}.bak"

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of an existing file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if file doesn't exist
        """
        if not file_path.exists():
            return None

        backup_path = self._get_backup_path(file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path
