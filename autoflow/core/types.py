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

from typing import Any, Required, TypedDict


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

    Tracks which implementations have been approved and provides
    structured review data for QA gating.
    """

    approved_hashes: list[ReviewApproval]
    last_review_run: str
    review_summary: str
    needs_review: bool


# === Strategy Memory Types ===


class StrategyMemory(TypedDict, total=False):
    """
    Represents strategy memory for a spec.

    Stores strategic context, decisions, and learnings that persist
    across runs and agents.
    """

    spec_slug: str
    updated_at: str
    strategic_context: str
    key_decisions: list[str]
    lessons_learned: list[str]
    retry_history: list[dict[str, Any]]
    optimization_hints: list[str]


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
