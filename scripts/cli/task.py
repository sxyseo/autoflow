"""
Autoflow CLI - Task Commands

Manage task lists within specification documents for AI-driven development.

Usage:
    from scripts.cli.task import add_subparser, list_tasks, next_task

    # Register task commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    list_tasks(args)
    next_task(args)
"""

from __future__ import annotations

import argparse
import json
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    ROOT,
    VALID_TASK_STATUSES,
    ensure_state,
    now_stamp,
    print_json,
    write_json,
    load_tasks,
    save_tasks,
    sync_review_state,
    record_event,
    task_file,
    load_spec_metadata,
)


def _get_task_helper_functions():
    """Import task helper functions from autoflow.py (lazy import to avoid circular dependency)."""
    # These functions will be moved to utils.py in future subtasks
    import scripts.autoflow as af

    return {
        'task_lookup': af.task_lookup,
        'default_tasks': af.default_tasks,
    }


def task_lookup(data: dict, task_id: str, spec_slug: str | None = None) -> dict:
    """Wrapper for lazy-imported task_lookup function."""
    _helpers = _get_task_helper_functions()
    return _helpers['task_lookup'](data, task_id, spec_slug)


def default_tasks() -> list:
    """Wrapper for lazy-imported default_tasks function."""
    _helpers = _get_task_helper_functions()
    return _helpers['default_tasks']()


def init_tasks_cmd(args: argparse.Namespace) -> None:
    """
    Initialize tasks for a spec with default task structure.

    Creates a tasks.json file for the spec with the default task template.
    If the file already exists and --force is not provided, the existing
    tasks are loaded and returned without modification.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - force: Force re-initialization even if tasks.json exists

    Side Effects:
        Creates or updates tasks.json file
        Syncs review state with reason "tasks_initialized"
        Records a tasks.initialized event
        Prints JSON response with spec, path, created flag, and task count
    """
    ensure_state()
    load_spec_metadata(args.spec)
    path = task_file(args.spec)
    created = False
    if not path.exists() or args.force:
        write_json(
            path,
            {
                "spec_slug": args.spec,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
        sync_review_state(args.spec, reason="tasks_initialized")
        record_event(args.spec, "tasks.initialized", {"force": args.force})
        created = True
    payload = load_tasks(args.spec)
    print(
        json.dumps(
            {
                "spec": args.spec,
                "tasks_file": str(path),
                "created": created,
                "task_count": len(payload.get("tasks", [])),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def list_tasks(args: argparse.Namespace) -> None:
    """
    List all tasks for a spec in JSON format.

    Retrieves the task list for a given spec and prints it as formatted JSON.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier

    Side Effects:
        Prints JSON task list to stdout
    """
    tasks = load_tasks(args.spec)
    print_json(tasks)


def next_task_data(spec_slug: str, role: str | None = None) -> dict[str, Any] | None:
    """
    Find the next available task for a given role.

    Searches for a task that is:
    - For non-reviewer roles: status is "todo" or "needs_changes", matches the role if specified,
      and has all dependencies completed
    - For reviewer role: status is "in_review"

    Args:
        spec_slug: Spec slug identifier
        role: Optional role filter (e.g., "frontend", "backend"). If None, returns any
            available task. If "reviewer", returns tasks in review status.

    Returns:
        Task dictionary if an available task is found, None otherwise

    Side Effects:
        None
    """
    tasks = load_tasks(spec_slug)
    for task in tasks.get("tasks", []):
        if role == "reviewer":
            if task["status"] != "in_review":
                continue
        else:
            if task["status"] not in {"todo", "needs_changes"}:
                continue
            if role and task["owner_role"] != role:
                continue
        blocked = False
        for dep in task.get("depends_on", []):
            # task_lookup now handles both same-repo and cross-repo dependencies
            dep_task = task_lookup(tasks, dep, spec_slug=spec_slug)
            if dep_task["status"] != "done":
                blocked = True
                break
        if not blocked:
            return task
    return None


def next_task(args: argparse.Namespace) -> None:
    """
    Print the next available task for a spec in JSON format.

    Retrieves and displays the next available task for a given spec and role.
    If no task is available, prints an empty JSON object.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - role: Optional role filter (e.g., "frontend", "backend", "reviewer")

    Side Effects:
        Prints task data as JSON to stdout, or {} if no task is available
    """
    task = next_task_data(args.spec, args.role)
    if not task:
        print("{}")
        return
    print_json(task)


def set_task_status(args: argparse.Namespace) -> None:
    """
    Set the status of a task within a spec.

    Updates the task's status field, adds a note with timestamp, saves the
    updated tasks data, records an event, and prints the updated task as JSON.

    Valid statuses: todo, in_progress, in_review, needs_changes, blocked, done

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier to update
            - status: New status value (must be in VALID_TASK_STATUSES)
            - note: Optional note to add (defaults to status change message)

    Raises:
        SystemExit: If the provided status is not valid
    """
    if args.status not in VALID_TASK_STATUSES:
        raise SystemExit(f"invalid status: {args.status}")
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = args.status
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or f"status set to {args.status}"}
    )
    save_tasks(args.spec, data, reason="task_status_updated")
    record_event(args.spec, "task.status_updated", {"task": args.task, "status": args.status})
    print_json(task)


def update_task_cmd(args: argparse.Namespace) -> None:
    """
    Update multiple fields of a task within a spec.

    Updates one or more task fields (status, title, owner_role, acceptance_criteria,
    or notes), saves the updated tasks data, records an event, and prints the
    updated task as JSON.

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier to update
            - status: Optional new status value
            - title: Optional new title
            - owner_role: Optional new owner role
            - append_criterion: Optional acceptance criterion to append
            - note: Optional note to add (added automatically if status is set)

    Raises:
        SystemExit: If no update fields are provided or if status is invalid
    """
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    changed_fields = []
    if args.status:
        if args.status not in VALID_TASK_STATUSES:
            raise SystemExit(f"invalid status: {args.status}")
        task["status"] = args.status
        changed_fields.append("status")
    if args.title:
        task["title"] = args.title
        changed_fields.append("title")
    if args.owner_role:
        task["owner_role"] = args.owner_role
        changed_fields.append("owner_role")
    if args.append_criterion:
        task.setdefault("acceptance_criteria", []).append(args.append_criterion)
        changed_fields.append("acceptance_criteria")
    if args.note:
        task.setdefault("notes", []).append({"at": now_stamp(), "note": args.note})
        changed_fields.append("notes")
    elif args.status:
        task.setdefault("notes", []).append({"at": now_stamp(), "note": f"status set to {args.status}"})
    if not changed_fields:
        raise SystemExit("no task update provided")
    save_tasks(args.spec, data, reason="task_updated")
    record_event(args.spec, "task.updated", {"task": args.task, "fields": changed_fields})
    print(json.dumps(task, indent=2, ensure_ascii=True))


def reset_task_cmd(args: argparse.Namespace) -> None:
    """
    Reset a task to todo status.

    Resets the task's status to "todo", adds a note with timestamp, saves the
    updated tasks data, records an event, and prints the updated task as JSON.

    This is useful for recovering from blocked or failed states and allowing
    the task to be picked up again.

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier to reset
            - note: Optional note to add (defaults to "task reset to todo")

    Side Effects:
        Updates task status to "todo"
        Adds note to task notes
        Records task.reset event
        Prints updated task as JSON
    """
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = "todo"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or "task reset to todo"}
    )
    save_tasks(args.spec, data, reason="task_reset")
    record_event(args.spec, "task.reset", {"task": args.task})
    print(json.dumps(task, indent=2, ensure_ascii=True))


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register task command subparsers with the argument parser.

    This function is called during CLI initialization to add all task-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    init_tasks_cmd_parser = sub.add_parser("init-tasks", help="initialize tasks for a spec")
    init_tasks_cmd_parser.add_argument("--spec", required=True)
    init_tasks_cmd_parser.add_argument("--force", action="store_true", help="force re-initialization")
    init_tasks_cmd_parser.set_defaults(func=init_tasks_cmd)

    list_tasks_parser = sub.add_parser("list-tasks", help="list all tasks for a spec")
    list_tasks_parser.add_argument("--spec", required=True)
    list_tasks_parser.set_defaults(func=list_tasks)

    next_task_parser = sub.add_parser("next-task", help="show next available task for a role")
    next_task_parser.add_argument("--spec", required=True)
    next_task_parser.add_argument("--role", default="", help="filter by owner role")
    next_task_parser.set_defaults(func=next_task)

    set_task_status_parser = sub.add_parser("set-task-status", help="set task status")
    set_task_status_parser.add_argument("--spec", required=True)
    set_task_status_parser.add_argument("--task", required=True)
    set_task_status_parser.add_argument("--status", required=True)
    set_task_status_parser.add_argument("--note", default="")
    set_task_status_parser.set_defaults(func=set_task_status)

    update_task_parser = sub.add_parser("update-task", help="update task fields")
    update_task_parser.add_argument("--spec", required=True)
    update_task_parser.add_argument("--task", required=True)
    update_task_parser.add_argument("--status", default="")
    update_task_parser.add_argument("--title", default="")
    update_task_parser.add_argument("--owner-role", dest="owner_role", default="")
    update_task_parser.add_argument("--append-criterion", dest="append_criterion", default="")
    update_task_parser.add_argument("--note", default="")
    update_task_parser.set_defaults(func=update_task_cmd)

    reset_task_parser = sub.add_parser("reset-task", help="reset task to todo")
    reset_task_parser.add_argument("--spec", required=True)
    reset_task_parser.add_argument("--task", required=True)
    reset_task_parser.add_argument("--note", default="")
    reset_task_parser.set_defaults(func=reset_task_cmd)
