"""
Autoflow Core Commands - Pure data-returning functions

This module provides pure functions that extract and return data from the Autoflow state.
These functions mirror CLI commands but return data structures instead of printing JSON,
making them suitable for direct import by orchestration scripts.

Functions:
- get_workflow_state: Get complete workflow state for a spec
- get_task_history: Get run history for a specific task
- get_strategy_summary: Get strategy memory summary
- sync_agents: Sync discovered agents to agents.json
- taskmaster_import: Import tasks from Taskmaster format
- taskmaster_export: Export tasks to Taskmaster format
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# These functions will be implemented in subsequent subtasks
# This file establishes the module structure and public API


def get_workflow_state(spec_slug: str) -> dict[str, Any]:
    """
    Get complete workflow state for a spec.

    Args:
        spec_slug: Spec identifier (e.g., "001-example")

    Returns:
        Dict containing:
        - spec: Spec identifier
        - review_status: Review approval status
        - worktree: Git worktree information
        - fix_request_present: Whether QA fix request exists
        - fix_request: QA fix request data
        - strategy_summary: Strategy memory summary
        - active_runs: List of active run metadata
        - ready_tasks: Tasks ready to be executed
        - blocked_or_active_tasks: Tasks that are blocked or active
        - blocking_reason: Reason if workflow is blocked
        - recommended_next_action: Next recommended task to execute

    Raises:
        SystemExit: If spec task file is missing
    """
    # TODO: Implement in subtask-1-2
    raise NotImplementedError("get_workflow_state will be implemented in subtask-1-2")


def get_task_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get run history for a specific task.

    Args:
        spec_slug: Spec identifier
        task_id: Task identifier (e.g., "task-1")
        limit: Maximum number of history entries to return

    Returns:
        List of run metadata dicts, sorted by creation time, most recent last.
        Each dict contains run information (id, role, result, created_at, etc.)
    """
    # TODO: Implement in subtask-1-3
    raise NotImplementedError("get_task_history will be implemented in subtask-1-3")


def sync_agents(overwrite: bool = False) -> dict[str, Any]:
    """
    Sync discovered agents to agents.json configuration file.

    Discovers available CLI agents (claude, codex) and ACP agents from system config,
    then merges them into the agents.json file. Existing agents are preserved unless
    overwrite=True.

    Args:
        overwrite: If True, overwrite existing agent configs. If False, skip existing.

    Returns:
        Dict containing:
        - agents_file: Path to agents.json
        - added: List of agent names that were added
        - total_agents: Total number of agents in file after sync
    """
    # TODO: Implement in subtask-1-4
    raise NotImplementedError("sync_agents will be implemented in subtask-1-4")


def get_strategy_summary(spec_slug: str) -> dict[str, Any]:
    """
    Get strategy memory summary for a spec.

    Args:
        spec_slug: Spec identifier

    Returns:
        Dict containing:
        - updated_at: Last update timestamp
        - playbook: Learned rules and patterns
        - planner_notes: Recent planner notes
        - recent_reflections: Recent reflection entries
        - stats: Strategy statistics
    """
    # TODO: Implement in subtask-1-5
    raise NotImplementedError("get_strategy_summary will be implemented in subtask-1-5")


def taskmaster_export(spec_slug: str, output: str | None = None) -> dict[str, Any] | Path:
    """
    Export tasks to Taskmaster format.

    Args:
        spec_slug: Spec identifier
        output: Optional output file path. If provided, writes to file and returns Path.
                If None, returns the export payload dict.

    Returns:
        If output is None: Export payload dict with project, exported_at, and tasks list.
        If output is provided: Path to the written file.
    """
    # TODO: Implement in subtask-1-6
    raise NotImplementedError("taskmaster_export will be implemented in subtask-1-6")


def taskmaster_import(spec_slug: str, input: str) -> dict[str, Any]:
    """
    Import tasks from Taskmaster format.

    Reads a Taskmaster export file (JSON with tasks array), normalizes the task data,
    and imports it into the spec's task file. Records an event and syncs review state.

    Args:
        spec_slug: Spec identifier
        input: Path to input file (JSON)

    Returns:
        Dict containing:
        - spec: Spec identifier
        - task_count: Number of tasks imported
    """
    # TODO: Implement in subtask-1-6
    raise NotImplementedError("taskmaster_import will be implemented in subtask-1-6")


__all__ = [
    "get_workflow_state",
    "get_task_history",
    "sync_agents",
    "get_strategy_summary",
    "taskmaster_import",
    "taskmaster_export",
]
