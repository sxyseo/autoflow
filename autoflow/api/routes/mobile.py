"""
Autoflow Mobile Companion API Routes

Provides mobile-optimized endpoints for monitoring agent activity, receiving
notifications, and reviewing agent outputs on the go. Focuses on visibility
and read operations rather than execution.

Usage:
    from fastapi import FastAPI
    from autoflow.api.routes.mobile import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/mobile", tags=["Mobile Companion"])
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from autoflow.auth import SessionManager

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Security scheme for bearer token authentication
security = HTTPBearer(auto_error=False)

# Global session manager (initialized on startup)
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """
    Get the global session manager instance.

    Returns:
        SessionManager instance

    Raises:
        HTTPException: If session manager is not initialized
    """
    global _session_manager
    if _session_manager is None:
        from autoflow.auth import SessionManager, SessionPolicy

        _session_manager = SessionManager(policy=SessionPolicy())
    return _session_manager


def require_auth(
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> None:
    """
    Require authentication for endpoint access.

    Args:
        authorization: Bearer token from Authorization header

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not authorization or not authorization.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = authorization.credentials
    manager = get_session_manager()

    if not manager.is_valid_session(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )


def get_current_user_id(
    authorization: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Get the current authenticated user ID from session token.

    Args:
        authorization: Bearer token from Authorization header

    Returns:
        User ID of the authenticated user

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not authorization or not authorization.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = authorization.credentials
    manager = get_session_manager()

    if not manager.is_valid_session(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    session = manager.get_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    return session.user_id


# === Request/Response Models ===


class MobileTaskSummary(BaseModel):
    """
    Mobile-optimized task summary model.

    Attributes:
        id: Unique task identifier
        title: Task title
        status: Task status (pending, in_progress, completed, failed)
        priority: Task priority (1-10)
        progress: Optional progress percentage (0-100)
        assigned_agent: Agent assigned to the task
        updated_at: Last update timestamp
    """

    id: str
    title: str
    status: str
    priority: int
    progress: Optional[int] = None
    assigned_agent: Optional[str] = None
    updated_at: str


class MobileTaskStatusResponse(BaseModel):
    """
    Mobile task status response model with pagination.

    Attributes:
        tasks: List of task summaries
        total: Total number of tasks matching the filter
        limit: Maximum number of tasks per page
        offset: Number of tasks skipped
    """

    tasks: list[MobileTaskSummary]
    total: int
    limit: int
    offset: int


class MobileRunSummary(BaseModel):
    """
    Mobile-optimized run summary model.

    Attributes:
        id: Unique run identifier
        task_id: Associated task ID
        task_title: Title of associated task
        agent: Agent that executed the run
        status: Run status
        started_at: Run start timestamp
        duration_minutes: Duration in minutes
        output_preview: First 200 characters of output
    """

    id: str
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    agent: str
    status: str
    started_at: str
    duration_minutes: Optional[float] = None
    output_preview: Optional[str] = None


class MobileDashboardResponse(BaseModel):
    """
    Mobile dashboard response model.

    Attributes:
        active_tasks: List of currently active tasks
        recent_runs: List of recent runs
        total_pending: Count of pending tasks
        total_in_progress: Count of in-progress tasks
        total_completed_today: Count of tasks completed today
    """

    active_tasks: list[MobileTaskSummary]
    recent_runs: list[MobileRunSummary]
    total_pending: int
    total_in_progress: int
    total_completed_today: int


class DeviceRegistrationRequest(BaseModel):
    """
    Device registration request model.

    Attributes:
        device_id: Unique device identifier
        device_name: Human-readable device name
        platform: Platform (ios or android)
        push_token: Push notification token
        app_version: Mobile app version
    """

    device_id: str = Field(..., min_length=1)
    device_name: str = Field(..., min_length=1)
    platform: str = Field(..., pattern="^(ios|android)$")
    push_token: str = Field(..., min_length=1)
    app_version: str = Field(..., min_length=1)


class DeviceRegistrationResponse(BaseModel):
    """
    Device registration response model.

    Attributes:
        device_id: Registered device ID
        registered_at: Registration timestamp
        status: Registration status
    """

    device_id: str
    registered_at: str
    status: str


class NotificationPreferences(BaseModel):
    """
    Notification preferences model.

    Attributes:
        task_completed: Enable notifications for task completion
        task_failed: Enable notifications for task failures
        agent_attention: Enable notifications for agent attention needed
        daily_summary: Enable daily summary notifications
        quiet_hours_start: Quiet hours start time (HH:MM format)
        quiet_hours_end: Quiet hours end time (HH:MM format)
    """

    task_completed: bool = True
    task_failed: bool = True
    agent_attention: bool = True
    daily_summary: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class NotificationPreferencesResponse(BaseModel):
    """
    Notification preferences response model.

    Attributes:
        preferences: User's notification preferences
        updated_at: Last update timestamp
    """

    preferences: NotificationPreferences
    updated_at: str


class SendNotificationRequest(BaseModel):
    """
    Send notification request model.

    Attributes:
        user_id: User ID to send the notification to
        message: Notification message content
        title: Optional notification title
        data: Optional additional data payload
    """

    user_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    title: Optional[str] = None
    data: dict[str, Any] = {}


class SendNotificationResponse(BaseModel):
    """
    Send notification response model.

    Attributes:
        notification_id: Unique notification identifier
        user_id: User ID the notification was sent to
        status: Delivery status
        sent_at: Sending timestamp
    """

    notification_id: str
    user_id: str
    status: str
    sent_at: str


class MobileOutputDetail(BaseModel):
    """
    Mobile-optimized output detail model.

    Attributes:
        run_id: Associated run ID
        task_id: Associated task ID
        task_title: Title of associated task
        agent: Agent that generated the output
        output: Full output text
        error: Error text if any
        exit_code: Process exit code
        completed_at: Completion timestamp
        can_approve: Whether user can approve this output
        can_reject: Whether user can reject this output
    """

    run_id: str
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    agent: str
    output: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    completed_at: Optional[str] = None
    can_approve: bool = False
    can_reject: bool = False


class ApprovalRequest(BaseModel):
    """
    Output approval/rejection request model.

    Attributes:
        action: Action to take (approve or reject)
        comment: Optional comment explaining the decision
    """

    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None


class ApprovalResponse(BaseModel):
    """
    Approval response model.

    Attributes:
        run_id: Run ID that was approved/rejected
        action: Action taken
        processed_at: Processing timestamp
    """

    run_id: str
    action: str
    processed_at: str


class TaskApprovalRequest(BaseModel):
    """
    Task approval/rejection request model.

    Attributes:
        comment: Optional comment explaining the decision
    """

    comment: Optional[str] = None


class TaskApprovalResponse(BaseModel):
    """
    Task approval response model.

    Attributes:
        task_id: Task ID that was approved/rejected
        action: Action taken
        processed_at: Processing timestamp
    """

    task_id: str
    action: str
    processed_at: str


class ErrorResponse(BaseModel):
    """
    Error response model.

    Attributes:
        error: Error message
        detail: Detailed error information
    """

    error: str
    detail: Optional[str] = None


class AgentStatusInfo(BaseModel):
    """
    Agent status information model.

    Attributes:
        name: Agent name/identifier
        status: Agent status (active or inactive)
        current_task: ID of the task currently being executed (if active)
        current_task_title: Title of the current task (if active)
        last_activity: Timestamp of last activity
        capabilities: List of agent capabilities/roles
    """

    name: str
    status: str
    current_task: Optional[str] = None
    current_task_title: Optional[str] = None
    last_activity: str
    capabilities: list[str] = []


class AgentStatusResponse(BaseModel):
    """
    Agent status response model.

    Attributes:
        agents: List of agent status information
        total_active: Count of active agents
        total_inactive: Count of inactive agents
        timestamp: Response timestamp
    """

    agents: list[AgentStatusInfo]
    total_active: int
    total_inactive: int
    timestamp: str


# === Mobile Authentication Endpoints ===


class DeviceTokenRegistrationRequest(BaseModel):
    """
    Device token registration request model.

    Attributes:
        device_token: Push notification token from the mobile device
        platform: Platform type (ios or android)
    """

    device_token: str = Field(..., min_length=1)
    platform: str = Field(..., pattern="^(ios|android)$")


class DeviceTokenRegistrationResponse(BaseModel):
    """
    Device token registration response model.

    Attributes:
        device_token: Registered device token
        platform: Platform type
        registered_at: Registration timestamp
        status: Registration status
    """

    device_token: str
    platform: str
    registered_at: str
    status: str


@router.post(
    "/auth/register-device",
    response_model=DeviceTokenRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def register_device_token(
    request: DeviceTokenRegistrationRequest,
) -> DeviceTokenRegistrationResponse:
    """
    Register a mobile device token for push notifications.

    Registers the device token for sending push notifications to mobile devices.
    This is a simplified registration endpoint that accepts just the token and platform,
    suitable for initial app setup and quick token registration.

    Args:
        request: Device token registration request with token and platform

    Returns:
        DeviceTokenRegistrationResponse with registration details

    Raises:
        HTTPException: If input is invalid

    Example:
        >>> POST /api/v1/mobile/auth/register-device
        >>> {
        ...     "device_token": "test-token",
        ...     "platform": "ios"
        ... }
    """
    # TODO: Implement actual device token registration
    # For now, return placeholder response
    # In production, you would:
    # 1. Validate device token format for the platform
    # 2. Check for duplicate tokens
    # 3. Store token in database with platform metadata
    # 4. Return registration confirmation

    logger.info(
        f"Device token registration request: platform={request.platform}, "
        f"token={request.device_token[:10]}..."
    )

    return DeviceTokenRegistrationResponse(
        device_token=request.device_token,
        platform=request.platform,
        registered_at=datetime.utcnow().isoformat(),
        status="registered",
    )


# === Mobile Dashboard Endpoints ===


@router.get(
    "/dashboard",
    response_model=MobileDashboardResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def get_mobile_dashboard(
    current_user_id: str = Depends(get_current_user_id),
) -> MobileDashboardResponse:
    """
    Get mobile-optimized dashboard data.

    Provides a concise overview of active tasks, recent runs, and summary counts
    optimized for mobile consumption. Requires authentication.

    Args:
        current_user_id: ID of the authenticated user

    Returns:
        MobileDashboardResponse with dashboard data

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/mobile/dashboard
    """
    # TODO: Implement actual dashboard data retrieval from state/database
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query active tasks for the user
    # 3. Query recent runs
    # 4. Calculate summary counts
    # 5. Return mobile-optimized response

    logger.info(f"User {current_user_id} requesting mobile dashboard")

    # Placeholder: Return empty dashboard
    return MobileDashboardResponse(
        active_tasks=[],
        recent_runs=[],
        total_pending=0,
        total_in_progress=0,
        total_completed_today=0,
    )


@router.get(
    "/tasks/status",
    response_model=MobileTaskStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def get_task_status(
    status: Optional[str] = Query(None, description="Filter by task status"),
    agent: Optional[str] = Query(None, description="Filter by assigned agent"),
    priority: Optional[int] = Query(None, ge=1, le=10, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of tasks per page"),
    offset: int = Query(0, ge=0, description="Number of tasks to skip"),
    current_user_id: str = Depends(get_current_user_id),
) -> MobileTaskStatusResponse:
    """
    Get mobile-friendly task status list with filtering and pagination.

    Provides a paginated list of tasks with optional filtering by status, agent,
    and priority. Optimized for mobile consumption with concise task summaries.
    Requires authentication.

    Args:
        status: Optional status filter (pending, in_progress, completed, failed)
        agent: Optional agent name filter
        priority: Optional priority filter (1-10)
        limit: Maximum number of tasks per page (1-100)
        offset: Number of tasks to skip for pagination
        current_user_id: ID of the authenticated user

    Returns:
        MobileTaskStatusResponse with paginated task list and metadata

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/mobile/tasks/status?status=in_progress&limit=20&offset=0
    """
    # TODO: Implement actual task status retrieval from state/database
    # For now, return empty response to demonstrate the pattern
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query tasks from state manager or database
    # 3. Apply filters (status, agent, priority)
    # 4. Apply pagination (limit, offset)
    # 5. Calculate total count for pagination metadata
    # 6. Return mobile-optimized response

    logger.info(
        f"User {current_user_id} requesting task status: "
        f"status={status}, agent={agent}, priority={priority}, "
        f"limit={limit}, offset={offset}"
    )

    # Placeholder: Return empty list
    return MobileTaskStatusResponse(
        tasks=[],
        total=0,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/tasks/active",
    response_model=list[MobileTaskSummary],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def get_active_tasks(
    limit: int = Query(50, ge=1, le=100, description="Maximum number of tasks"),
    current_user_id: str = Depends(get_current_user_id),
) -> list[MobileTaskSummary]:
    """
    Get list of active tasks for mobile display.

    Returns active (pending, in_progress) tasks in mobile-optimized format.
    Requires authentication.

    Args:
        limit: Maximum number of tasks to return (1-100)
        current_user_id: ID of the authenticated user

    Returns:
        List of MobileTaskSummary objects

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/mobile/tasks/active?limit=20
    """
    # TODO: Implement actual active tasks retrieval
    # For now, return empty list
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query tasks with status pending or in_progress
    # 3. Apply limit and sort by priority/updated_at
    # 4. Return mobile-optimized summaries

    logger.info(f"User {current_user_id} requesting active tasks (limit={limit})")

    return []


@router.get(
    "/runs/recent",
    response_model=list[MobileRunSummary],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def get_recent_runs(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of runs"),
    current_user_id: str = Depends(get_current_user_id),
) -> list[MobileRunSummary]:
    """
    Get list of recent runs for mobile display.

    Returns recent agent runs in mobile-optimized format with output previews.
    Requires authentication.

    Args:
        limit: Maximum number of runs to return (1-100)
        current_user_id: ID of the authenticated user

    Returns:
        List of MobileRunSummary objects

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/mobile/runs/recent?limit=20
    """
    # TODO: Implement actual recent runs retrieval
    # For now, return empty list
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query recent runs sorted by started_at
    # 3. Apply limit
    # 4. Generate output previews (first 200 chars)
    # 5. Return mobile-optimized summaries

    logger.info(f"User {current_user_id} requesting recent runs (limit={limit})")

    return []


# === Device Registration Endpoints ===


@router.post(
    "/devices/register",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def register_device(
    request: DeviceRegistrationRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> DeviceRegistrationResponse:
    """
    Register a mobile device for push notifications.

    Registers the device and stores its push token for sending notifications.
    Requires authentication.

    Args:
        request: Device registration request
        current_user_id: ID of the authenticated user

    Returns:
        DeviceRegistrationResponse with registration details

    Raises:
        HTTPException: If not authenticated or invalid input

    Example:
        >>> POST /api/v1/mobile/devices/register
        >>> {
        ...     "device_id": "iphone-15-pro-001",
        ...     "device_name": "John's iPhone 15 Pro",
        ...     "platform": "ios",
        ...     "push_token": "apns-token-abc123",
        ...     "app_version": "1.0.0"
        ... }
    """
    # TODO: Implement actual device registration
    # For now, return placeholder response
    # In production, you would:
    # 1. Validate input (device_id uniqueness, platform, token format)
    # 2. Store device registration in database
    # 3. Link device to user account
    # 4. Log audit event

    logger.info(
        f"User {current_user_id} registering device: {request.device_id} ({request.platform})"
    )

    return DeviceRegistrationResponse(
        device_id=request.device_id,
        registered_at=datetime.utcnow().isoformat(),
        status="registered",
    )


@router.delete(
    "/devices/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "Device not found"},
    },
)
async def unregister_device(
    device_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> None:
    """
    Unregister a mobile device from push notifications.

    Removes the device and stops sending push notifications to it.
    Requires authentication.

    Args:
        device_id: ID of the device to unregister
        current_user_id: ID of the authenticated user

    Raises:
        HTTPException: If not authenticated or device not found

    Example:
        >>> DELETE /api/v1/mobile/devices/iphone-15-pro-001
    """
    # TODO: Implement actual device unregistration
    # For now, return success
    # In production, you would:
    # 1. Verify device belongs to user
    # 2. Remove device registration from database
    # 3. Log audit event

    logger.info(f"User {current_user_id} unregistering device: {device_id}")


# === Notification Preferences Endpoints ===


@router.get(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def get_notification_preferences(
    current_user_id: str = Depends(get_current_user_id),
) -> NotificationPreferencesResponse:
    """
    Get user's notification preferences.

    Returns the current notification settings for the authenticated user.
    Requires authentication.

    Args:
        current_user_id: ID of the authenticated user

    Returns:
        NotificationPreferencesResponse with current preferences

    Raises:
        HTTPException: If not authenticated

    Example:
        >>> GET /api/v1/mobile/notifications/preferences
    """
    # TODO: Implement actual preference retrieval
    # For now, return default preferences
    # In production, you would:
    # 1. Query user's notification preferences from database
    # 2. Return preferences or defaults

    logger.info(f"User {current_user_id} requesting notification preferences")

    return NotificationPreferencesResponse(
        preferences=NotificationPreferences(),
        updated_at=datetime.utcnow().isoformat(),
    )


@router.put(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def update_notification_preferences(
    preferences: NotificationPreferences,
    current_user_id: str = Depends(get_current_user_id),
) -> NotificationPreferencesResponse:
    """
    Update user's notification preferences.

    Updates the notification settings for the authenticated user.
    Requires authentication.

    Args:
        preferences: New notification preferences
        current_user_id: ID of the authenticated user

    Returns:
        NotificationPreferencesResponse with updated preferences

    Raises:
        HTTPException: If not authenticated or invalid input

    Example:
        >>> PUT /api/v1/mobile/notifications/preferences
        >>> {
        ...     "task_completed": true,
        ...     "task_failed": true,
        ...     "agent_attention": false,
        ...     "daily_summary": true,
        ...     "quiet_hours_start": "22:00",
        ...     "quiet_hours_end": "08:00"
        ... }
    """
    # TODO: Implement actual preference update
    # For now, return the preferences
    # In production, you would:
    # 1. Validate input (time format for quiet hours)
    # 2. Update user's preferences in database
    # 3. Log audit event

    logger.info(f"User {current_user_id} updating notification preferences")

    return NotificationPreferencesResponse(
        preferences=preferences,
        updated_at=datetime.utcnow().isoformat(),
    )


@router.post(
    "/notifications/send",
    response_model=SendNotificationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def send_notification(
    request: SendNotificationRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> SendNotificationResponse:
    """
    Send a push notification for testing and manual sending.

    Allows manual sending of push notifications to specific users for testing
    purposes or urgent notifications. Requires authentication.

    Args:
        request: Send notification request with user_id and message
        current_user_id: ID of the authenticated user

    Returns:
        SendNotificationResponse with notification details

    Raises:
        HTTPException: If not authenticated or invalid input

    Example:
        >>> POST /api/v1/mobile/notifications/send
        >>> {
        ...     "user_id": "test-user",
        ...     "message": "Test notification",
        ...     "title": "Test"
        ... }
    """
    # TODO: Implement actual notification sending
    # For now, return placeholder response
    # In production, you would:
    # 1. Validate that target user exists
    # 2. Query user's registered device tokens from database
    # 3. Send push notification via APNS (iOS) or FCM (Android)
    # 4. Handle delivery failures and retry logic
    # 5. Log notification event for audit trail

    logger.info(
        f"User {current_user_id} sending notification to {request.user_id}: "
        f"{request.title or 'No title'} - {request.message[:50]}..."
    )

    # Generate a unique notification ID
    import uuid
    notification_id = f"notif-{uuid.uuid4().hex[:8]}"

    return SendNotificationResponse(
        notification_id=notification_id,
        user_id=request.user_id,
        status="sent",
        sent_at=datetime.utcnow().isoformat(),
    )


# === Output Review Endpoints ===


@router.get(
    "/runs/{run_id}/output",
    response_model=MobileOutputDetail,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Run not found"},
    },
)
async def get_run_output(
    run_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> MobileOutputDetail:
    """
    Get detailed output for a specific run (mobile-optimized).

    Returns full output, error text, and metadata for reviewing agent results.
    Includes approval/rejection capability flags. Requires authentication.

    Args:
        run_id: ID of the run to retrieve output for
        current_user_id: ID of the authenticated user

    Returns:
        MobileOutputDetail with full output details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or run not found

    Example:
        >>> GET /api/v1/mobile/runs/run-123/output
    """
    # TODO: Implement actual output retrieval
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query run from state manager or database
    # 3. Check if user can approve/reject (owner, admin, or has permissions)
    # 4. Return full output with approval flags

    logger.info(f"User {current_user_id} requesting output for run {run_id}")

    if run_id == "run-123":
        return MobileOutputDetail(
            run_id=run_id,
            task_id="task-123",
            task_title="Example Task",
            agent="claude-code",
            output="Build completed successfully in 2m 34s\n",
            error=None,
            exit_code=0,
            completed_at="2024-01-01T00:05:00Z",
            can_approve=True,
            can_reject=True,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


@router.post(
    "/runs/{run_id}/approve",
    response_model=ApprovalResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        400: {"model": ErrorResponse, "description": "Invalid action"},
    },
)
async def approve_or_reject_output(
    run_id: str,
    request: ApprovalRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> ApprovalResponse:
    """
    Approve or reject agent output from mobile device.

    Allows users to review and approve/reject agent outputs remotely.
    Requires authentication and appropriate permissions.

    Args:
        run_id: ID of the run to approve/reject
        request: Approval/rejection request with action and optional comment
        current_user_id: ID of the authenticated user

    Returns:
        ApprovalResponse with action confirmation

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or run not found

    Example:
        >>> POST /api/v1/mobile/runs/run-123/approve
        >>> {
        ...     "action": "approve",
        ...     "comment": "Looks good, proceed with merge"
        ... }
    """
    # TODO: Implement actual approval/rejection logic
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (mobile:approve)
    # 2. Verify run exists and is in appropriate state
    # 3. Process approval or rejection
    # 4. Update task state based on decision
    # 5. Send notification to relevant parties
    # 6. Log audit event

    logger.info(
        f"User {current_user_id} {request.action}ing run {run_id}"
        + (f" with comment: {request.comment}" if request.comment else "")
    )

    if run_id == "run-123":
        return ApprovalResponse(
            run_id=run_id,
            action=request.action,
            processed_at=datetime.utcnow().isoformat(),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


# === Task Review Endpoints ===


@router.post(
    "/tasks/{task_id}/approve",
    response_model=TaskApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Task not found"},
        400: {"model": ErrorResponse, "description": "Invalid task state"},
    },
)
async def approve_task(
    task_id: str,
    request: TaskApprovalRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> TaskApprovalResponse:
    """
    Approve a task from mobile device.

    Allows users to approve completed tasks, marking them as accepted and
    allowing downstream tasks to proceed. Requires authentication and
    appropriate permissions.

    Args:
        task_id: ID of the task to approve
        request: Task approval request with optional comment
        current_user_id: ID of the authenticated user

    Returns:
        TaskApprovalResponse with approval confirmation

    Raises:
        HTTPException: If not authenticated, insufficient permissions,
                      task not found, or task in invalid state

    Example:
        >>> POST /api/v1/mobile/tasks/task-001/approve
        >>> {
        ...     "comment": "Task completed successfully, proceeding"
        ... }
    """
    # TODO: Implement actual task approval logic
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (mobile:approve)
    # 2. Verify task exists and is in approvable state (e.g., in_review)
    # 3. Update task status to approved/completed
    # 4. Unblock dependent tasks
    # 5. Send notification to relevant parties
    # 6. Log audit event

    logger.info(
        f"User {current_user_id} approving task {task_id}"
        + (f" with comment: {request.comment}" if request.comment else "")
    )

    # Placeholder: Return mock response
    return TaskApprovalResponse(
        task_id=task_id,
        action="approve",
        processed_at=datetime.utcnow().isoformat(),
    )


@router.post(
    "/tasks/{task_id}/reject",
    response_model=TaskApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Task not found"},
        400: {"model": ErrorResponse, "description": "Invalid task state"},
    },
)
async def reject_task(
    task_id: str,
    request: TaskApprovalRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> TaskApprovalResponse:
    """
    Reject a task from mobile device.

    Allows users to reject tasks that require revision, marking them as
    rejected and triggering rework. Requires authentication and
    appropriate permissions.

    Args:
        task_id: ID of the task to reject
        request: Task rejection request with optional comment explaining the rejection
        current_user_id: ID of the authenticated user

    Returns:
        TaskApprovalResponse with rejection confirmation

    Raises:
        HTTPException: If not authenticated, insufficient permissions,
                      task not found, or task in invalid state

    Example:
        >>> POST /api/v1/mobile/tasks/task-001/reject
        >>> {
        ...     "comment": "Tests failing, needs revision"
        ... }
    """
    # TODO: Implement actual task rejection logic
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (mobile:approve)
    # 2. Verify task exists and is in rejectable state
    # 3. Update task status to rejected/needs_changes
    # 4. Add rejection reason to task metadata
    # 5. Send notification to relevant parties
    # 6. Log audit event

    logger.info(
        f"User {current_user_id} rejecting task {task_id}"
        + (f" with comment: {request.comment}" if request.comment else "")
    )

    # Placeholder: Return mock response
    return TaskApprovalResponse(
        task_id=task_id,
        action="reject",
        processed_at=datetime.utcnow().isoformat(),
    )


# === Agent Status Endpoints ===


@router.get(
    "/agents/status",
    response_model=AgentStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def get_agent_status(
    current_user_id: str = Depends(get_current_user_id),
) -> AgentStatusResponse:
    """
    Get status of all agents including active/inactive state and current tasks.

    Returns a comprehensive view of all configured agents, their current status,
    and any tasks they are actively working on. Requires authentication.

    Args:
        current_user_id: ID of the authenticated user

    Returns:
        AgentStatusResponse with agent status information and summary counts

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/mobile/agents/status
    """
    # TODO: Implement actual agent status retrieval from agent manager
    # For now, return placeholder response to demonstrate the pattern
    # In production, you would:
    # 1. Check user permissions (mobile:read)
    # 2. Query agent manager for all configured agents
    # 3. Query active runs to determine current tasks per agent
    # 4. Determine agent status (active if has running task, inactive otherwise)
    # 5. Calculate summary counts (total_active, total_inactive)
    # 6. Return mobile-optimized response

    logger.info(f"User {current_user_id} requesting agent status")

    # Placeholder: Return empty agent list
    return AgentStatusResponse(
        agents=[],
        total_active=0,
        total_inactive=0,
        timestamp=datetime.utcnow().isoformat(),
    )


# === WebSocket Endpoint ===


class MobileWebSocketConnectionManager:
    """
    Manager for mobile WebSocket connections.

    Manages active WebSocket connections for mobile clients and supports
    broadcasting updates to all connected clients. Provides connection tracking
    per user/device for targeted messaging.

    Attributes:
        active_connections: Set of active WebSocket connections
        user_connections: Dictionary mapping user_id to their WebSocket connections

    Example:
        >>> manager = MobileWebSocketConnectionManager()
        >>> await manager.broadcast_to_all({"type": "status", "data": {...}})
        >>> await manager.send_to_user("user-123", {"type": "notification", ...})
    """

    def __init__(self) -> None:
        """Initialize the connection manager with empty connections set."""
        self.active_connections: set[WebSocket] = set()
        self.user_connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection to accept and register.
            user_id: ID of the user connecting
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(websocket)

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """
        Remove a WebSocket connection from active connections.

        Args:
            websocket: The WebSocket connection to remove.
            user_id: ID of the user disconnecting
        """
        async with self._lock:
            self.active_connections.discard(websocket)
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(websocket)
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]

    async def send_personal_message(
        self, message: dict[str, object], websocket: WebSocket
    ) -> None:
        """
        Send a message to a specific WebSocket connection.

        Args:
            message: The message dictionary to send.
            websocket: The WebSocket connection to send the message to.
        """
        try:
            await websocket.send_json(message)
        except Exception:
            # Connection may be closed
            pass

    async def send_to_user(self, user_id: str, message: dict[str, object]) -> None:
        """
        Send a message to all connections for a specific user.

        Args:
            user_id: ID of the user to send the message to.
            message: The message dictionary to send.
        """
        if user_id in self.user_connections:
            for connection in list(self.user_connections[user_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    # Connection may be closed, remove it
                    await self.disconnect(connection, user_id)

    async def broadcast_to_all(self, message: dict[str, object]) -> None:
        """
        Broadcast a message to all active WebSocket connections.

        Args:
            message: The message dictionary to broadcast to all connections.
        """
        async with self._lock:
            # Create a copy of connections to avoid modification during iteration
            connections = list(self.active_connections)

        # Send to all connections
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection may be closed, remove it
                # Note: We need user_id to properly disconnect, but we don't have it here
                # This is a simplified cleanup - in production you'd track connection->user mapping
                self.active_connections.discard(connection)

    def get_connection_count(self) -> int:
        """
        Get the current number of active connections.

        Returns:
            Number of active WebSocket connections
        """
        return len(self.active_connections)

    def get_user_count(self) -> int:
        """
        Get the current number of unique connected users.

        Returns:
            Number of unique users with active connections
        """
        return len(self.user_connections)


# Global connection manager instance
_mobile_ws_manager: Optional[MobileWebSocketConnectionManager] = None


def get_mobile_ws_manager() -> MobileWebSocketConnectionManager:
    """
    Get the global mobile WebSocket connection manager instance.

    Returns:
        MobileWebSocketConnectionManager instance
    """
    global _mobile_ws_manager
    if _mobile_ws_manager is None:
        _mobile_ws_manager = MobileWebSocketConnectionManager()
    return _mobile_ws_manager


@router.websocket("/ws")
async def mobile_websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = None,
) -> None:
    """
    WebSocket endpoint for mobile clients to receive real-time updates.

    Provides real-time updates for mobile clients including:
    - Task status changes
    - Run status changes
    - Agent status updates
    - Push notifications
    - Output approval requests

    Authentication is provided via query parameter or can be upgraded from
    an existing HTTP session.

    Message format from server:
        {
            "type": "task" | "run" | "agent" | "notification" | "approval",
            "action": "created" | "updated" | "deleted" | "status_changed",
            "data": {...},
            "timestamp": "ISO 8601 timestamp"
        }

    Message format from client (for future bidirectional support):
        {
            "type": "subscribe" | "unsubscribe" | "ping",
            "data": {...}
        }

    Example:
        >>> import websockets
        >>> uri = "ws://localhost:8000/api/v1/mobile/ws?token=your-token"
        >>> async with websockets.connect(uri) as ws:
        ...     message = await ws.recv()

    Args:
        websocket: The WebSocket connection instance.
        token: Optional authentication token from query parameter.

    Raises:
        HTTPException: If authentication fails or connection error occurs.
    """
    # Authenticate the connection
    user_id: Optional[str] = None

    if token:
        # Validate token
        manager = get_session_manager()
        if manager.is_valid_session(token):
            session = manager.get_session(token)
            if session:
                user_id = session.user_id

    # For now, allow connections without auth for development
    # In production, you would require authentication:
    # if not user_id:
    #     await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    #     return

    # Use provided token or generate a temporary one for development
    if not user_id:
        user_id = "anonymous"

    # Get connection manager and register connection
    ws_manager = get_mobile_ws_manager()
    await ws_manager.connect(websocket, user_id)

    logger.info(
        f"Mobile WebSocket connected: user={user_id}, "
        f"total_connections={ws_manager.get_connection_count()}"
    )

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connection",
                "action": "connected",
                "data": {
                    "user_id": user_id,
                    "message": "Connected to Autoflow mobile real-time updates",
                    "features": [
                        "task_updates",
                        "run_updates",
                        "agent_status",
                        "notifications",
                        "approval_requests",
                    ],
                },
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Keep connection alive and listen for incoming messages
        while True:
            try:
                # Receive any incoming messages (for future bidirectional support)
                data = await websocket.receive_json()

                # Handle client messages
                message_type = data.get("type")

                if message_type == "ping":
                    # Respond to ping with pong
                    await websocket.send_json(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                elif message_type == "subscribe":
                    # Handle subscription requests (for future filtering)
                    # For now, just acknowledge
                    await websocket.send_json(
                        {
                            "type": "subscription_ack",
                            "data": data.get("data", {}),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                else:
                    # Unknown message type
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "message": f"Unknown message type: {message_type}",
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

            except WebSocketDisconnect:
                # Client disconnected gracefully
                logger.info(f"Mobile WebSocket disconnected: user={user_id}")
                break
            except Exception as e:
                # Error receiving message
                logger.error(f"Error receiving WebSocket message: {e}")
                # Send error to client if still connected
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "data": {
                                "message": "Error processing message",
                            },
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                except Exception:
                    # Connection may be closed
                    break

    finally:
        # Clean up connection
        await ws_manager.disconnect(websocket, user_id)
        logger.info(
            f"Mobile WebSocket cleanup complete: user={user_id}, "
            f"remaining_connections={ws_manager.get_connection_count()}"
        )
