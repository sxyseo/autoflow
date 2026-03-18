"""
Push Notification Providers

Defines the provider interface and implementations for different push
notification services including Firebase Cloud Messaging (FCM).

Usage:
    from autoflow.notifications.providers import FirebaseProvider, MockProvider

    # Use Firebase for production
    firebase_provider = FirebaseProvider(
        credentials_path="path/to/service-account.json"
    )
    await firebase_provider.send(
        token="device-token",
        title="Hello",
        body="World"
    )

    # Use mock for testing
    mock_provider = MockProvider()
    await mock_provider.send(
        token="device-token",
        title="Hello",
        body="World"
    )
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel

# Configure logging
logger = logging.getLogger(__name__)


class ProviderPriority(str, Enum):
    """Priority levels for push notifications."""

    HIGH = "high"
    NORMAL = "normal"


class PushResult(BaseModel):
    """
    Result of a push notification send operation.

    Attributes:
        success: Whether the notification was sent successfully
        message: Result message or error details
        provider_message: Optional message from the provider
        notification_id: Optional notification ID from provider
    """

    success: bool
    message: str
    provider_message: Optional[str] = None
    notification_id: Optional[str] = None


class PushProvider(ABC):
    """
    Abstract base class for push notification providers.

    Defines the interface that all push notification providers must implement.
    This allows for easy switching between different services (Firebase, APNS,
    mock, etc.) without changing the calling code.

    Attributes:
        provider_name: Name of the provider
        enabled: Whether the provider is currently enabled

    Example:
        >>> provider = FirebaseProvider(credentials_path="credentials.json")
        >>> result = await provider.send(
        ...     token="device-token",
        ...     title="Task Completed",
        ...     body="Your task is done"
        ... )
        >>> print(result.success)
        True
    """

    provider_name: str
    enabled: bool = True

    @abstractmethod
    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> PushResult:
        """
        Send a push notification.

        Args:
            token: Device token to send notification to
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            PushResult indicating success or failure

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Providers must implement send()")

    @abstractmethod
    async def send_batch(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> dict[str, PushResult]:
        """
        Send push notifications to multiple devices.

        Args:
            tokens: List of device tokens
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            Dictionary mapping tokens to PushResult objects

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError("Providers must implement send_batch()")

    def is_enabled(self) -> bool:
        """
        Check if the provider is enabled.

        Returns:
            True if provider is enabled, False otherwise
        """
        return self.enabled

    def enable(self) -> None:
        """Enable the provider."""
        self.enabled = True
        logger.info(f"Push provider '{self.provider_name}' enabled")

    def disable(self) -> None:
        """Disable the provider."""
        self.enabled = False
        logger.info(f"Push provider '{self.provider_name}' disabled")


class MockProvider(PushProvider):
    """
    Mock push notification provider for testing and development.

    Simulates sending push notifications without actually calling any
    external services. Useful for development and testing environments.

    Attributes:
        simulate_delay: Whether to simulate network delay
        simulate_failure_rate: Rate of simulated failures (0.0-1.0)
        sent_notifications: List of all sent notifications for inspection

    Example:
        >>> provider = MockProvider(simulate_delay=False)
        >>> result = await provider.send(
        ...     token="test-token",
        ...     title="Test",
        ...     body="Notification"
        ... )
        >>> assert result.success
        >>> print(provider.sent_notifications[0]['title'])
        Test
    """

    def __init__(
        self,
        simulate_delay: bool = False,
        simulate_failure_rate: float = 0.0,
    ):
        """
        Initialize the mock provider.

        Args:
            simulate_delay: Whether to simulate network delay
            simulate_failure_rate: Rate of simulated failures (0.0-1.0)
        """
        self.provider_name = "mock"
        self.enabled = True
        self.simulate_delay = simulate_delay
        self.simulate_failure_rate = max(0.0, min(1.0, simulate_failure_rate))
        self.sent_notifications: list[dict[str, Any]] = []

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> PushResult:
        """
        Simulate sending a push notification.

        Args:
            token: Device token to send notification to
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            PushResult indicating success or simulated failure
        """
        import asyncio
        import random

        # Simulate network delay if enabled
        if self.simulate_delay:
            await asyncio.sleep(random.uniform(0.1, 0.5))

        # Simulate failure based on failure rate
        if random.random() < self.simulate_failure_rate:
            logger.warning(
                f"Mock provider simulating failure for token {token[:10]}..."
            )
            return PushResult(
                success=False,
                message="Simulated network failure",
                provider_message="Mock error: Simulated failure",
            )

        # Record the notification
        notification = {
            "token": token,
            "title": title,
            "body": body,
            "data": data,
            "priority": priority,
        }
        self.sent_notifications.append(notification)

        logger.info(
            f"Mock provider sent notification: "
            f"title='{title}', token={token[:10]}..."
        )

        return PushResult(
            success=True,
            message="Notification sent successfully (mock)",
            notification_id=f"mock-{id(notification)}",
        )

    async def send_batch(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> dict[str, PushResult]:
        """
        Simulate sending push notifications to multiple devices.

        Args:
            tokens: List of device tokens
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            Dictionary mapping tokens to PushResult objects
        """
        import asyncio

        # Send to all tokens concurrently
        tasks = [
            self.send(token, title, body, data, priority) for token in tokens
        ]
        results = await asyncio.gather(*tasks)

        return dict(zip(tokens, results))

    def clear_notifications(self) -> None:
        """Clear the record of sent notifications."""
        self.sent_notifications.clear()

    def get_sent_count(self) -> int:
        """
        Get the number of sent notifications.

        Returns:
            Number of notifications sent through this provider
        """
        return len(self.sent_notifications)


class FirebaseProvider(PushProvider):
    """
    Firebase Cloud Messaging (FCM) push notification provider.

    Integrates with Firebase Cloud Messaging to send push notifications
    to iOS and Android devices. Requires Firebase service account credentials.

    Attributes:
        credentials_path: Path to Firebase service account JSON file
        project_id: Firebase project ID
        simulate_mode: If True, simulate sending without actual API calls

    Example:
        >>> provider = FirebaseProvider(
        ...     credentials_path="firebase-service-account.json"
        ... )
        >>> result = await provider.send(
        ...     token="device-fcm-token",
        ...     title="Task Completed",
        ...     body="Your task is done"
        ... )
        >>> print(result.success)
        True
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None,
        simulate_mode: bool = False,
    ):
        """
        Initialize the Firebase provider.

        Args:
            credentials_path: Path to Firebase service account JSON file
            project_id: Firebase project ID (optional, inferred from credentials)
            simulate_mode: If True, simulate sending without actual API calls
        """
        self.provider_name = "firebase"
        self.enabled = True
        self.credentials_path = credentials_path
        self.project_id = project_id
        self.simulate_mode = simulate_mode
        self._app: Optional[Any] = None

    def _get_app(self) -> Optional[Any]:
        """
        Get or initialize the Firebase app instance.

        Returns:
            Firebase app instance or None if not configured
        """
        if self._app is not None:
            return self._app

        if self.simulate_mode:
            logger.info("Firebase provider in simulate mode - no app initialized")
            return None

        if not self.credentials_path:
            logger.warning("Firebase credentials not configured")
            return None

        try:
            import firebase_admin
            from firebase_admin import credentials, firestore

            # Check if an app is already initialized
            try:
                self._app = firebase_admin.get_app()
                return self._app
            except ValueError:
                # No app initialized, create one
                pass

            # Load credentials from file
            cred = credentials.Certificate(self.credentials_path)

            # Initialize app with optional project ID
            initialize_args: dict[str, Any] = {"credential": cred}
            if self.project_id:
                initialize_args["options"] = {"projectId": self.project_id}

            self._app = firebase_admin.initialize_app(**initialize_args)
            logger.info(f"Firebase app initialized for project {self.project_id or 'default'}")
            return self._app

        except ImportError:
            logger.error(
                "firebase-admin package not installed. "
                "Install with: pip install firebase-admin"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Firebase app: {e}")
            return None

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> PushResult:
        """
        Send a push notification via Firebase Cloud Messaging.

        Args:
            token: Device token to send notification to
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            PushResult indicating success or failure
        """
        if not self.is_enabled():
            return PushResult(
                success=False,
                message="Firebase provider is disabled",
            )

        if self.simulate_mode:
            return await self._simulate_send(token, title, body, data, priority)

        app = self._get_app()
        if app is None:
            return PushResult(
                success=False,
                message="Firebase app not initialized. Check credentials.",
            )

        try:
            from firebase_admin import messaging

            # Build the message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
                android=messaging.AndroidConfig(
                    priority=(
                        messaging.AndroidNotification.Priority.HIGH
                        if priority == ProviderPriority.HIGH
                        else messaging.AndroidNotification.Priority.NORMAL
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body,
                            ),
                            badge=1,
                            sound="default",
                        ),
                    ),
                ),
            )

            # Send the message
            response = messaging.send(message, app=app)

            logger.info(
                f"Firebase notification sent successfully: "
                f"id={response}, token={token[:10]}..."
            )

            return PushResult(
                success=True,
                message="Notification sent successfully",
                provider_message=response,
                notification_id=response,
            )

        except ImportError:
            logger.error("firebase-admin package not installed")
            return PushResult(
                success=False,
                message="firebase-admin package not installed. "
                "Install with: pip install firebase-admin",
            )
        except Exception as e:
            logger.error(f"Failed to send Firebase notification: {e}")
            return PushResult(
                success=False,
                message=f"Failed to send notification: {e}",
                provider_message=str(e),
            )

    async def send_batch(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict[str, Any]] = None,
        priority: ProviderPriority = ProviderPriority.NORMAL,
    ) -> dict[str, PushResult]:
        """
        Send push notifications to multiple devices via Firebase.

        Args:
            tokens: List of device tokens
            title: Notification title
            body: Notification body text
            data: Optional additional data payload
            priority: Notification priority level

        Returns:
            Dictionary mapping tokens to PushResult objects
        """
        if not tokens:
            return {}

        if not self.is_enabled():
            return {
                token: PushResult(
                    success=False,
                    message="Firebase provider is disabled",
                )
                for token in tokens
            }

        if self.simulate_mode:
            return await self._simulate_send_batch(tokens, title, body, data, priority)

        app = self._get_app()
        if app is None:
            return {
                token: PushResult(
                    success=False,
                    message="Firebase app not initialized. Check credentials.",
                )
                for token in tokens
            }

        try:
            from firebase_admin import messaging

            # Build multicast message
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                tokens=tokens,
                android=messaging.AndroidConfig(
                    priority=(
                        messaging.AndroidNotification.Priority.HIGH
                        if priority == ProviderPriority.HIGH
                        else messaging.AndroidNotification.Priority.NORMAL
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body,
                            ),
                            badge=1,
                            sound="default",
                        ),
                    ),
                ),
            )

            # Send the multicast message
            batch_response = messaging.send_multicast(message, app=app)

            # Build results dictionary
            results: dict[str, PushResult] = {}
            for i, token in enumerate(tokens):
                if i < batch_response.success_count:
                    results[token] = PushResult(
                        success=True,
                        message="Notification sent successfully",
                        notification_id=batch_response.responses[i].message_id,
                    )
                else:
                    failure_index = i - batch_response.success_count
                    exception = batch_response.responses[
                        batch_response.success_count + failure_index
                    ].exception
                    results[token] = PushResult(
                        success=False,
                        message="Failed to send notification",
                        provider_message=str(exception) if exception else "Unknown error",
                    )

            logger.info(
                f"Firebase batch send: {batch_response.success_count}/{len(tokens)} successful"
            )

            return results

        except ImportError:
            logger.error("firebase-admin package not installed")
            return {
                token: PushResult(
                    success=False,
                    message="firebase-admin package not installed",
                )
                for token in tokens
            }
        except Exception as e:
            logger.error(f"Failed to send Firebase batch notifications: {e}")
            return {
                token: PushResult(
                    success=False,
                    message=f"Failed to send notification: {e}",
                )
                for token in tokens
            }

    async def _simulate_send(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[dict[str, Any]],
        priority: ProviderPriority,
    ) -> PushResult:
        """Simulate sending a notification for testing."""
        logger.info(
            f"Firebase SIMULATE: Sending notification to {token[:10]}... "
            f"title='{title}', priority={priority}"
        )

        return PushResult(
            success=True,
            message="Notification sent successfully (simulated)",
            notification_id=f"sim-{id(token)}",
        )

    async def _simulate_send_batch(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: Optional[dict[str, Any]],
        priority: ProviderPriority,
    ) -> dict[str, PushResult]:
        """Simulate sending batch notifications for testing."""
        logger.info(
            f"Firebase SIMULATE: Sending batch to {len(tokens)} tokens "
            f"title='{title}', priority={priority}"
        )

        return {
            token: PushResult(
                success=True,
                message="Notification sent successfully (simulated)",
                notification_id=f"sim-{id(token)}",
            )
            for token in tokens
        }
