"""
Team Management Module

Provides CRUD operations for managing teams in the collaboration system.
Teams are groups of users who collaborate on shared workspaces and tasks.

Usage:
    from autoflow.collaboration.team import TeamManager
    from autoflow.collaboration.models import RoleType

    # Create a team manager
    manager = TeamManager(".autoflow")
    manager.initialize()

    # Create a team
    team = manager.create_team(
        team_id="team-001",
        name="Engineering",
        description="Core engineering team"
    )

    # Get a team
    team = manager.get_team("team-001")

    # List teams
    teams = manager.list_teams()

    # Update a team
    manager.update_team("team-001", description="Updated description")

    # Manage team members
    role = manager.add_member("team-001", "user-001", RoleType.ADMIN)
    members = manager.list_members("team-001")
    manager.set_member_role("team-001", "user-001", RoleType.MEMBER)
    manager.remove_member("team-001", "user-001")

    # Delete a team
    manager.delete_team("team-001")
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

from autoflow.collaboration.models import Role, RoleType, Team


class TeamManager:
    """
    Manages teams for collaboration.

    Provides CRUD operations for teams with persistent storage.
    Teams are groups of users who can collaborate on shared workspaces.

    The TeamManager uses persistent storage, storing team data in the
    teams/ directory and team roles in the team_roles/ directory within the state directory.

    Attributes:
        state_dir: Root directory for state storage
        teams_dir: Directory for team files
        team_roles_dir: Directory for team role files
        backup_dir: Directory for backups

    Example:
        >>> manager = TeamManager(".autoflow")
        >>> manager.initialize()
        >>> team = manager.create_team(
        ...     team_id="team-001",
        ...     name="Engineering",
        ...     description="Core engineering team"
        ... )
        >>> print(team.name)
        Engineering
    """

    def __init__(self, state_dir: Union[str, Path] = ".autoflow"):
        """
        Initialize the TeamManager.

        Args:
            state_dir: Root directory for state storage.
                       Will be created if it doesn't exist.
        """
        self.state_dir = Path(state_dir).resolve()
        self.teams_dir = self.state_dir / "teams"
        self.team_roles_dir = self.state_dir / "team_roles"
        self.backup_dir = self.state_dir / "backups"

    def initialize(self) -> None:
        """
        Initialize the team directory structure.

        Creates the teams and team_roles directories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> manager = TeamManager(".autoflow")
            >>> manager.initialize()
            >>> assert manager.teams_dir.exists()
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.teams_dir.mkdir(exist_ok=True)
        self.team_roles_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

    def create_team(
        self,
        team_id: str,
        name: str,
        description: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Team:
        """
        Create a new team.

        Args:
            team_id: Unique team identifier
            name: Team name
            description: Team description
            metadata: Additional team data

        Returns:
            Created Team object

        Raises:
            ValueError: If team already exists or validation fails

        Example:
            >>> team = manager.create_team(
            ...     team_id="team-001",
            ...     name="Engineering",
            ...     description="Core engineering team"
            ... )
            >>> print(team.id)
            team-001
        """
        # Check if team already exists
        if self.get_team(team_id) is not None:
            raise ValueError(f"Team {team_id} already exists")

        # Create team object
        team = Team(
            id=team_id,
            name=name,
            description=description,
            metadata=metadata or {},
        )

        # Save to file
        self._save_team(team)
        return team

    def get_team(self, team_id: str) -> Optional[Team]:
        """
        Get a team by ID.

        Args:
            team_id: Team identifier

        Returns:
            Team object or None if not found

        Example:
            >>> team = manager.get_team("team-001")
            >>> if team:
            ...     print(team.name)
        """
        file_path = self.teams_dir / f"{team_id}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return Team(**data)
        except (json.JSONDecodeError, ValidationError, FileNotFoundError):
            return None

    def list_teams(
        self,
        limit: int = 100,
    ) -> list[Team]:
        """
        List all teams.

        Args:
            limit: Maximum number of teams to return

        Returns:
            List of Team objects

        Example:
            >>> teams = manager.list_teams()
            >>> for team in teams:
            ...     print(team.name)
        """
        teams = []
        if not self.teams_dir.exists():
            return teams

        for team_file in self.teams_dir.glob("*.json"):
            try:
                with open(team_file, encoding="utf-8") as f:
                    data = json.load(f)
                team = Team(**data)
                teams.append(team)
            except (json.JSONDecodeError, ValidationError):
                continue

        # Sort by created_at descending
        teams.sort(key=lambda t: t.created_at, reverse=True)
        return teams[:limit]

    def update_team(
        self,
        team_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[Team]:
        """
        Update an existing team.

        Only updates the fields that are provided (partial update).
        The updated_at timestamp is automatically updated.

        Args:
            team_id: Team identifier
            name: New team name (optional)
            description: New description (optional)
            metadata: New metadata dict (optional)

        Returns:
            Updated Team object or None if not found

        Raises:
            ValueError: If validation fails

        Example:
            >>> team = manager.update_team(
            ...     "team-001",
            ...     description="Updated description"
            ... )
            >>> print(team.description)
            Updated description
        """
        team = self.get_team(team_id)
        if team is None:
            return None

        # Update fields if provided
        if name is not None:
            team.name = name
        if description is not None:
            team.description = description
        if metadata is not None:
            team.metadata = metadata

        # Update timestamp
        team.touch()

        # Save changes
        self._save_team(team)
        return team

    def delete_team(self, team_id: str) -> bool:
        """
        Delete a team.

        Args:
            team_id: Team identifier

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = manager.delete_team("team-001")
            >>> if deleted:
            ...     print("Team deleted")
        """
        file_path = self.teams_dir / f"{team_id}.json"
        if file_path.exists():
            # Create backup before deletion
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    def team_exists(self, team_id: str) -> bool:
        """
        Check if a team exists.

        Args:
            team_id: Team identifier

        Returns:
            True if team exists, False otherwise

        Example:
            >>> if manager.team_exists("team-001"):
            ...     print("Team found")
        """
        return (self.teams_dir / f"{team_id}.json").exists()

    def get_team_count(self) -> int:
        """
        Get the total count of teams.

        Returns:
            Number of teams

        Example:
            >>> count = manager.get_team_count()
            >>> print(f"Total teams: {count}")
        """
        return len(self.list_teams())

    def add_member(
        self,
        team_id: str,
        user_id: str,
        role_type: RoleType = RoleType.MEMBER,
        granted_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Role:
        """
        Add a member to a team with a specific role.

        Args:
            team_id: Team identifier
            user_id: User ID to add as a member
            role_type: Role to assign (default: MEMBER)
            granted_by: User ID who is granting this role (optional)
            expires_at: Optional expiration timestamp for the role
            metadata: Additional role data

        Returns:
            Created Role object

        Raises:
            ValueError: If team doesn't exist or user is already a member

        Example:
            >>> role = manager.add_member(
            ...     "team-001",
            ...     "user-001",
            ...     role_type=RoleType.ADMIN
            ... )
            >>> print(role.role_type)
            admin
        """
        # Check if team exists
        if not self.team_exists(team_id):
            raise ValueError(f"Team {team_id} does not exist")

        # Check if user is already a member
        if self.get_member_role(team_id, user_id) is not None:
            raise ValueError(f"User {user_id} is already a member of team {team_id}")

        # Create role
        role = Role(
            user_id=user_id,
            role_type=role_type,
            team_id=team_id,
            granted_by=granted_by,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        # Save role
        self._save_role(role)

        # Update team member list
        team = self.get_team(team_id)
        if team:
            team.add_member(user_id)
            self._save_team(team)

        return role

    def remove_member(self, team_id: str, user_id: str) -> bool:
        """
        Remove a member from a team.

        Args:
            team_id: Team identifier
            user_id: User ID to remove

        Returns:
            True if member was removed, False if not found

        Example:
            >>> removed = manager.remove_member("team-001", "user-001")
            >>> if removed:
            ...     print("Member removed")
        """
        role_file = self.team_roles_dir / f"{team_id}_{user_id}.json"
        if role_file.exists():
            # Create backup before deletion
            self._create_backup(role_file)
            role_file.unlink()

            # Update team member list
            team = self.get_team(team_id)
            if team:
                team.remove_member(user_id)
                self._save_team(team)

            return True
        return False

    def set_member_role(
        self,
        team_id: str,
        user_id: str,
        role_type: RoleType,
        granted_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Optional[Role]:
        """
        Set a member's role in a team.

        Creates a new role if the user is not already a member.

        Args:
            team_id: Team identifier
            user_id: User ID whose role to set
            role_type: New role type
            granted_by: User ID who is granting this role (optional)
            expires_at: Optional expiration timestamp for the role

        Returns:
            Updated or created Role object, or None if team not found

        Example:
            >>> role = manager.set_member_role(
            ...     "team-001",
            ...     "user-001",
            ...     role_type=RoleType.ADMIN
            ... )
            >>> print(role.role_type)
            admin
        """
        # Check if team exists
        if not self.team_exists(team_id):
            return None

        # Get existing role or create new one
        role = self.get_member_role(team_id, user_id)

        if role is None:
            # User is not yet a member, add them
            return self.add_member(team_id, user_id, role_type, granted_by, expires_at)

        # Update existing role
        role.role_type = role_type
        role.granted_by = granted_by
        role.expires_at = expires_at

        # Save changes
        self._save_role(role)
        return role

    def get_member_role(self, team_id: str, user_id: str) -> Optional[Role]:
        """
        Get a member's role in a team.

        Args:
            team_id: Team identifier
            user_id: User ID

        Returns:
            Role object or None if not found

        Example:
            >>> role = manager.get_member_role("team-001", "user-001")
            >>> if role:
            ...     print(role.role_type)
        """
        role_file = self.team_roles_dir / f"{team_id}_{user_id}.json"
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
        team_id: str,
        role_type: Optional[RoleType] = None,
    ) -> list[Role]:
        """
        List all members of a team, optionally filtered by role.

        Args:
            team_id: Team identifier
            role_type: Filter by role type (optional)

        Returns:
            List of Role objects representing team members

        Example:
            >>> members = manager.list_members("team-001")
            >>> for role in members:
            ...     print(f"{role.user_id}: {role.role_type}")
        """
        members = []
        if not self.team_roles_dir.exists():
            return members

        # Filter role files for this team
        pattern = f"{team_id}_*.json"
        for role_file in self.team_roles_dir.glob(pattern):
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

    def is_member(self, team_id: str, user_id: str) -> bool:
        """
        Check if a user is a member of a team.

        Args:
            team_id: Team identifier
            user_id: User ID to check

        Returns:
            True if user is a member, False otherwise

        Example:
            >>> if manager.is_member("team-001", "user-001"):
            ...     print("User is a member")
        """
        role = self.get_member_role(team_id, user_id)
        return role is not None and not role.is_expired()

    def get_member_count(self, team_id: str) -> int:
        """
        Get the count of members in a team.

        Args:
            team_id: Team identifier

        Returns:
            Number of members in the team

        Example:
            >>> count = manager.get_member_count("team-001")
            >>> print(f"Team has {count} members")
        """
        return len(self.list_members(team_id))

    def _save_team(self, team: Team) -> Path:
        """
        Save a team to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.

        Args:
            team: Team object to save

        Returns:
            Path to the saved team file

        Raises:
            OSError: If write operation fails
        """
        file_path = self.teams_dir / f"{team.id}.json"

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(file_path)

        # Convert to dict for JSON serialization
        data = team.model_dump(mode="json")

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
        file_path = self.team_roles_dir / f"{role.team_id}_{role.user_id}.json"

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
