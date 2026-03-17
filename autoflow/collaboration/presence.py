"""
Autoflow Presence Tracking Module

Provides presence tracking system that monitors user activity and online status
for real-time collaboration awareness. Implements crash-safe file operations using
write-to-temp and rename pattern.

Usage:
    from autoflow.collaboration.presence import PresenceTracker

    # Using the PresenceTracker
    tracker = PresenceTracker(".autoflow")
    tracker.initialize()
    tracker.update_presence(
        user_id="user-001",
        workspace_id="workspace-001",
        current_task="task-001"
    )

    # Get online users
    online_users = tracker.get_online_users("workspace-001")
    for user in online_users:
        print(f"{user.user_id} is {user.status}")
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import ValidationError

from autoflow.collaboration.models import (
    PresenceStatus,
    UserPresence,
)


class PresenceTracker:
    """
    Manages presence tracking for real-time collaboration.

    Provides atomic file operations with crash safety using the
    write-to-temporary-and-rename pattern. Presence records are stored
    per-user in the presence directory for efficient querying.

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        presence_dir: Root directory for presence storage
        backup_dir: Directory for backup files
        default_timeout_seconds: Default timeout for considering users offline

    Example:
        >>> tracker = PresenceTracker(".autoflow")
        >>> tracker.initialize()
        >>> tracker.update_presence(
        ...     user_id="user-001",
        ...     workspace_id="workspace-001",
        ...     current_task="task-001"
        ... )
    """

    # Subdirectories within state directory
    PRESENCE_DIR = "presence"
    BACKUP_DIR = "backups"

    # Default timeout for considering users offline (5 minutes)
    DEFAULT_TIMEOUT_SECONDS = 300

    def __init__(
        self,
        state_dir: Union[str, Path],
        default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """
        Initialize the PresenceTracker.

        Args:
            state_dir: Root directory for state storage.
                      Presence will be stored in state_dir/presence/
            default_timeout_seconds: Seconds of inactivity before marking user offline
        """
        self.state_dir = Path(state_dir).resolve()
        self._presence_dir = self.state_dir / self.PRESENCE_DIR
        self._backup_dir = self._presence_dir / self.BACKUP_DIR
        self.default_timeout_seconds = default_timeout_seconds

    @property
    def presence_dir(self) -> Path:
        """Path to presence directory."""
        return self._presence_dir

    @presence_dir.setter
    def presence_dir(self, value: Path) -> None:
        """Set presence directory and create parent structure."""
        self._presence_dir = value

    def initialize(self) -> None:
        """
        Initialize the presence directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> tracker = PresenceTracker(".autoflow")
            >>> tracker.initialize()
            >>> assert tracker.presence_dir.exists()
        """
        self.presence_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @property
    def backup_dir(self) -> Path:
        """Path to backup directory."""
        return self._backup_dir

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.presence_dir)
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
        import shutil

        shutil.copy2(file_path, backup_path)
        return backup_path

    def _write_json(
        self,
        file_path: Path,
        data: dict[str, Any],
        indent: int = 2,
    ) -> Path:
        """
        Write JSON data to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.
        Creates parent directories if needed.

        Args:
            file_path: Destination path
            data: JSON-serializable data
            indent: Indentation level for pretty printing

        Returns:
            Path to the written file

        Raises:
            OSError: If write operation fails
        """
        path = file_path.resolve()

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(path)

        # Write to temporary file in same directory (ensures same filesystem)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, path)
            return path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _read_json(
        self,
        file_path: Path,
        default: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Read JSON data from a file.

        Args:
            file_path: Path to the JSON file
            default: Default value if file doesn't exist or is invalid

        Returns:
            Parsed JSON data or default value

        Raises:
            ValueError: If file contains invalid JSON and no default provided
        """
        if not file_path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            if default is not None:
                return default
            raise ValueError(f"Invalid JSON in {file_path}: {e}") from e

    def _get_presence_path(self, user_id: str) -> Path:
        """
        Get the file path for a user's presence record.

        Args:
            user_id: User identifier

        Returns:
            Path to the presence file
        """
        return self.presence_dir / f"{user_id}.json"

    # === Presence Management Methods ===

    def update_presence(
        self,
        user_id: str,
        workspace_id: Optional[str] = None,
        current_task: Optional[str] = None,
        status: PresenceStatus = PresenceStatus.ONLINE,
        status_message: str = "",
        team_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UserPresence:
        """
        Update a user's presence information.

        Creates or updates a user's presence record with the provided information.
        Sets the user's status to online and updates the last_seen timestamp.

        Args:
            user_id: User ID to update presence for
            workspace_id: Optional workspace ID where user is active
            current_task: Optional task ID the user is working on
            status: Presence status (default: online)
            status_message: Optional custom status message
            team_id: Optional team ID associated with the user
            metadata: Additional presence data

        Returns:
            The updated UserPresence object

        Example:
            >>> presence = tracker.update_presence(
            ...     user_id="user-001",
            ...     workspace_id="workspace-001",
            ...     current_task="task-001"
            ... )
            >>> print(f"{presence.user_id} is {presence.status}")
            user-001 is online
        """
        presence = UserPresence(
            user_id=user_id,
            status=status,
            workspace_id=workspace_id,
            team_id=team_id,
            last_seen=datetime.utcnow(),
            status_message=status_message,
            metadata=metadata or {},
        )

        # Store current task in metadata if provided
        if current_task:
            presence.metadata["current_task"] = current_task

        # Save presence to file
        presence_path = self._get_presence_path(user_id)
        self._write_json(presence_path, presence.model_dump(mode="json"))

        return presence

    def get_presence(self, user_id: str) -> Optional[UserPresence]:
        """
        Get a user's presence information.

        Args:
            user_id: User ID to get presence for

        Returns:
            UserPresence object if found, None otherwise

        Example:
            >>> presence = tracker.get_presence("user-001")
            >>> if presence:
            ...     print(f"{presence.user_id} is {presence.status}")
        """
        presence_path = self._get_presence_path(user_id)
        data = self._read_json(presence_path, default=None)

        if data is None:
            return None

        try:
            return UserPresence(**data)
        except ValidationError:
            return None

    def get_all_presences(self) -> dict[str, UserPresence]:
        """
        Get all user presence records.

        Returns:
            Dictionary mapping user IDs to their UserPresence objects

        Example:
            >>> presences = tracker.get_all_presences()
            >>> for user_id, presence in presences.items():
            ...     print(f"{user_id}: {presence.status}")
        """
        presences = {}

        if not self.presence_dir.exists():
            return presences

        for presence_file in self.presence_dir.glob("*.json"):
            user_id = presence_file.stem
            data = self._read_json(presence_file, default=None)

            if data is not None:
                try:
                    presences[user_id] = UserPresence(**data)
                except ValidationError:
                    # Skip invalid records
                    continue

        return presences

    def get_online_users(
        self,
        workspace_id: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> list[UserPresence]:
        """
        Get users who are currently online.

        Args:
            workspace_id: Optional workspace ID to filter by
            timeout_seconds: Optional timeout for considering users online.
                            If None, uses default_timeout_seconds.

        Returns:
            List of UserPresence objects for online users

        Example:
            >>> online_users = tracker.get_online_users("workspace-001")
            >>> for user in online_users:
            ...     print(f"{user.user_id} is online")
        """
        timeout = timeout_seconds or self.default_timeout_seconds
        all_presences = self.get_all_presences()
        online_users = []

        for presence in all_presences.values():
            # Filter by workspace if specified
            if workspace_id and presence.workspace_id != workspace_id:
                continue

            # Check if user is active
            if presence.is_active(timeout_seconds=timeout):
                online_users.append(presence)

        return online_users

    def get_idle_users(
        self,
        timeout_seconds: Optional[int] = None,
    ) -> list[UserPresence]:
        """
        Get users who are idle (inactive but not offline).

        Args:
            timeout_seconds: Optional timeout for considering users idle.
                            If None, uses default_timeout_seconds.

        Returns:
            List of UserPresence objects for idle users

        Example:
            >>> idle_users = tracker.get_idle_users()
            >>> for user in idle_users:
            ...     print(f"{user.user_id} is idle")
        """
        timeout = timeout_seconds or self.default_timeout_seconds
        all_presences = self.get_all_presences()
        idle_users = []

        for presence in all_presences.values():
            # Check if user is offline
            if presence.status == PresenceStatus.OFFLINE:
                continue

            # Check if user has been inactive
            if not presence.is_active(timeout_seconds=timeout):
                idle_users.append(presence)

        return idle_users

    def mark_offline(self, user_id: str) -> Optional[UserPresence]:
        """
        Mark a user as offline.

        Args:
            user_id: User ID to mark offline

        Returns:
            The updated UserPresence object, or None if user not found

        Example:
            >>> presence = tracker.mark_offline("user-001")
            >>> if presence:
            ...     print(f"{presence.user_id} is now offline")
        """
        presence = self.get_presence(user_id)
        if presence is None:
            return None

        presence.set_offline()

        # Save updated presence
        presence_path = self._get_presence_path(user_id)
        self._write_json(presence_path, presence.model_dump(mode="json"))

        return presence

    def cleanup_expired_presences(
        self,
        timeout_seconds: Optional[int] = None,
    ) -> int:
        """
        Remove presence records for users who have been offline too long.

        Args:
            timeout_seconds: Optional timeout for considering presences expired.
                            If None, uses 2x default_timeout_seconds.

        Returns:
            Number of presence records removed

        Example:
            >>> removed = tracker.cleanup_expired_presences()
            >>> print(f"Cleaned up {removed} expired presences")
        """
        timeout = timeout_seconds or (self.default_timeout_seconds * 2)
        all_presences = self.get_all_presences()
        removed_count = 0

        for user_id, presence in all_presences.items():
            # Check if user has been offline for too long
            if presence.status == PresenceStatus.OFFLINE:
                time_since_last_seen = datetime.utcnow() - presence.last_seen
                if time_since_last_seen.total_seconds() > timeout:
                    # Remove the presence file
                    presence_path = self._get_presence_path(user_id)
                    if presence_path.exists():
                        presence_path.unlink()
                        removed_count += 1

        return removed_count

    def get_users_by_task(
        self,
        task_id: str,
    ) -> list[UserPresence]:
        """
        Get users who are currently working on a specific task.

        Args:
            task_id: Task ID to search for

        Returns:
            List of UserPresence objects for users working on the task

        Example:
            >>> users = tracker.get_users_by_task("task-001")
            >>> for user in users:
            ...     print(f"{user.user_id} is working on task-001")
        """
        all_presences = self.get_all_presences()
        task_users = []

        for presence in all_presences.values():
            current_task = presence.metadata.get("current_task")
            if current_task == task_id:
                task_users.append(presence)

        return task_users
