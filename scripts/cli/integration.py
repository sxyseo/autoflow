"""
Autoflow CLI - Integration Commands

Manage integration with external project management tools like Taskmaster.

Usage:
    from scripts.cli.integration import add_subparser, export_taskmaster_cmd

    # Register integration commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    export_taskmaster_cmd(args)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    VALID_TASK_STATUSES,
    invalidate_tasks_cache,
    load_tasks,
    now_stamp,
    print_json,
    read_json,
    record_event,
    sync_review_state,
    task_file,
    write_json,
)


def taskmaster_payload(spec_slug: str) -> dict[str, Any]:
    """
    Build Taskmaster-compatible export payload from spec tasks.

    Transforms Autoflow task data into the Taskmaster JSON format, mapping
    Autoflow field names to Taskmaster conventions. The payload includes
    project metadata and a list of tasks with their dependencies.

    Args:
        spec_slug: Slug identifier of the spec to export

    Returns:
        Dictionary containing:
        - project: Spec slug identifier
        - exported_at: ISO 8601 timestamp of export
        - tasks: List of task dictionaries in Taskmaster format
    """
    tasks = load_tasks(spec_slug)
    return {
        "project": spec_slug,
        "exported_at": now_stamp(),
        "tasks": [
            {
                "id": task["id"],
                "title": task["title"],
                "status": task["status"],
                "dependencies": task.get("depends_on", []),
                "owner_role": task["owner_role"],
                "acceptanceCriteria": task.get("acceptance_criteria", []),
                "notes": task.get("notes", []),
            }
            for task in tasks.get("tasks", [])
        ],
    }


def export_taskmaster_cmd(args: argparse.Namespace) -> None:
    """
    Export spec tasks in Taskmaster JSON format.

    Creates a Taskmaster-compatible JSON export of all tasks in a spec.
    Can write to a file or print to stdout. Useful for migrating tasks
    to external project management tools or for backup purposes.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug to export
            - output: Optional file path to write JSON (prints to stdout if None)
    """
    payload = taskmaster_payload(args.spec)
    if args.output:
        output = Path(args.output)
        write_json(output, payload)
        print(str(output))
        return
    print_json(payload)


def normalize_imported_task(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """
    Normalize an imported task entry to Autoflow format.

    Handles multiple input formats (Taskmaster, legacy Autoflow, etc.) and
    converts them to the standard Autoflow task schema. Provides sensible
    defaults for missing fields and validates status values.

    Args:
        entry: Raw task dictionary from import source. May contain various
            field names (e.g., "dependencies" vs "depends_on",
            "acceptanceCriteria" vs "acceptance_criteria")
        index: Numeric index used for generating default task ID

    Returns:
        Normalized task dictionary with fields:
        - id: Task identifier (from entry or generated as T{index})
        - title: Task title (from "title", "name", or generated)
        - status: Validated task status (defaults to "todo")
        - depends_on: List of task dependency IDs
        - owner_role: Role responsible for the task
        - acceptance_criteria: List of acceptance criteria
        - notes: List of task notes
    """
    depends = entry.get("depends_on", entry.get("dependencies", [])) or []
    criteria = entry.get("acceptance_criteria", entry.get("acceptanceCriteria", [])) or []
    status = entry.get("status", "todo")
    if status not in VALID_TASK_STATUSES:
        status = "todo"
    return {
        "id": entry.get("id") or f"T{index}",
        "title": entry.get("title", entry.get("name", f"Task {index}")),
        "status": status,
        "depends_on": depends,
        "owner_role": entry.get("owner_role", entry.get("role", "implementation-runner")),
        "acceptance_criteria": criteria,
        "notes": entry.get("notes", []),
    }


def import_taskmaster_cmd(args: argparse.Namespace) -> None:
    """
    Import tasks from Taskmaster JSON format into a spec.

    Reads a JSON file containing task data in Taskmaster or compatible format,
    normalizes the entries to Autoflow schema, and updates the spec's task file.
    Accepts both a list of tasks or a dict with a "tasks" key.

    Synchronizes review state after import and records the import event for
    audit trail purposes.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug to import tasks into
            - input: Path to JSON file containing task data

    Side Effects:
        - Overwrites the spec's task file with imported data
        - Syncs review state (may clear existing review data)
        - Records "taskmaster.imported" event in spec history
    """
    payload = read_json(Path(args.input))
    tasks_input = payload if isinstance(payload, list) else payload.get("tasks", [])
    normalized = [
        normalize_imported_task(item, index)
        for index, item in enumerate(tasks_input, start=1)
    ]
    data = {
        "spec_slug": args.spec,
        "updated_at": now_stamp(),
        "tasks": normalized,
    }
    write_json(task_file(args.spec), data)
    invalidate_tasks_cache()
    sync_review_state(args.spec, reason="taskmaster_import")
    record_event(args.spec, "taskmaster.imported", {"task_count": len(normalized), "source": args.input})
    print_json({"spec": args.spec, "task_count": len(normalized)})


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register integration command subparsers with the argument parser.

    This function is called during CLI initialization to add all integration-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    export_taskmaster = sub.add_parser("export-taskmaster", help="export Autoflow tasks in a Taskmaster-friendly JSON shape")
    export_taskmaster.add_argument("--spec", required=True)
    export_taskmaster.add_argument("--output", default="")
    export_taskmaster.set_defaults(func=export_taskmaster_cmd)

    import_taskmaster = sub.add_parser("import-taskmaster", help="import task data from a Taskmaster-style JSON file")
    import_taskmaster.add_argument("--spec", required=True)
    import_taskmaster.add_argument("--input", required=True)
    import_taskmaster.set_defaults(func=import_taskmaster_cmd)
