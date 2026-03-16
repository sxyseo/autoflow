"""
Autoflow Tasks and Runs Management API Routes

Provides endpoints for managing tasks and agent execution runs.
Supports task/run CRUD operations with RBAC authorization.
Integrates with the state management for persistent storage.

Usage:
    from fastapi import FastAPI
    from autoflow.api.routes.tasks import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/tasks", tags=["Tasks and Runs"])
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from autoflow.auth import SessionManager
from autoflow.core.state import Run, RunStatus, Task, TaskStatus

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


class TaskListItem(BaseModel):
    """
    Task list item model.

    Attributes:
        id: Unique task identifier
        title: Task title
        status: Task status
        priority: Task priority (1-10)
        created_at: Task creation timestamp
        updated_at: Last update timestamp
        assigned_agent: Agent assigned to the task
        labels: List of labels associated with task
    """

    id: str
    title: str
    status: str
    priority: int
    created_at: str
    updated_at: str
    assigned_agent: Optional[str] = None
    labels: list[str] = []


class TaskListResponse(BaseModel):
    """
    Task list response model.

    Attributes:
        tasks: List of tasks
        total: Total number of tasks
    """

    tasks: list[TaskListItem]
    total: int


class TaskDetailResponse(BaseModel):
    """
    Task detail response model.

    Attributes:
        id: Unique task identifier
        title: Task title
        description: Task description
        status: Task status
        priority: Task priority (1-10)
        created_at: Task creation timestamp
        updated_at: Last update timestamp
        assigned_agent: Agent assigned to the task
        labels: List of labels associated with task
        dependencies: List of task IDs this task depends on
        metadata: Additional metadata
    """

    id: str
    title: str
    description: str
    status: str
    priority: int
    created_at: str
    updated_at: str
    assigned_agent: Optional[str] = None
    labels: list[str] = []
    dependencies: list[str] = []
    metadata: dict[str, Any] = {}


class CreateTaskRequest(BaseModel):
    """
    Create task request model.

    Attributes:
        id: Unique task identifier
        title: Task title
        description: Task description
        priority: Task priority (1-10)
        assigned_agent: Agent to assign the task to
        labels: List of labels to associate with task
        dependencies: List of task IDs this task depends on
        metadata: Additional metadata
    """

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = ""
    priority: int = Field(5, ge=1, le=10)
    assigned_agent: Optional[str] = None
    labels: list[str] = []
    dependencies: list[str] = []
    metadata: dict[str, Any] = {}


class CreateTaskResponse(BaseModel):
    """
    Create task response model.

    Attributes:
        id: Newly created task ID
        title: Task title
        status: Task status
    """

    id: str
    title: str
    status: str


class UpdateTaskRequest(BaseModel):
    """
    Update task request model.

    Attributes:
        title: Updated task title
        description: Updated task description
        status: Updated task status
        priority: Updated task priority
        assigned_agent: Updated assigned agent
        labels: Updated list of labels
        dependencies: Updated list of dependencies
        metadata: Updated metadata
    """

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    assigned_agent: Optional[str] = None
    labels: Optional[list[str]] = None
    dependencies: Optional[list[str]] = None
    metadata: Optional[dict[str, Any]] = None


class UpdateTaskResponse(BaseModel):
    """
    Update task response model.

    Attributes:
        id: Updated task ID
        title: Updated task title
        status: Updated task status
        updated_at: Update timestamp
    """

    id: str
    title: str
    status: str
    updated_at: str


class DeleteTaskResponse(BaseModel):
    """
    Delete task response model.

    Attributes:
        message: Confirmation message
    """

    message: str


class RunListItem(BaseModel):
    """
    Run list item model.

    Attributes:
        id: Unique run identifier
        task_id: Associated task ID
        agent: Agent that executed the run
        status: Run status
        started_at: Run start timestamp
        completed_at: Run completion timestamp
        duration_seconds: Run duration in seconds
    """

    id: str
    task_id: Optional[str] = None
    agent: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None


class RunListResponse(BaseModel):
    """
    Run list response model.

    Attributes:
        runs: List of runs
        total: Total number of runs
    """

    runs: list[RunListItem]
    total: int


class RunDetailResponse(BaseModel):
    """
    Run detail response model.

    Attributes:
        id: Unique run identifier
        task_id: Associated task ID
        agent: Agent that executed the run
        status: Run status
        started_at: Run start timestamp
        completed_at: Run completion timestamp
        duration_seconds: Run duration in seconds
        workdir: Working directory for the run
        command: Command that was executed
        exit_code: Process exit code
        output: Standard output from the run
        error: Standard error from the run
        metadata: Additional metadata
    """

    id: str
    task_id: Optional[str] = None
    agent: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    workdir: str
    command: Optional[str] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = {}


class CreateRunRequest(BaseModel):
    """
    Create run request model.

    Attributes:
        id: Unique run identifier
        task_id: Associated task ID
        agent: Agent to execute the run
        workdir: Working directory for the run
        command: Command to execute
        metadata: Additional metadata
    """

    id: str = Field(..., min_length=1)
    task_id: Optional[str] = None
    agent: str = Field(..., min_length=1)
    workdir: str = "."
    command: Optional[str] = None
    metadata: dict[str, Any] = {}


class CreateRunResponse(BaseModel):
    """
    Create run response model.

    Attributes:
        id: Newly created run ID
        agent: Agent that will execute the run
        status: Run status
    """

    id: str
    agent: str
    status: str


class ErrorResponse(BaseModel):
    """
    Error response model.

    Attributes:
        error: Error message
        detail: Detailed error information
    """

    error: str
    detail: Optional[str] = None


# === Task Endpoints ===


@router.get(
    "",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def list_tasks(
    status: Optional[str] = Query(None, description="Filter by status"),
    agent: Optional[str] = Query(None, description="Filter by assigned agent"),
    current_user_id: str = Depends(get_current_user_id),
) -> TaskListResponse:
    """
    List all tasks.

    Requires authentication. Supports filtering by status and agent.
    Users with read permissions can view tasks.

    Args:
        status: Optional status to filter by
        agent: Optional agent name to filter by
        current_user_id: ID of the authenticated user

    Returns:
        TaskListResponse with list of tasks

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/tasks?status=in_progress&agent=claude-code
    """
    # TODO: Implement actual task listing from state/database
    # For now, return empty list to demonstrate the pattern
    # In production, you would:
    # 1. Check user permissions (tasks:read)
    # 2. Query state manager or database for tasks
    # 3. Apply filters (status, agent)
    # 4. Return paginated results

    logger.info(f"User {current_user_id} listing tasks: status={status}, agent={agent}")

    # Placeholder: Return empty list
    return TaskListResponse(
        tasks=[],
        total=0,
    )


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Task not found"},
    },
)
async def get_task(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> TaskDetailResponse:
    """
    Get detailed information about a specific task.

    Requires authentication. Users with read permissions can view tasks.

    Args:
        task_id: ID of the task to retrieve
        current_user_id: ID of the authenticated user

    Returns:
        TaskDetailResponse with task details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or task not found

    Example:
        >>> GET /api/v1/tasks/task-123
    """
    # TODO: Implement actual task retrieval from state/database
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (tasks:read)
    # 2. Query state manager or database for task by ID
    # 3. Return task details

    logger.info(f"User {current_user_id} viewing task {task_id}")

    # Placeholder: Return mock task data
    if task_id == "task-123":
        return TaskDetailResponse(
            id=task_id,
            title="Example Task",
            description="An example task for demonstration",
            status="pending",
            priority=5,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            assigned_agent="claude-code",
            labels=["example", "backend"],
            dependencies=[],
            metadata={},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task '{task_id}' not found",
    )


@router.post(
    "",
    response_model=CreateTaskResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        409: {"model": ErrorResponse, "description": "Task already exists"},
    },
)
async def create_task(
    request: CreateTaskRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> CreateTaskResponse:
    """
    Create a new task.

    Requires authentication. Users with write permissions can create tasks.

    Args:
        request: Task creation request
        current_user_id: ID of the authenticated user

    Returns:
        CreateTaskResponse with created task details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or invalid input

    Example:
        >>> POST /api/v1/tasks
        >>> {
        ...     "id": "task-backend-api",
        ...     "title": "Implement Backend API",
        ...     "description": "Create REST API endpoints",
        ...     "priority": 8,
        ...     "assigned_agent": "claude-code",
        ...     "labels": ["backend", "api"]
        ... }
    """
    # TODO: Implement actual task creation
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (tasks:write)
    # 2. Validate input (ID format, priority range)
    # 3. Check if task ID already exists
    # 4. Create task in state manager or database
    # 5. Log audit event

    logger.info(f"User {current_user_id} creating task: {request.id}")

    # Placeholder: Return mock response
    return CreateTaskResponse(
        id=request.id,
        title=request.title,
        status="pending",
    )


@router.put(
    "/{task_id}",
    response_model=UpdateTaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Task not found"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
    },
)
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> UpdateTaskResponse:
    """
    Update an existing task.

    Requires authentication. Users with write permissions can update tasks.

    Args:
        task_id: ID of the task to update
        request: Task update request
        current_user_id: ID of the authenticated user

    Returns:
        UpdateTaskResponse with updated task details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or task not found

    Example:
        >>> PUT /api/v1/tasks/task-123
        >>> {
        ...     "title": "Updated Task Title",
        ...     "status": "in_progress"
        ... }
    """
    # TODO: Implement actual task update
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (tasks:write)
    # 2. Query task from state manager or database
    # 3. Update allowed fields
    # 4. Log audit event

    logger.info(f"User {current_user_id} updating task {task_id}")

    # Placeholder: Return mock response
    from datetime import datetime

    if task_id == "task-123":
        return UpdateTaskResponse(
            id=task_id,
            title=request.title or "Example Task",
            status=request.status or "pending",
            updated_at=datetime.utcnow().isoformat(),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Task '{task_id}' not found",
    )


@router.delete(
    "/{task_id}",
    response_model=DeleteTaskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Task not found"},
    },
)
async def delete_task(
    task_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> DeleteTaskResponse:
    """
    Delete a task.

    Requires authentication. Users with delete permissions can delete tasks.
    This is a permanent deletion and cannot be undone.

    Args:
        task_id: ID of the task to delete
        current_user_id: ID of the authenticated user

    Returns:
        DeleteTaskResponse with confirmation message

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or task not found

    Example:
        >>> DELETE /api/v1/tasks/task-123
    """
    # TODO: Implement actual task deletion
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (tasks:delete)
    # 2. Query task from state manager or database
    # 3. Delete task
    # 4. Log audit event

    logger.info(f"User {current_user_id} deleting task {task_id}")

    # Placeholder: Return mock response
    return DeleteTaskResponse(message=f"Task '{task_id}' deleted successfully")


# === Run Endpoints ===


@router.get(
    "/runs",
    response_model=RunListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
    },
)
async def list_runs(
    status: Optional[str] = Query(None, description="Filter by status"),
    agent: Optional[str] = Query(None, description="Filter by agent"),
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of runs"),
    current_user_id: str = Depends(get_current_user_id),
) -> RunListResponse:
    """
    List all agent execution runs.

    Requires authentication. Supports filtering by status, agent, and task ID.
    Users with read permissions can view runs.

    Args:
        status: Optional status to filter by
        agent: Optional agent name to filter by
        task_id: Optional task ID to filter by
        limit: Maximum number of runs to return (1-1000)
        current_user_id: ID of the authenticated user

    Returns:
        RunListResponse with list of runs

    Raises:
        HTTPException: If not authenticated or insufficient permissions

    Example:
        >>> GET /api/v1/tasks/runs?status=running&agent=claude-code
    """
    # TODO: Implement actual run listing from state/database
    # For now, return empty list to demonstrate the pattern
    # In production, you would:
    # 1. Check user permissions (runs:read)
    # 2. Query state manager or database for runs
    # 3. Apply filters (status, agent, task_id)
    # 4. Return paginated results

    logger.info(
        f"User {current_user_id} listing runs: status={status}, agent={agent}, task_id={task_id}"
    )

    # Placeholder: Return empty list
    return RunListResponse(
        runs=[],
        total=0,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunDetailResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        404: {"model": ErrorResponse, "description": "Run not found"},
    },
)
async def get_run(
    run_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> RunDetailResponse:
    """
    Get detailed information about a specific run.

    Requires authentication. Users with read permissions can view runs.

    Args:
        run_id: ID of the run to retrieve
        current_user_id: ID of the authenticated user

    Returns:
        RunDetailResponse with run details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or run not found

    Example:
        >>> GET /api/v1/tasks/runs/run-123
    """
    # TODO: Implement actual run retrieval from state/database
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (runs:read)
    # 2. Query state manager or database for run by ID
    # 3. Return run details

    logger.info(f"User {current_user_id} viewing run {run_id}")

    # Placeholder: Return mock run data
    if run_id == "run-123":
        return RunDetailResponse(
            id=run_id,
            task_id="task-123",
            agent="claude-code",
            status="completed",
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T00:05:00Z",
            duration_seconds=300.0,
            workdir="/workspace",
            command="echo 'hello'",
            exit_code=0,
            output="hello\n",
            error=None,
            metadata={},
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run '{run_id}' not found",
    )


@router.post(
    "/runs",
    response_model=CreateRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "Insufficient permissions"},
        400: {"model": ErrorResponse, "description": "Invalid input"},
        409: {"model": ErrorResponse, "description": "Run already exists"},
    },
)
async def create_run(
    request: CreateRunRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> CreateRunResponse:
    """
    Create a new agent execution run.

    Requires authentication. Users with write permissions can create runs.

    Args:
        request: Run creation request
        current_user_id: ID of the authenticated user

    Returns:
        CreateRunResponse with created run details

    Raises:
        HTTPException: If not authenticated, insufficient permissions, or invalid input

    Example:
        >>> POST /api/v1/tasks/runs
        >>> {
        ...     "id": "run-backend-test",
        ...     "task_id": "task-123",
        ...     "agent": "claude-code",
        ...     "workdir": "/workspace"
        ... }
    """
    # TODO: Implement actual run creation
    # For now, return placeholder response
    # In production, you would:
    # 1. Check user permissions (runs:write)
    # 2. Validate input (ID format, agent name)
    # 3. Check if run ID already exists
    # 4. Create run in state manager or database
    # 5. Log audit event

    logger.info(f"User {current_user_id} creating run: {request.id}")

    # Placeholder: Return mock response
    return CreateRunResponse(
        id=request.id,
        agent=request.agent,
        status="started",
    )
