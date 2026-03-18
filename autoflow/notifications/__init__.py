"""
Autoflow Push Notification Module

Provides push notification services for mobile companion app, including
Firebase Cloud Messaging integration and device token management.

Usage:
    from autoflow.notifications.push import PushNotificationService
    from autoflow.notifications.providers import FirebaseProvider

    # Initialize service
    service = PushNotificationService()
    service.initialize()

    # Register device token
    service.register_device_token("user-001", "device-token", "ios")

    # Send notification
    service.send_notification(
        user_id="user-001",
        title="Task Completed",
        body="Your task has been completed successfully",
        data={"task_id": "task-001"}
    )
"""

from __future__ import annotations

from autoflow.notifications.push import (
    PushNotificationService,
    PushNotificationType,
    DeviceInfo,
    PushNotification,
)
from autoflow.notifications.providers import (
    PushProvider,
    FirebaseProvider,
    MockProvider,
)

__all__ = [
    "PushNotificationService",
    "PushNotificationType",
    "DeviceInfo",
    "PushNotification",
    "PushProvider",
    "FirebaseProvider",
    "MockProvider",
]
