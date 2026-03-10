"""
Autoflow Web API Models Module

Provides Pydantic models for API request/response schemas. These models
define the structure of data exchanged between the web dashboard and the
FastAPI backend.

Usage:
    from autoflow.web.models import TaskResponse, RunResponse, StatusResponse

    # Create a task response
    task_resp = TaskResponse(
        id="task-001",
        title="Fix bug",
        status="pending",
        priority=5
    )

    # Create a status response
    status = StatusResponse(
        status="healthy",
        version="0.1.0",
        tasks_total=10,
        runs_total=5
    )
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from autoflow.core.state import MetadataDict


class TaskResponse(BaseModel):
    """
    API response model for a task.

    Represents a task in the system with all its properties.
    Used by GET /api/tasks and GET /api/tasks/{id} endpoints.

    Attributes:
        id: Unique task identifier
        title: Task title
        description: Detailed task description
        status: Current task status (pending, in_progress, completed, failed, cancelled)
        priority: Task priority level (1-10, higher is more urgent)
        created_at: Task creation timestamp
        updated_at: Last update timestamp
        assigned_agent: Agent assigned to this task
        labels: List of tags/labels for categorization
        dependencies: List of task IDs this task depends on
        metadata: Additional task metadata

    Example:
        >>> task = TaskResponse(
        ...     id="task-001",
        ...     title="Fix authentication bug",
        ...     status="in_progress",
        ...     priority=8
        ... )
    """

    id: str
    title: str
    description: str = ""
    status: str = "pending"
    priority: int = 5
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_agent: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    metadata: MetadataDict = Field(default_factory=dict)

    class Config:
        """Pydantic config for TaskResponse."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class RunResponse(BaseModel):
    """
    API response model for an agent run.

    Represents an agent execution run with its status and output.
    Used by GET /api/runs and GET /api/runs/{id} endpoints.

    Attributes:
        id: Unique run identifier
        task_id: Associated task ID (optional)
        agent: Name of the agent that executed
        status: Run status (started, running, completed, failed, timeout, cancelled)
        started_at: Run start timestamp
        completed_at: Run completion timestamp (None if running)
        duration_seconds: Run duration in seconds (None if running)
        workdir: Working directory for the run
        command: Command that was executed
        exit_code: Process exit code (None if running)
        output: Standard output from the run
        error: Error output if the run failed
        metadata: Additional run metadata

    Example:
        >>> run = RunResponse(
        ...     id="run-001",
        ...     task_id="task-001",
        ...     agent="claude-code",
        ...     status="running"
        ... )
    """

    id: str
    task_id: Optional[str] = None
    agent: str
    status: str = "started"
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    workdir: str = "."
    command: Optional[str] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: MetadataDict = Field(default_factory=dict)

    class Config:
        """Pydantic config for RunResponse."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class SpecResponse(BaseModel):
    """
    API response model for a specification.

    Represents a specification document in the system.
    Used by GET /api/specs and GET /api/specs/{id} endpoints.

    Attributes:
        id: Unique spec identifier
        title: Specification title
        content: Specification content (markdown)
        version: Specification version
        created_at: Creation timestamp
        updated_at: Last update timestamp
        author: Spec author (optional)
        tags: List of tags for categorization
        metadata: Additional spec metadata

    Example:
        >>> spec = SpecResponse(
        ...     id="spec-001",
        ...     title="Web Dashboard",
        ...     content="...",
        ...     version="1.0"
        ... )
    """

    id: str
    title: str
    content: str
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: MetadataDict = Field(default_factory=dict)

    class Config:
        """Pydantic config for SpecResponse."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class StatusResponse(BaseModel):
    """
    API response model for system status.

    Represents the overall system status and summary statistics.
    Used by GET /api/status endpoint.

    Attributes:
        status: System health status (healthy, degraded, error)
        version: API version
        state_dir: Path to state directory
        initialized: Whether state is initialized
        tasks_total: Total number of tasks
        tasks_by_status: Task counts grouped by status
        runs_total: Total number of runs
        runs_by_status: Run counts grouped by status
        specs_total: Total number of specs
        memory_total: Total number of memory entries

    Example:
        >>> status = StatusResponse(
        ...     status="healthy",
        ...     version="0.1.0",
        ...     tasks_total=10,
        ...     runs_total=5
        ... )
    """

    status: str = "healthy"
    version: str = "0.1.0"
    state_dir: Optional[str] = None
    initialized: bool = False
    tasks_total: int = 0
    tasks_by_status: dict[str, int] = Field(default_factory=dict)
    runs_total: int = 0
    runs_by_status: dict[str, int] = Field(default_factory=dict)
    specs_total: int = 0
    memory_total: int = 0


class ErrorResponse(BaseModel):
    """
    API response model for errors.

    Represents an error response from the API.
    Used when an endpoint encounters an error.

    Attributes:
        error: Error message
        detail: Detailed error description (optional)
        code: Error code for programmatic handling (optional)

    Example:
        >>> error = ErrorResponse(
        ...     error="Task not found",
        ...     detail="Task 'task-001' does not exist",
        ...     code="TASK_NOT_FOUND"
        ... )
    """

    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class TaskListResponse(BaseModel):
    """
    API response model for a list of tasks.

    Wraps a list of tasks with metadata.
    Used by GET /api/tasks endpoint.

    Attributes:
        tasks: List of task responses
        total: Total number of tasks
        filtered: Whether results are filtered

    Example:
        >>> response = TaskListResponse(
        ...     tasks=[task1, task2],
        ...     total=2,
        ...     filtered=False
        ... )
    """

    tasks: list[TaskResponse]
    total: int
    filtered: bool = False


class RunListResponse(BaseModel):
    """
    API response model for a list of runs.

    Wraps a list of runs with metadata.
    Used by GET /api/runs endpoint.

    Attributes:
        runs: List of run responses
        total: Total number of runs
        filtered: Whether results are filtered

    Example:
        >>> response = RunListResponse(
        ...     runs=[run1, run2],
        ...     total=2,
        ...     filtered=False
        ... )
    """

    runs: list[RunResponse]
    total: int
    filtered: bool = False


class SpecListResponse(BaseModel):
    """
    API response model for a list of specifications.

    Wraps a list of specs with metadata.
    Used by GET /api/specs endpoint.

    Attributes:
        specs: List of spec responses
        total: Total number of specs
        filtered: Whether results are filtered

    Example:
        >>> response = SpecListResponse(
        ...     specs=[spec1, spec2],
        ...     total=2,
        ...     filtered=False
        ... )
    """

    specs: list[SpecResponse]
    total: int
    filtered: bool = False
