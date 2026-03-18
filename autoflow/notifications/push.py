"""
Autoflow Push Notification Service

Provides push notification management for mobile devices with support for
multiple providers (Firebase, mock, etc.). Implements crash-safe file
operations using write-to-temp and rename pattern.

Usage:
    from autoflow.notifications.push import PushNotificationService

    # Initialize service
    service = PushNotificationService(".autoflow")
    service.initialize()

    # Register device token
    service.register_device_token(
        user_id="user-001",
        device_token="firebase-token",
        platform="ios"
    )

    # Send notification
    notification = PushNotification(
        title="Task Completed",
        body="Your task has been completed successfully",
        data={"task_id": "task-001"}
    )
    service.send_notification("user-001", notification)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from autoflow.notifications.providers import (
    FirebaseProvider,
    MockProvider,
    ProviderPriority,
    PushProvider,
    PushResult,
)


class PushNotificationType(str, Enum):
    """Types of push notifications."""

    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_ASSIGNED = "task_assigned"
    AGENT_ATTENTION = "agent_attention"
    AGENT_ERROR = "agent_error"
    REVIEW_REQUEST = "review_request"
    REVIEW_APPROVED = "review_approved"
    REVIEW_REJECTED = "review_rejected"
    SYSTEM_ANNOUNCEMENT = "system_announcement"
    DAILY_SUMMARY = "daily_summary"


class DeviceInfo(BaseModel):
    """
    Information about a registered mobile device.

    Attributes:
        device_id: Unique device identifier
        user_id: ID of the user who owns this device
        device_name: Human-readable device name
        platform: Platform type (ios or android)
        push_token: Push notification service token
        app_version: Mobile app version
        registered_at: Registration timestamp
        last_active: Last activity timestamp
        enabled: Whether push notifications are enabled for this device
    """

    device_id: str
    user_id: str
    device_name: str
    platform: str
    push_token: str
    app_version: str
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    enabled: bool = True


class PushNotification(BaseModel):
    """
    Push notification message.

    Attributes:
        title: Notification title
        body: Notification body text
        notification_type: Type of notification
        data: Optional additional data payload
        priority: Notification priority level
        badge: Optional badge count for iOS
        sound: Sound to play (default for default sound)
    """

    title: str
    body: str
    notification_type: Optional[PushNotificationType] = None
    data: dict[str, Any] = Field(default_factory=dict)
    priority: ProviderPriority = ProviderPriority.NORMAL
    badge: Optional[int] = None
    sound: str = "default"


class PushNotificationService:
    """
    Service for managing push notifications to mobile devices.

    Provides device token management, notification sending, and integration
    with multiple push notification providers. Uses atomic file operations
    for crash-safe persistence.

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        state_dir: Root directory for state storage
        devices_dir: Directory for device registrations
        provider: Push notification provider to use

    Example:
        >>> service = PushNotificationService(".autoflow")
        >>> service.initialize()
        >>> service.register_device_token(
        ...     "user-001",
        ...     "firebase-token",
        ...     "ios"
        ... )
        >>> notification = PushNotification(
        ...     title="Task Completed",
        ...     body="Your task is done"
        ... )
        >>> await service.send_notification("user-001", notification)
    """

    # Subdirectories within state directory
    DEVICES_DIR = "devices"
    BACKUP_DIR = "backups"

    def __init__(
        self,
        state_dir: Union[str, Path],
        provider: Optional[PushProvider] = None,
    ):
        """
        Initialize the PushNotificationService.

        Args:
            state_dir: Root directory for state storage
            provider: Optional custom push notification provider
        """
        self.state_dir = Path(state_dir).resolve()
        self._devices_dir = self.state_dir / self.DEVICES_DIR
        self._backup_dir = self._devices_dir / self.BACKUP_DIR

        # Initialize provider (default to MockProvider for safety)
        if provider is None:
            self.provider = MockProvider()
        else:
            self.provider = provider

    @property
    def devices_dir(self) -> Path:
        """Path to devices directory."""
        return self._devices_dir

    @property
    def backup_dir(self) -> Path:
        """Path to backup directory."""
        return self._backup_dir

    def initialize(self) -> None:
        """
        Initialize the push notification service.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> service = PushNotificationService(".autoflow")
            >>> service.initialize()
            >>> assert service.devices_dir.exists()
        """
        self.devices_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_devices_path(self, user_id: str) -> Path:
        """
        Get the file path for a user's devices.

        Args:
            user_id: User ID

        Returns:
            Path to the user's devices file
        """
        return self.devices_dir / f"{user_id}.json"

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.devices_dir)
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
            return {"devices": []}

        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}") from e

    def register_device_token(
        self,
        user_id: str,
        push_token: str,
        platform: str,
        device_name: Optional[str] = None,
        app_version: str = "1.0.0",
    ) -> DeviceInfo:
        """
        Register a device token for push notifications.

        Args:
            user_id: User ID who owns this device
            push_token: Push notification service token
            platform: Platform type (ios or android)
            device_name: Optional human-readable device name
            app_version: Mobile app version

        Returns:
            Created or updated DeviceInfo

        Raises:
            ValueError: If input is invalid

        Example:
            >>> device = service.register_device_token(
            ...     "user-001",
            ...     "firebase-token",
            ...     "ios",
            ...     device_name="John's iPhone"
            ... )
            >>> print(device.device_id)
            device-xxx
        """
        if platform not in ("ios", "android"):
            raise ValueError(f"Invalid platform: {platform}")

        # Generate device ID
        device_id = f"device-{uuid4().hex[:8]}"

        # If device name not provided, generate one
        if device_name is None:
            device_name = f"{platform.capitalize()} Device"

        # Create device info
        device = DeviceInfo(
            device_id=device_id,
            user_id=user_id,
            device_name=device_name,
            platform=platform,
            push_token=push_token,
            app_version=app_version,
        )

        # Get existing devices
        devices_path = self._get_user_devices_path(user_id)
        data = self._read_json(devices_path)
        devices = data.get("devices", [])

        # Check if token already exists and update
        updated = False
        for i, existing_device in enumerate(devices):
            if existing_device.get("push_token") == push_token:
                # Update existing device
                device_dict = device.model_dump(mode='json')
                device_dict['device_id'] = existing_device['device_id']
                devices[i] = device_dict
                updated = True
                break

        # If not updated, add new device
        if not updated:
            devices.append(device.model_dump(mode='json'))

        # Save to file
        self._write_json(devices_path, {"devices": devices})

        return device

    def unregister_device(self, user_id: str, device_id: str) -> bool:
        """
        Unregister a device from push notifications.

        Args:
            user_id: User ID who owns the device
            device_id: Device ID to unregister

        Returns:
            True if device was unregistered, False if not found

        Example:
            >>> success = service.unregister_device("user-001", "device-abc123")
            >>> print(success)
            True
        """
        devices_path = self._get_user_devices_path(user_id)
        data = self._read_json(devices_path)
        devices = data.get("devices", [])

        # Find and remove the device
        original_count = len(devices)
        devices = [d for d in devices if d.get("device_id") != device_id]

        if len(devices) == original_count:
            return False

        # Create backup and save
        self._create_backup(devices_path)
        self._write_json(devices_path, {"devices": devices})

        return True

    def get_user_devices(self, user_id: str) -> list[DeviceInfo]:
        """
        Get all registered devices for a user.

        Args:
            user_id: User ID to get devices for

        Returns:
            List of DeviceInfo objects

        Example:
            >>> devices = service.get_user_devices("user-001")
            >>> len(devices)
            2
        """
        devices_path = self._get_user_devices_path(user_id)
        data = self._read_json(devices_path)
        devices_data = data.get("devices", [])

        devices = []
        for device_data in devices_data:
            try:
                devices.append(DeviceInfo(**device_data))
            except Exception:
                # Skip invalid device data
                continue

        return devices

    def get_enabled_devices(self, user_id: str) -> list[DeviceInfo]:
        """
        Get enabled devices for a user.

        Args:
            user_id: User ID to get devices for

        Returns:
            List of enabled DeviceInfo objects

        Example:
            >>> devices = service.get_enabled_devices("user-001")
            >>> for device in devices:
            ...     print(f"{device.device_name}: {device.push_token[:10]}...")
        """
        devices = self.get_user_devices(user_id)
        return [d for d in devices if d.enabled]

    async def send_notification(
        self,
        user_id: str,
        notification: PushNotification,
    ) -> dict[str, PushResult]:
        """
        Send a push notification to all enabled devices for a user.

        Args:
            user_id: User ID to send notification to
            notification: PushNotification to send

        Returns:
            Dictionary mapping device IDs to PushResult objects

        Example:
            >>> notification = PushNotification(
            ...     title="Task Completed",
            ...     body="Your task is done"
            ... )
            >>> results = await service.send_notification("user-001", notification)
            >>> for device_id, result in results.items():
            ...     print(f"{device_id}: {result.success}")
        """
        devices = self.get_enabled_devices(user_id)

        if not devices:
            return {}

        # Use provider's batch send for efficiency
        tokens = [d.push_token for d in devices]
        token_results = await self.provider.send_batch(
            tokens=tokens,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            priority=notification.priority,
        )

        # Map results back to device IDs
        device_results: dict[str, PushResult] = {}
        for device, token in zip(devices, tokens):
            device_results[device.device_id] = token_results.get(
                token,
                PushResult(
                    success=False,
                    message="Token not found in batch results",
                ),
            )

        return device_results

    async def send_to_device(
        self,
        device_id: str,
        user_id: str,
        notification: PushNotification,
    ) -> PushResult:
        """
        Send a push notification to a specific device.

        Args:
            device_id: Device ID to send notification to
            user_id: User ID who owns the device
            notification: PushNotification to send

        Returns:
            PushResult indicating success or failure

        Example:
            >>> notification = PushNotification(
            ...     title="Hello",
            ...     body="World"
            ... )
            >>> result = await service.send_to_device(
            ...     "device-abc123",
            ...     "user-001",
            ...     notification
            ... )
            >>> print(result.success)
            True
        """
        devices = self.get_user_devices(user_id)

        # Find the device
        device = None
        for d in devices:
            if d.device_id == device_id:
                device = d
                break

        if device is None:
            return PushResult(
                success=False,
                message=f"Device '{device_id}' not found",
            )

        if not device.enabled:
            return PushResult(
                success=False,
                message=f"Device '{device_id}' is disabled",
            )

        # Send notification
        return await self.provider.send(
            token=device.push_token,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            priority=notification.priority,
        )

    async def notify_task_completed(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
    ) -> dict[str, PushResult]:
        """
        Send a task completed notification.

        Args:
            user_id: User ID to notify
            task_id: Task ID that was completed
            task_title: Title of the task

        Returns:
            Dictionary mapping device IDs to PushResult objects

        Example:
            >>> results = await service.notify_task_completed(
            ...     "user-001",
            ...     "task-123",
            ...     "Fix authentication bug"
            ... )
        """
        notification = PushNotification(
            title="Task Completed",
            body=f"Task '{task_title}' has been completed successfully",
            notification_type=PushNotificationType.TASK_COMPLETED,
            data={"task_id": task_id, "task_title": task_title},
            priority=ProviderPriority.NORMAL,
        )

        return await self.send_notification(user_id, notification)

    async def notify_task_failed(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
        error_message: Optional[str] = None,
    ) -> dict[str, PushResult]:
        """
        Send a task failed notification.

        Args:
            user_id: User ID to notify
            task_id: Task ID that failed
            task_title: Title of the task
            error_message: Optional error message

        Returns:
            Dictionary mapping device IDs to PushResult objects
        """
        body = f"Task '{task_title}' has failed"
        if error_message:
            body += f": {error_message[:100]}"

        notification = PushNotification(
            title="Task Failed",
            body=body,
            notification_type=PushNotificationType.TASK_FAILED,
            data={"task_id": task_id, "task_title": task_title},
            priority=ProviderPriority.HIGH,
        )

        return await self.send_notification(user_id, notification)

    async def notify_agent_attention(
        self,
        user_id: str,
        agent_name: str,
        task_id: str,
        reason: str,
    ) -> dict[str, PushResult]:
        """
        Send an agent attention needed notification.

        Args:
            user_id: User ID to notify
            agent_name: Name of the agent that needs attention
            task_id: Task ID the agent is working on
            reason: Reason for needing attention

        Returns:
            Dictionary mapping device IDs to PushResult objects
        """
        notification = PushNotification(
            title="Agent Attention Needed",
            body=f"Agent '{agent_name}' needs attention: {reason}",
            notification_type=PushNotificationType.AGENT_ATTENTION,
            data={"agent_name": agent_name, "task_id": task_id, "reason": reason},
            priority=ProviderPriority.HIGH,
            badge=1,
        )

        return await self.send_notification(user_id, notification)

    async def notify_review_request(
        self,
        user_id: str,
        task_id: str,
        task_title: str,
        requester_id: str,
    ) -> dict[str, PushResult]:
        """
        Send a review request notification.

        Args:
            user_id: User ID to notify
            task_id: Task ID to review
            task_title: Title of the task
            requester_id: ID of the user requesting review

        Returns:
            Dictionary mapping device IDs to PushResult objects
        """
        notification = PushNotification(
            title="Review Requested",
            body=f"Please review task: {task_title}",
            notification_type=PushNotificationType.REVIEW_REQUEST,
            data={
                "task_id": task_id,
                "task_title": task_title,
                "requester_id": requester_id,
            },
            priority=ProviderPriority.NORMAL,
            badge=1,
        )

        return await self.send_notification(user_id, notification)
