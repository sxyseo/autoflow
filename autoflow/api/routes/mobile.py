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

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
