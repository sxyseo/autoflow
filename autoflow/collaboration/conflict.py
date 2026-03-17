#!/usr/bin/env python3
"""
Autoflow Conflict Manager Module

Provides conflict detection and resolution for collaborative task editing.
Controls task locking, detects concurrent edits, and warns about potential
conflicts when multiple users work on the same task.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from autoflow.collaboration.models import EditSession, TaskLock


@dataclass
class ConflictConfig:
    """
    Configuration for conflict management.

    Args:
        lock_timeout_seconds: Default duration for task locks (default: 30 minutes)
        stale_lock_threshold: Age in seconds before considering a lock stale (default: 30 minutes)
        auto_release_stale: Whether to automatically release stale locks
        enable_edit_sessions: Whether to track detailed edit sessions
        edit_session_timeout: Seconds of inactivity before marking edit session as idle (default: 5 minutes)
    """
    lock_timeout_seconds: int = 1800  # 30 minutes
    stale_lock_threshold: int = 1800  # 30 minutes
    auto_release_stale: bool = True
    enable_edit_sessions: bool = True
    edit_session_timeout: int = 300  # 5 minutes

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "lock_timeout_seconds": self.lock_timeout_seconds,
            "stale_lock_threshold": self.stale_lock_threshold,
            "auto_release_stale": self.auto_release_stale,
            "enable_edit_sessions": self.enable_edit_sessions,
            "edit_session_timeout": self.edit_session_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ConflictConfig':
        """Create config from dictionary."""
        return cls(
            lock_timeout_seconds=data.get("lock_timeout_seconds", 1800),
            stale_lock_threshold=data.get("stale_lock_threshold", 1800),
            auto_release_stale=data.get("auto_release_stale", True),
            enable_edit_sessions=data.get("enable_edit_sessions", True),
            edit_session_timeout=data.get("edit_session_timeout", 300),
        )


class ConflictManager:
    """
    Conflict detection and resolution manager for collaborative task editing.

    Manages task locks to prevent concurrent editing conflicts, tracks active
    edit sessions, and provides conflict detection warnings when multiple users
    attempt to work on the same task.
    """

    def __init__(
        self,
        autoflow_dir: str = ".autoflow",
        config: Optional[ConflictConfig] = None
    ):
        """
        Initialize conflict manager.

        Args:
            autoflow_dir: Path to .autoflow directory
            config: Conflict manager configuration
        """
        self.autoflow_dir = Path(autoflow_dir)
        self.config = config or ConflictConfig()
        self.locks_dir = self.autoflow_dir / "locks"
        self.sessions_dir = self.autoflow_dir / "edit_sessions"

    def initialize(self) -> None:
        """
        Initialize the conflict manager storage directories.

        Creates the locks and edit sessions directories if they don't exist.
        """
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_lock_file_path(self, task_id: str) -> Path:
        """
        Get the file path for a task lock.

        Args:
            task_id: Task ID

        Returns:
            Path to the lock file
        """
        # Sanitize task_id to be safe as a filename
        safe_task_id = task_id.replace("/", "_").replace("\\", "_")
        return self.locks_dir / f"{safe_task_id}.lock.json"

    def _get_session_file_path(self, session_id: str) -> Path:
        """
        Get the file path for an edit session.

        Args:
            session_id: Session ID

        Returns:
            Path to the session file
        """
        safe_session_id = session_id.replace("/", "_").replace("\\", "_")
        return self.sessions_dir / f"{safe_session_id}.session.json"

    def _write_lock(self, lock: TaskLock) -> None:
        """
        Write a lock to disk atomically.

        Args:
            lock: TaskLock to write
        """
        lock_file = self._get_lock_file_path(lock.task_id)
        temp_file = lock_file.with_suffix(".tmp")

        lock_data = {
            "id": lock.id,
            "task_id": lock.task_id,
            "user_id": lock.user_id,
            "workspace_id": lock.workspace_id,
            "locked_at": lock.locked_at.isoformat(),
            "expires_at": lock.expires_at.isoformat() if lock.expires_at else None,
            "metadata": lock.metadata,
        }

        with open(temp_file, "w") as f:
            json.dump(lock_data, f, indent=2)

        temp_file.replace(lock_file)

    def _read_lock(self, task_id: str) -> Optional[TaskLock]:
        """
        Read a lock from disk.

        Args:
            task_id: Task ID

        Returns:
            TaskLock if exists and is valid, None otherwise
        """
        lock_file = self._get_lock_file_path(task_id)

        if not lock_file.exists():
            return None

        try:
            with open(lock_file, "r") as f:
                lock_data = json.load(f)

            # Parse dates
            locked_at = datetime.fromisoformat(lock_data["locked_at"])
            expires_at = None
            if lock_data.get("expires_at"):
                expires_at = datetime.fromisoformat(lock_data["expires_at"])

            lock = TaskLock(
                id=lock_data["id"],
                task_id=lock_data["task_id"],
                user_id=lock_data["user_id"],
                workspace_id=lock_data["workspace_id"],
                locked_at=locked_at,
                expires_at=expires_at,
                metadata=lock_data.get("metadata", {}),
            )

            # Check if lock is expired
            if not lock.is_valid():
                # Clean up expired lock
                lock_file.unlink()
                return None

            return lock

        except (json.JSONDecodeError, KeyError, ValueError):
            # Invalid lock file, remove it
            lock_file.unlink(missing_ok=True)
            return None

    def _write_session(self, session: EditSession) -> None:
        """
        Write an edit session to disk atomically.

        Args:
            session: EditSession to write
        """
        session_file = self._get_session_file_path(session.id)
        temp_file = session_file.with_suffix(".tmp")

        session_data = {
            "id": session.id,
            "task_id": session.task_id,
            "user_id": session.user_id,
            "workspace_id": session.workspace_id,
            "started_at": session.started_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "status": session.status,
            "idle_timeout_seconds": session.idle_timeout_seconds,
            "metadata": session.metadata,
        }

        with open(temp_file, "w") as f:
            json.dump(session_data, f, indent=2)

        temp_file.replace(session_file)

    def _read_session(self, session_id: str) -> Optional[EditSession]:
        """
        Read an edit session from disk.

        Args:
            session_id: Session ID

        Returns:
            EditSession if exists, None otherwise
        """
        session_file = self._get_session_file_path(session_id)

        if not session_file.exists():
            return None

        try:
            with open(session_file, "r") as f:
                session_data = json.load(f)

            session = EditSession(
                id=session_data["id"],
                task_id=session_data["task_id"],
                user_id=session_data["user_id"],
                workspace_id=session_data["workspace_id"],
                started_at=datetime.fromisoformat(session_data["started_at"]),
                last_activity=datetime.fromisoformat(session_data["last_activity"]),
                status=session_data["status"],
                idle_timeout_seconds=session_data.get("idle_timeout_seconds", 300),
                metadata=session_data.get("metadata", {}),
            )

            # Check if session is abandoned
            if session.is_abandoned():
                # Clean up abandoned session
                session_file.unlink()
                return None

            return session

        except (json.JSONDecodeError, KeyError, ValueError):
            # Invalid session file, remove it
            session_file.unlink(missing_ok=True)
            return None

    def try_lock(
        self,
        task_id: str,
        user_id: str,
        workspace_id: str,
        lock_type: str = "edit",
        duration_seconds: Optional[int] = None
    ) -> tuple[bool, Optional[TaskLock], Optional[str]]:
        """
        Attempt to acquire a lock on a task.

        Args:
            task_id: Task ID to lock
            user_id: User ID requesting the lock
            workspace_id: Workspace ID containing the task
            lock_type: Type of lock (edit, view)
            duration_seconds: Optional duration for the lock

        Returns:
            Tuple of (success, lock, conflict_message)
            - success: True if lock was acquired
            - lock: The acquired lock or existing lock if conflict
            - conflict_message: Human-readable conflict message if lock failed
        """
        # Ensure directories exist
        self.initialize()

        # Check for existing lock
        existing_lock = self._read_lock(task_id)
        if existing_lock:
            # Check if lock is held by same user
            if existing_lock.user_id == user_id:
                # Refresh the lock
                if duration_seconds:
                    existing_lock.refresh(duration_seconds)
                self._write_lock(existing_lock)
                return True, existing_lock, None

            # Check if existing lock is stale and auto-release is enabled
            if self.config.auto_release_stale and existing_lock.is_expired():
                # Remove expired lock and continue to acquire new lock
                self._get_lock_file_path(task_id).unlink(missing_ok=True)
                existing_lock = None
            else:
                # Lock held by different user and is still valid
                conflict_msg = (
                    f"Task {task_id} is currently locked by {existing_lock.user_id} "
                    f"since {existing_lock.locked_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return False, existing_lock, conflict_msg

        # Create new lock
        lock_duration = duration_seconds or self.config.lock_timeout_seconds
        expires_at = datetime.utcnow() + timedelta(seconds=lock_duration)

        lock = TaskLock(
            id=f"lock-{task_id}-{user_id}-{datetime.utcnow().timestamp()}",
            task_id=task_id,
            user_id=user_id,
            workspace_id=workspace_id,
            locked_at=datetime.utcnow(),
            expires_at=expires_at,
            metadata={"lock_type": lock_type}
        )

        self._write_lock(lock)

        # Create edit session if enabled
        if self.config.enable_edit_sessions:
            self.start_edit_session(
                task_id=task_id,
                user_id=user_id,
                workspace_id=workspace_id
            )

        return True, lock, None

    def release_lock(
        self,
        task_id: str,
        user_id: str
    ) -> bool:
        """
        Release a lock on a task.

        Args:
            task_id: Task ID to unlock
            user_id: User ID releasing the lock

        Returns:
            True if lock was released, False if lock didn't exist or user didn't hold it
        """
        lock = self._read_lock(task_id)
        if not lock:
            return False

        # Only allow the lock holder to release it
        if lock.user_id != user_id:
            return False

        # Remove lock file
        lock_file = self._get_lock_file_path(task_id)
        lock_file.unlink(missing_ok=True)

        # Complete associated edit sessions
        if self.config.enable_edit_sessions:
            self.complete_user_sessions(task_id, user_id)

        return True

    def get_lock(self, task_id: str) -> Optional[TaskLock]:
        """
        Get the current lock on a task.

        Args:
            task_id: Task ID

        Returns:
            TaskLock if task is locked, None otherwise
        """
        return self._read_lock(task_id)

    def get_active_editors(self, task_id: str) -> List[EditSession]:
        """
        Get all users actively editing a task.

        Args:
            task_id: Task ID

        Returns:
            List of active EditSession objects
        """
        if not self.config.enable_edit_sessions:
            return []

        active_sessions = []

        # Scan session directory for sessions related to this task
        if not self.sessions_dir.exists():
            return []

        for session_file in self.sessions_dir.glob("*.session.json"):
            try:
                with open(session_file, "r") as f:
                    session_data = json.load(f)

                if session_data.get("task_id") == task_id:
                    session = self._read_session(session_data["id"])
                    if session and session.is_active():
                        active_sessions.append(session)

            except (json.JSONDecodeError, KeyError):
                continue

        return active_sessions

    def detect_conflicts(
        self,
        task_id: str,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        Detect conflicts for a user trying to work on a task.

        Args:
            task_id: Task ID to check for conflicts
            user_id: User ID requesting to work on the task

        Returns:
            List of conflict dictionaries with type, message, and metadata
        """
        conflicts = []

        # Check for existing lock
        lock = self.get_lock(task_id)
        if lock and lock.user_id != user_id:
            time_remaining = "expired" if lock.is_expired() else "active"
            conflicts.append({
                "type": "lock_conflict",
                "message": (
                    f"Task is locked by {lock.user_id} "
                    f"(since {lock.locked_at.strftime('%Y-%m-%d %H:%M:%S')}, {time_remaining})"
                ),
                "held_by": lock.user_id,
                "locked_at": lock.locked_at.isoformat(),
                "expires_at": lock.expires_at.isoformat() if lock.expires_at else None,
                "severity": "high" if lock.is_valid() else "low",
            })

        # Check for active editors
        active_editors = self.get_active_editors(task_id)
        for session in active_editors:
            if session.user_id != user_id:
                idle_time = session.get_idle_time_seconds()
                conflicts.append({
                    "type": "active_editor",
                    "message": (
                        f"{session.user_id} is actively editing this task "
                        f"(idle for {int(idle_time)}s)"
                    ),
                    "editor": session.user_id,
                    "session_id": session.id,
                    "last_activity": session.last_activity.isoformat(),
                    "idle_time_seconds": idle_time,
                    "severity": "medium" if idle_time < 60 else "low",
                })

        return conflicts

    def has_conflict(self, task_id: str, user_id: str) -> bool:
        """
        Check if a user has any conflicts working on a task.

        Args:
            task_id: Task ID to check
            user_id: User ID to check for conflicts

        Returns:
            True if there are conflicts, False otherwise
        """
        conflicts = self.detect_conflicts(task_id, user_id)
        return len(conflicts) > 0

    def get_conflicting_users(self, task_id: str) -> List[str]:
        """
        Get list of users who would conflict with editing a task.

        Args:
            task_id: Task ID

        Returns:
            List of user IDs who would cause conflicts
        """
        conflicting_users = set()

        # Check lock holder
        lock = self.get_lock(task_id)
        if lock:
            conflicting_users.add(lock.user_id)

        # Check active editors
        active_editors = self.get_active_editors(task_id)
        for session in active_editors:
            conflicting_users.add(session.user_id)

        return list(conflicting_users)

    def start_edit_session(
        self,
        task_id: str,
        user_id: str,
        workspace_id: str,
        session_id: Optional[str] = None
    ) -> EditSession:
        """
        Start tracking an edit session for a user.

        Args:
            task_id: Task ID being edited
            user_id: User ID editing
            workspace_id: Workspace ID
            session_id: Optional session ID (auto-generated if not provided)

        Returns:
            The created EditSession
        """
        self.initialize()

        if session_id is None:
            session_id = f"session-{task_id}-{user_id}-{datetime.utcnow().timestamp()}"

        session = EditSession(
            id=session_id,
            task_id=task_id,
            user_id=user_id,
            workspace_id=workspace_id,
            started_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            status="active",
            idle_timeout_seconds=self.config.edit_session_timeout,
        )

        self._write_session(session)
        return session

    def record_activity(
        self,
        task_id: str,
        user_id: str
    ) -> Optional[EditSession]:
        """
        Record activity for a user's edit session on a task.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Updated EditSession if found, None otherwise
        """
        # Find the user's session for this task
        if not self.sessions_dir.exists():
            return None

        for session_file in self.sessions_dir.glob("*.session.json"):
            session = self._read_session(session_file.stem)
            if session and session.task_id == task_id and session.user_id == user_id:
                session.record_activity()
                self._write_session(session)
                return session

        return None

    def complete_user_sessions(
        self,
        task_id: str,
        user_id: str
    ) -> int:
        """
        Complete all sessions for a user on a task.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Number of sessions completed
        """
        completed_count = 0

        if not self.sessions_dir.exists():
            return 0

        for session_file in self.sessions_dir.glob("*.session.json"):
            session = self._read_session(session_file.stem)
            if session and session.task_id == task_id and session.user_id == user_id:
                session.complete()
                self._write_session(session)

                # Remove completed session file
                session_file.unlink(missing_ok=True)
                completed_count += 1

        return completed_count

    def cleanup_stale_locks(self) -> int:
        """
        Clean up expired locks.

        Returns:
            Number of locks cleaned up
        """
        cleaned_count = 0

        if not self.locks_dir.exists():
            return 0

        for lock_file in self.locks_dir.glob("*.lock.json"):
            try:
                with open(lock_file, "r") as f:
                    lock_data = json.load(f)

                expires_at = None
                if lock_data.get("expires_at"):
                    expires_at = datetime.fromisoformat(lock_data["expires_at"])

                # Check if expired
                if expires_at and datetime.utcnow() > expires_at:
                    lock_file.unlink()
                    cleaned_count += 1

            except (json.JSONDecodeError, ValueError, KeyError):
                # Invalid lock file, remove it
                lock_file.unlink(missing_ok=True)
                cleaned_count += 1

        return cleaned_count

    def cleanup_stale_sessions(self) -> int:
        """
        Clean up abandoned edit sessions.

        Returns:
            Number of sessions cleaned up
        """
        cleaned_count = 0

        if not self.sessions_dir.exists():
            return 0

        for session_file in self.sessions_dir.glob("*.session.json"):
            session = self._read_session(session_file.stem)
            if session is None:
                # Session was already removed during read if abandoned
                cleaned_count += 1

        return cleaned_count

    def get_all_locks(self) -> List[TaskLock]:
        """
        Get all active locks.

        Returns:
            List of all active TaskLock objects
        """
        locks = []

        if not self.locks_dir.exists():
            return []

        for lock_file in self.locks_dir.glob("*.lock.json"):
            lock = self._read_lock(lock_file.stem.replace(".lock", ""))
            if lock:
                locks.append(lock)

        return locks

    def get_all_sessions(self) -> List[EditSession]:
        """
        Get all active edit sessions.

        Returns:
            List of all active EditSession objects
        """
        sessions = []

        if not self.sessions_dir.exists():
            return []

        for session_file in self.sessions_dir.glob("*.session.json"):
            session = self._read_session(session_file.stem.replace(".session", ""))
            if session:
                sessions.append(session)

        return sessions
