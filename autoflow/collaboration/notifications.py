"""
Autoflow Notification Management Module

Provides notification system for alerting team members about relevant events
such as review requests, mentions, and workspace updates. Implements crash-safe
file operations using write-to-temp and rename pattern.

Usage:
    from autoflow.collaboration.notifications import NotificationManager

    # Using the NotificationManager
    manager = NotificationManager(".autoflow")
    manager.initialize()

    # Create and send a notification
    notification = manager.create_notification(
        user_id="user-001",
        notification_type=NotificationType.REVIEW_REQUEST,
        title="Review Requested",
        message="Please review task-001",
        workspace_id="workspace-001"
    )
    manager.send_notification(notification.id)

    # Get user's notifications
    notifications = manager.get_user_notifications("user-001")
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import ValidationError

from autoflow.collaboration.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)


class NotificationManager:
    """
    Manages notifications for team collaboration.

    Provides atomic file operations with crash safety using the
    write-to-temporary-and-rename pattern. Notifications are organized
    by recipient user for efficient querying.

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        notifications_dir: Root directory for notification storage
        backup_dir: Directory for backup files

    Example:
        >>> manager = NotificationManager(".autoflow")
        >>> manager.initialize()
        >>> notification = manager.create_notification(
        ...     user_id="user-001",
        ...     notification_type=NotificationType.REVIEW_REQUEST,
        ...     title="Review Requested",
        ...     message="Please review task-001"
        ... )
        >>> manager.send_notification(notification.id)
    """

    # Subdirectories within notifications directory
    NOTIFICATIONS_DIR = "notifications"
    BACKUP_DIR = "backups"

    def __init__(self, state_dir: Union[str, Path]):
        """
        Initialize the NotificationManager.

        Args:
            state_dir: Root directory for state storage.
                       Notifications will be stored in state_dir/notifications/
        """
        self.state_dir = Path(state_dir).resolve()
        self._notifications_dir = self.state_dir / self.NOTIFICATIONS_DIR
        self._backup_dir = self._notifications_dir / self.BACKUP_DIR

    @property
    def notifications_dir(self) -> Path:
        """Path to notifications directory."""
        return self._notifications_dir

    @property
    def backup_dir(self) -> Path:
        """Path to backup directory."""
        return self._backup_dir

    def initialize(self) -> None:
        """
        Initialize the notification directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> manager = NotificationManager(".autoflow")
            >>> manager.initialize()
            >>> assert manager.notifications_dir.exists()
        """
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_dir(self, user_id: str) -> Path:
        """
        Get the directory for a user's notifications.

        Args:
            user_id: User ID

        Returns:
            Path to the user's notification directory
        """
        return self.notifications_dir / user_id

    def _get_notification_path(self, notification_id: str, user_id: str) -> Path:
        """
        Get the file path for a notification.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Path to the notification file
        """
        return self._get_user_dir(user_id) / f"{notification_id}.json"

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.notifications_dir)
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

    def _write_json(
        self,
        file_path: Path,
        data: dict[str, Any],
        indent: int = 2,
    ) -> Path:
        """
        Write JSON data to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.
        Either the write completes successfully or the file remains unchanged.

        Args:
            file_path: Path to the file to write
            data: Dictionary to write as JSON
            indent: JSON indentation level

        Returns:
            Path to the written file

        Raises:
            IOError: If write operation fails
        """
        # Create parent directory if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file
        fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=".",
            dir=file_path.parent,
        )

        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=indent, default=str)

            # Atomic rename to final location
            os.replace(temp_path, file_path)
            return file_path

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise IOError(f"Failed to write {file_path}: {e}") from e

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        """
        Read JSON data from a file.

        Args:
            file_path: Path to the file to read

        Returns:
            Dictionary containing the JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file contains invalid JSON
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}") from e

    def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        workspace_id: Optional[str] = None,
        team_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Notification:
        """
        Create a new notification.

        Args:
            user_id: User ID to notify
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            workspace_id: Workspace ID associated with notification
            team_id: Team ID associated with notification
            expires_at: Optional expiration timestamp
            metadata: Additional notification data

        Returns:
            Created notification object

        Raises:
            ValueError: If notification creation fails

        Example:
            >>> notification = manager.create_notification(
            ...     user_id="user-001",
            ...     notification_type=NotificationType.REVIEW_REQUEST,
            ...     title="Review Requested",
            ...     message="Please review task-001"
            ... )
            >>> print(notification.id)
            notif-xxx
        """
        notification_id = f"notif-{uuid4().hex[:8]}"

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            workspace_id=workspace_id,
            team_id=team_id,
            status=NotificationStatus.PENDING,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            metadata=metadata or {},
        )

        # Save to file
        notification_path = self._get_notification_path(notification_id, user_id)
        self._write_json(notification_path, notification.dict())

        return notification

    def send_notification(self, notification_id: str, user_id: str) -> Notification:
        """
        Send a notification (mark as sent).

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Updated notification

        Raises:
            FileNotFoundError: If notification doesn't exist

        Example:
            >>> notification = manager.send_notification("notif-001", "user-001")
            >>> print(notification.status)
            sent
        """
        notification = self.get_notification(notification_id, user_id)
        notification.status = NotificationStatus.SENT

        # Save updated status
        notification_path = self._get_notification_path(notification_id, user_id)
        self._write_json(notification_path, notification.dict())

        return notification

    def deliver_notification(self, notification_id: str, user_id: str) -> Notification:
        """
        Mark a notification as delivered.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Updated notification

        Raises:
            FileNotFoundError: If notification doesn't exist

        Example:
            >>> notification = manager.deliver_notification("notif-001", "user-001")
            >>> print(notification.status)
            delivered
        """
        notification = self.get_notification(notification_id, user_id)
        notification.status = NotificationStatus.DELIVERED

        # Save updated status
        notification_path = self._get_notification_path(notification_id, user_id)
        self._write_json(notification_path, notification.dict())

        return notification

    def mark_as_read(self, notification_id: str, user_id: str) -> Notification:
        """
        Mark a notification as read.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Updated notification

        Raises:
            FileNotFoundError: If notification doesn't exist

        Example:
            >>> notification = manager.mark_as_read("notif-001", "user-001")
            >>> print(notification.status)
            read
        """
        notification = self.get_notification(notification_id, user_id)
        notification.mark_as_read()

        # Save updated status
        notification_path = self._get_notification_path(notification_id, user_id)
        self._write_json(notification_path, notification.dict())

        return notification

    def dismiss_notification(self, notification_id: str, user_id: str) -> Notification:
        """
        Dismiss a notification.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Updated notification

        Raises:
            FileNotFoundError: If notification doesn't exist

        Example:
            >>> notification = manager.dismiss_notification("notif-001", "user-001")
            >>> print(notification.status)
            dismissed
        """
        notification = self.get_notification(notification_id, user_id)
        notification.status = NotificationStatus.DISMISSED

        # Save updated status
        notification_path = self._get_notification_path(notification_id, user_id)
        self._write_json(notification_path, notification.dict())

        return notification

    def get_notification(self, notification_id: str, user_id: str) -> Notification:
        """
        Get a specific notification.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            Notification object

        Raises:
            FileNotFoundError: If notification doesn't exist
            ValidationError: If notification data is invalid

        Example:
            >>> notification = manager.get_notification("notif-001", "user-001")
            >>> print(notification.title)
            Review Requested
        """
        notification_path = self._get_notification_path(notification_id, user_id)
        data = self._read_json(notification_path)

        try:
            return Notification(**data)
        except ValidationError as e:
            raise ValidationError(f"Invalid notification data: {e}") from e

    def get_user_notifications(
        self,
        user_id: str,
        status: Optional[NotificationStatus] = None,
        notification_type: Optional[NotificationType] = None,
        include_expired: bool = False,
        limit: Optional[int] = None,
    ) -> list[Notification]:
        """
        Get notifications for a user.

        Args:
            user_id: User ID to get notifications for
            status: Optional status filter
            notification_type: Optional type filter
            include_expired: Whether to include expired notifications
            limit: Optional maximum number of notifications to return

        Returns:
            List of notifications, sorted by creation time (newest first)

        Example:
            >>> notifications = manager.get_user_notifications("user-001")
            >>> len(notifications)
            5
            >>> notifications = manager.get_user_notifications(
            ...     "user-001",
            ...     status=NotificationStatus.UNREAD
            ... )
        """
        user_dir = self._get_user_dir(user_id)

        if not user_dir.exists():
            return []

        notifications = []

        for notification_file in user_dir.glob("*.json"):
            try:
                data = self._read_json(notification_file)
                notification = Notification(**data)

                # Filter by status
                if status and notification.status != status:
                    continue

                # Filter by type
                if notification_type and notification.notification_type != notification_type:
                    continue

                # Filter expired
                if not include_expired and notification.is_expired():
                    continue

                notifications.append(notification)

            except (ValidationError, ValueError):
                # Skip invalid notifications
                continue

        # Sort by creation time (newest first)
        notifications.sort(key=lambda n: n.created_at, reverse=True)

        # Apply limit
        if limit is not None:
            notifications = notifications[:limit]

        return notifications

    def get_unread_notifications(
        self,
        user_id: str,
        limit: Optional[int] = None,
    ) -> list[Notification]:
        """
        Get unread notifications for a user.

        Args:
            user_id: User ID to get notifications for
            limit: Optional maximum number of notifications to return

        Returns:
            List of unread notifications

        Example:
            >>> notifications = manager.get_unread_notifications("user-001")
            >>> len(notifications)
            3
        """
        return self.get_user_notifications(
            user_id,
            status=NotificationStatus.DELIVERED,
            limit=limit,
        )

    def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """
        Delete a notification.

        Args:
            notification_id: Notification ID
            user_id: User ID who owns the notification

        Returns:
            True if notification was deleted, False if not found

        Example:
            >>> success = manager.delete_notification("notif-001", "user-001")
            >>> print(success)
            True
        """
        notification_path = self._get_notification_path(notification_id, user_id)

        if not notification_path.exists():
            return False

        # Create backup before deletion
        self._create_backup(notification_path)

        # Delete the file
        notification_path.unlink()
        return True

    def delete_expired_notifications(self, user_id: str) -> int:
        """
        Delete all expired notifications for a user.

        Args:
            user_id: User ID to clean up notifications for

        Returns:
            Number of notifications deleted

        Example:
            >>> count = manager.delete_expired_notifications("user-001")
            >>> print(f"Deleted {count} expired notifications")
        """
        notifications = self.get_user_notifications(user_id, include_expired=True)
        deleted_count = 0

        for notification in notifications:
            if notification.is_expired():
                if self.delete_notification(notification.id, user_id):
                    deleted_count += 1

        return deleted_count

    def cleanup_old_notifications(
        self,
        user_id: str,
        older_than_days: int = 30,
    ) -> int:
        """
        Delete old read/dismissed notifications for a user.

        Args:
            user_id: User ID to clean up notifications for
            older_than_days: Delete notifications older than this many days

        Returns:
            Number of notifications deleted

        Example:
            >>> count = manager.cleanup_old_notifications("user-001", older_than_days=30)
            >>> print(f"Deleted {count} old notifications")
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        notifications = self.get_user_notifications(user_id)
        deleted_count = 0

        for notification in notifications:
            if (
                notification.status
                in (NotificationStatus.READ, NotificationStatus.DISMISSED)
                and notification.created_at < cutoff_date
            ):
                if self.delete_notification(notification.id, user_id):
                    deleted_count += 1

        return deleted_count
