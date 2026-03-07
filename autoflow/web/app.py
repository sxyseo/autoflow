"""
Autoflow Web Application - FastAPI App

This module provides the FastAPI application with REST and WebSocket endpoints
for the web dashboard. Exposes state data from StateManager for monitoring.

Usage:
    import uvicorn
    from autoflow.web.app import app

    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000)

Endpoints:
    GET /              - Root endpoint with basic info
    GET /api/status    - System status and statistics
    GET /api/tasks     - List all tasks
    GET /api/tasks/{id} - Get specific task details
    GET /api/runs      - List all runs (future)
    GET /api/runs/{id} - Get specific run (future)
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, status as http_status

from autoflow import __version__
from autoflow.core.config import Config, load_config, get_state_dir
from autoflow.core.state import StateManager
from autoflow.web.models import StatusResponse, TaskResponse, TaskListResponse


# FastAPI application instance
app = FastAPI(
    title="Autoflow Dashboard API",
    description="Real-time monitoring dashboard for autonomous AI development workflows",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


def _get_state_manager(config: Optional[Config] = None) -> StateManager:
    """
    Get a StateManager instance.

    Creates a StateManager with the appropriate state directory based on
    the provided or default configuration.

    Args:
        config: Optional configuration object. Uses default if not provided.

    Returns:
        StateManager: Configured state manager instance.
    """
    state_dir = get_state_dir(config)
    return StateManager(state_dir)


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """
    Root endpoint - API information.

    Provides basic information about the API and links to documentation.

    Returns:
        Dictionary with API status and message.
    """
    return {
        "status": "ok",
        "message": "Autoflow Dashboard API",
        "version": __version__,
        "docs": "/docs",
    }


@app.get(
    "/api/status",
    response_model=StatusResponse,
    tags=["status"],
    responses={
        200: {"description": "Successfully retrieved system status"},
        500: {"description": "Internal server error"},
    },
)
async def get_status() -> StatusResponse:
    """
    Get system status and statistics.

    Returns comprehensive system status including:
    - Overall health status
    - Task counts (total and by status)
    - Run counts (total and by status)
    - Spec and memory counts
    - State directory information

    Returns:
        StatusResponse: System status with all summary statistics.

    Raises:
        HTTPException: If there's an error retrieving status information.
    """
    try:
        # Load configuration
        config = load_config()
        state_manager = _get_state_manager(config)

        # Get status data from state manager
        status_data = state_manager.get_status()

        # Build response using the StatusResponse model
        response = StatusResponse(
            status="healthy",
            version=__version__,
            state_dir=str(status_data.get("state_dir", "")),
            initialized=status_data.get("initialized", False),
            tasks_total=status_data.get("tasks", {}).get("total", 0),
            tasks_by_status=status_data.get("tasks", {}).get("by_status", {}),
            runs_total=status_data.get("runs", {}).get("total", 0),
            runs_by_status=status_data.get("runs", {}).get("by_status", {}),
            specs_total=status_data.get("specs", {}).get("total", 0),
            memory_total=status_data.get("memory", {}).get("total", 0),
        )

        return response

    except FileNotFoundError as e:
        # State directory not initialized
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"State directory not initialized: {e}",
        ) from e
    except PermissionError as e:
        # Permission error accessing state
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied accessing state: {e}",
        ) from e
    except Exception as e:
        # Generic internal server error
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}",
        ) from e


@app.get(
    "/api/tasks",
    response_model=TaskListResponse,
    tags=["tasks"],
    responses={
        200: {"description": "Successfully retrieved task list"},
        500: {"description": "Internal server error"},
    },
)
async def list_tasks() -> TaskListResponse:
    """
    List all tasks in the system.

    Returns a list of all tasks with their current status and metadata.
    Tasks are sorted by creation date (newest first).

    Returns:
        TaskListResponse: List of tasks with metadata.

    Raises:
        HTTPException: If there's an error retrieving task information.
    """
    try:
        # Load configuration
        config = load_config()
        state_manager = _get_state_manager(config)

        # Get all tasks from state manager
        tasks_data = state_manager.list_tasks()

        # Convert to TaskResponse models
        tasks = [
            TaskResponse(
                id=task.get("id", ""),
                title=task.get("title", ""),
                description=task.get("description", ""),
                status=task.get("status", "pending"),
                priority=task.get("priority", 5),
                created_at=task.get("created_at", ""),
                updated_at=task.get("updated_at", ""),
                assigned_agent=task.get("assigned_agent"),
                labels=task.get("labels", []),
                dependencies=task.get("dependencies", []),
                metadata=task.get("metadata", {}),
            )
            for task in tasks_data
        ]

        # Build response
        response = TaskListResponse(
            tasks=tasks,
            total=len(tasks),
            filtered=False,
        )

        return response

    except FileNotFoundError as e:
        # State directory not initialized
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"State directory not initialized: {e}",
        ) from e
    except PermissionError as e:
        # Permission error accessing state
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied accessing state: {e}",
        ) from e
    except Exception as e:
        # Generic internal server error
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}",
        ) from e


@app.get(
    "/api/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["tasks"],
    responses={
        200: {"description": "Successfully retrieved task"},
        404: {"description": "Task not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_task(task_id: str) -> TaskResponse:
    """
    Get details of a specific task.

    Returns detailed information about a single task including its
    current status, metadata, and relationships.

    Args:
        task_id: Unique identifier of the task

    Returns:
        TaskResponse: Detailed task information.

    Raises:
        HTTPException: If task is not found or error occurs.
    """
    try:
        # Load configuration
        config = load_config()
        state_manager = _get_state_manager(config)

        # Get task from state manager
        task_data = state_manager.load_task(task_id)

        if task_data is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_id}' not found",
            )

        # Convert to TaskResponse model
        response = TaskResponse(
            id=task_data.get("id", task_id),
            title=task_data.get("title", ""),
            description=task_data.get("description", ""),
            status=task_data.get("status", "pending"),
            priority=task_data.get("priority", 5),
            created_at=task_data.get("created_at", ""),
            updated_at=task_data.get("updated_at", ""),
            assigned_agent=task_data.get("assigned_agent"),
            labels=task_data.get("labels", []),
            dependencies=task_data.get("dependencies", []),
            metadata=task_data.get("metadata", {}),
        )

        return response

    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except FileNotFoundError as e:
        # State directory not initialized
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"State directory not initialized: {e}",
        ) from e
    except PermissionError as e:
        # Permission error accessing state
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied accessing state: {e}",
        ) from e
    except Exception as e:
        # Generic internal server error
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e}",
        ) from e


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """
    Health check endpoint.

    Simple endpoint for load balancers and monitoring systems to check
    if the API is running.

    Returns:
        Dictionary with health status.
    """
    return {"status": "healthy"}
