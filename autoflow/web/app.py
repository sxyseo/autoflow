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
    GET /api/runs      - List all runs
    GET /api/runs/{id} - Get specific run details with logs
    WS  /ws            - WebSocket endpoint for real-time updates
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional, Set

from fastapi import (
    FastAPI,
    HTTPException,
    status as http_status,
    WebSocket,
    WebSocketDisconnect,
)

from autoflow import __version__
from autoflow.core.config import Config, load_config, get_state_dir
from autoflow.core.state import StateManager
from autoflow.web.models import (
    StatusResponse,
    TaskResponse,
    TaskListResponse,
    RunResponse,
    RunListResponse,
)
from autoflow.web.monitor import WebSocketConnectionManager, StateMonitor


# FastAPI application instance
app = FastAPI(
    title="Autoflow Dashboard API",
    description="Real-time monitoring dashboard for autonomous AI development workflows",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# Global connection manager instance
manager = WebSocketConnectionManager()

# Global state monitor instance (initialized on startup)
monitor: Optional[StateMonitor] = None


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


@app.on_event("startup")
async def startup_event() -> None:
    """
    Startup event handler.

    Initializes and starts the state monitor when the FastAPI application starts.
    The monitor watches for file changes in the state directory and broadcasts
    updates to connected WebSocket clients.
    """
    global monitor

    try:
        # Load configuration and get state directory
        config = load_config()
        state_dir = get_state_dir(config)

        # Create and start the monitor
        monitor = StateMonitor(state_dir)
        await monitor.start()

    except Exception as e:
        # Log error but don't prevent startup
        pass


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """
    Shutdown event handler.

    Stops the state monitor when the FastAPI application shuts down.
    Ensures clean shutdown of background monitoring tasks.
    """
    global monitor

    if monitor is not None:
        try:
            await monitor.stop()
        except Exception:
            # Ignore errors during shutdown
            pass
        finally:
            monitor = None


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


@app.get(
    "/api/runs",
    response_model=RunListResponse,
    tags=["runs"],
    responses={
        200: {"description": "Successfully retrieved run list"},
        500: {"description": "Internal server error"},
    },
)
async def list_runs() -> RunListResponse:
    """
    List all runs in the system.

    Returns a list of all runs with their current status and metadata.
    Runs are sorted by start date (newest first).

    Returns:
        RunListResponse: List of runs with metadata.

    Raises:
        HTTPException: If there's an error retrieving run information.
    """
    try:
        # Load configuration
        config = load_config()
        state_manager = _get_state_manager(config)

        # Get all runs from state manager
        runs_data = state_manager.list_runs()

        # Convert to RunResponse models
        runs = [
            RunResponse(
                id=run.get("id", ""),
                task_id=run.get("task_id"),
                agent=run.get("agent", ""),
                status=run.get("status", "started"),
                started_at=run.get("started_at", ""),
                completed_at=run.get("completed_at"),
                duration_seconds=run.get("duration_seconds"),
                workdir=run.get("workdir", "."),
                command=run.get("command"),
                exit_code=run.get("exit_code"),
                output=run.get("output"),
                error=run.get("error"),
                metadata=run.get("metadata", {}),
            )
            for run in runs_data
        ]

        # Build response
        response = RunListResponse(
            runs=runs,
            total=len(runs),
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
    "/api/runs/{run_id}",
    response_model=RunResponse,
    tags=["runs"],
    responses={
        200: {"description": "Successfully retrieved run"},
        404: {"description": "Run not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_run(run_id: str) -> RunResponse:
    """
    Get details of a specific run.

    Returns detailed information about a single run including its
    current status, output, error logs, and metadata.

    Args:
        run_id: Unique identifier of the run

    Returns:
        RunResponse: Detailed run information.

    Raises:
        HTTPException: If run is not found or error occurs.
    """
    try:
        # Load configuration
        config = load_config()
        state_manager = _get_state_manager(config)

        # Get run from state manager
        run_data = state_manager.load_run(run_id)

        if run_data is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Run '{run_id}' not found",
            )

        # Convert to RunResponse model
        response = RunResponse(
            id=run_data.get("id", run_id),
            task_id=run_data.get("task_id"),
            agent=run_data.get("agent", ""),
            status=run_data.get("status", "started"),
            started_at=run_data.get("started_at", ""),
            completed_at=run_data.get("completed_at"),
            duration_seconds=run_data.get("duration_seconds"),
            workdir=run_data.get("workdir", "."),
            command=run_data.get("command"),
            exit_code=run_data.get("exit_code"),
            output=run_data.get("output"),
            error=run_data.get("error"),
            metadata=run_data.get("metadata", {}),
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


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time updates.

    Provides real-time updates for:
    - Task status changes
    - Run status changes
    - System status updates

    Clients connect to this endpoint and receive JSON messages with updates.
    Connection is kept alive and receives updates as they occur.

    Message format:
        {
            "type": "task" | "run" | "status" | "error",
            "action": "created" | "updated" | "deleted",
            "data": {...}
        }

    Example:
        >>> import websockets
        >>> async with websockets.connect("ws://localhost:8000/ws") as ws:
        ...     message = await ws.recv()

    Args:
        websocket: The WebSocket connection instance.

    Raises:
        HTTPException: If there's an error establishing the connection.
    """
    await manager.connect(websocket)

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connection",
                "status": "connected",
                "message": "Connected to Autoflow real-time updates",
            }
        )

        # Keep connection alive and listen for incoming messages
        while True:
            try:
                # Receive any incoming messages (for future bidirectional support)
                data = await websocket.receive_text()

                # Parse and handle incoming messages if needed
                # For now, we just acknowledge receipt
                try:
                    message = json.loads(data)
                    # Echo back or process the message if needed
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    # Invalid JSON, send error
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Invalid JSON format",
                        }
                    )

            except WebSocketDisconnect:
                # Client disconnected
                break
            except Exception as e:
                # Error receiving message, send error response
                try:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"Error processing message: {e}",
                        }
                    )
                except Exception:
                    # Connection may be closed
                    break

    except Exception as e:
        # Error in connection handling
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"Connection error: {e}",
                }
            )
        except Exception:
            # Connection may be closed
            pass
    finally:
        # Always disconnect on exit
        await manager.disconnect(websocket)
