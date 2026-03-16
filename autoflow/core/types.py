"""
Autoflow Type Definitions Module

Provides TypedDict definitions for common data structures used throughout
the Autoflow codebase. These types enable better IDE support, static analysis,
and type safety while working with JSON data structures.

Usage:
    from autoflow.core.types import TaskData, TasksFile, ReviewState

    # Type checking works
    task: TaskData = {
        "id": "task-001",
        "title": "Fix bug",
        "status": "todo"
    }

    # JSON loading with type safety
    tasks_file: TasksFile = load_json("tasks.json")
"""

from __future__ import annotations

from typing import Any, Required, TypeVar, TypedDict

# Type Variables
T = TypeVar("T")

# Type alias for JSON-serializable primitive data
JSONData = dict[str, Any] | list[Any] | str | int | float | bool | None


# === Task Types ===


class TaskNote(TypedDict, total=False):
    """A note attached to a task."""

    at: str  # ISO timestamp
    note: str


class TaskData(TypedDict, total=False):
    """
    Represents a single task in the system.

    This TypedDict provides type hints for task dictionaries while maintaining
    flexibility for optional fields. All fields are optional to support various
    task file formats and partial updates.
    """

    id: str
    title: str
    description: str
    status: str
    priority: str | int
    created_at: str
    updated_at: str
    assigned_agent: str
    labels: list[str]
    dependencies: list[str]
    metadata: dict[str, Any]
    owner_role: str
    slice_size: str
    auto_dispatch_allowed: bool
    verification_commands: list[str]
    artifacts: list[str]
    acceptance_criteria: list[str]
    notes: list[TaskNote]


class ExecutionStrategy(TypedDict, total=False):
    """Execution strategy rules for a task backlog."""

    planning_rule: str
    retry_rule: str
    parallelism_rule: str
    delivery_rule: str


class TasksFile(TypedDict, total=False):
    """
    Represents the tasks JSON file structure.

    This is the main structure for task files stored in .autoflow/tasks/.
    The tasks field is required, but other metadata fields are optional.
    """

    tasks: Required[list[TaskData]]
    updated_at: str
    spec_slug: str
    backlog_version: str
    goal: str
    execution_strategy: ExecutionStrategy


# === Review State Types ===


class ReviewApproval(TypedDict, total=False):
    """Represents an approved implementation hash."""

    hash: str
    approved_at: str
    approved_by: str


class ReviewState(TypedDict, total=False):
    """
    Represents review state for a spec.

    Tracks review validity, approvals, and feedback for spec reviews.
    Invalidated when spec artifacts change, requiring re-review.
    """

    valid: bool
    invalidated_at: str
    invalidated_reason: str
    spec_hash: str
    feedback: list[dict[str, Any]]
    feedback_count: int
    spec_changed: bool
    task_approvals: dict[str, str]


# === Strategy Memory Types ===


class StrategyMemoryCounters(TypedDict, total=False):
    """Counters for tracking run results in strategy memory."""

    needs_changes: int
    blocked: int
    failed: int


class StrategyMemoryStats(TypedDict, total=False):
    """Statistics for strategy memory tracking."""

    total_runs: int
    successful_runs: int
    needs_changes_runs: int
    blocked_runs: int
    failed_runs: int


class StrategyMemory(TypedDict, total=False):
    """
    Represents strategy memory for a spec.

    Stores reflections, playbook entries, counters, and statistics that
    persist across runs and agents for strategic learning.
    """

    reflections: list[dict[str, Any]]
    playbook: list[dict[str, Any]]
    counters: StrategyMemoryCounters
    stats: StrategyMemoryStats
    updated_at: str


# === Generic JSON Types ===


class MetadataDict(TypedDict, total=False):
    """
    Generic metadata dictionary for JSON objects.

    Provides a flexible structure for arbitrary metadata attached
    to various entities in the system.
    """

    created_at: str
    updated_at: str
    version: str
    author: str
    tags: list[str]
    archived: bool


class JsonData(TypedDict, total=False):
    """
    Generic JSON data structure with common fields.

    This provides a base type for JSON objects that include metadata
    and can be extended for specific use cases.
    """

    id: str
    metadata: MetadataDict


# === Type Aliases for Common Patterns ===


# Timestamp in ISO 8601 format
Timestamp = str

# Task status values
TaskStatus = str  # Literal["todo", "in_progress", "in_review", "needs_changes", "blocked", "done"]

# Priority levels
Priority = str  # Literal["P0", "P1", "P2", "P3"] | int

# Agent/Role identifiers
AgentId = str
RoleSlug = str

# Spec identifiers
SpecSlug = str
TaskId = str
RunId = str
