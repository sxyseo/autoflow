"""
Autoflow CLI - Search Tasks Command

Search and filter tasks across all specs by status, owner_role, and text search.

Usage:
    autoflow search-tasks
    autoflow search-tasks --status todo
    autoflow search-tasks --owner-role implementation-runner
    autoflow search-tasks --text "authentication"
    autoflow search-tasks --json
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from autoflow.cli.utils import _get_state_manager, _print_json
from autoflow.core.config import Config


@click.command()
@click.option(
    "--status",
    "-s",
    "status_filter",
    type=str,
    default=None,
    help="Filter by task status.",
)
@click.option(
    "--owner-role",
    "-o",
    type=str,
    default=None,
    help="Filter by owner role.",
)
@click.option(
    "--text",
    "-t",
    type=str,
    default=None,
    help="Filter by text search in title and notes.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of tasks to show.",
)
@click.pass_context
def search_tasks(
    ctx: click.Context,
    status_filter: str | None,
    owner_role: str | None,
    text: str | None,
    limit: int,
) -> None:
    """
    Search and filter tasks across all specs.

    Displays tasks filtered by status, owner_role, and/or text search in title/notes.

    \b
    Examples:
        autoflow search-tasks
        autoflow search-tasks --status todo
        autoflow search-tasks --owner-role implementation-runner
        autoflow search-tasks --text "authentication"
        autoflow search-tasks -s in_progress -o implementation-runner --limit 10
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)

    # Load and filter tasks
    result = _load_and_filter_tasks(
        state_manager.state_dir,
        status=status_filter,
        owner_role=owner_role,
        text=text,
        limit=limit,
    )

    if ctx.obj.get("output_json"):
        _print_json(result)
        return

    # Human-readable output
    tasks = result["tasks"]
    total_matching = result["total_matching"]
    count = result["count"]

    click.echo("Tasks")
    click.echo("=" * 60)

    if not tasks:
        click.echo("No tasks found matching the criteria")
        click.echo(f"\nFound {total_matching} matching task(s)")
        return

    for task_data in tasks:
        task_id = task_data.get("id", "unknown")
        title = task_data.get("title", "N/A")
        status = task_data.get("status", "unknown")
        role = task_data.get("owner_role", "N/A")

        click.echo(f"\n[{task_id}] {title}")
        click.echo(f"  Status: {status}")
        click.echo(f"  Owner: {role}")

        if task_data.get("notes"):
            notes = task_data["notes"]
            if isinstance(notes, list) and notes:
                # Show first note as preview
                first_note = notes[0]
                if isinstance(first_note, dict):
                    note_content = first_note.get("content", str(first_note))
                else:
                    note_content = str(first_note)
                click.echo(f"  Notes: {note_content[:80]}{'...' if len(note_content) > 80 else ''}")

    # Show messages
    if count < total_matching:
        # Limit was applied
        click.echo(f"\nShowing {count} of {total_matching} matching task(s)")
        click.echo(f"Found {total_matching} matching task(s)")
    else:
        # No limit applied
        click.echo(f"\nFound {total_matching} matching task(s)")


def _load_and_filter_tasks(
    state_dir: Path,
    status: str | None = None,
    owner_role: str | None = None,
    text: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Load and filter tasks from all spec task files.

    Args:
        state_dir: Path to the state directory
        status: Filter by task status
        owner_role: Filter by owner role
        text: Filter by text search in title and notes
        limit: Maximum number of tasks to return

    Returns:
        Dictionary with:
        - tasks: List of filtered task dictionaries (with spec field, sorted)
        - count: Number of tasks returned (after limit)
        - total_matching: Total number of tasks matching filters (before limit)
        - filters: Dictionary of applied filters
    """
    tasks_dir = state_dir / "tasks"
    filtered_tasks: list[dict] = []

    if not tasks_dir.exists():
        return {
            "tasks": [],
            "count": 0,
            "total_matching": 0,
            "filters": {"status": status, "owner_role": owner_role, "text": text},
        }

    # Iterate through all task files (one per spec)
    for task_file in tasks_dir.glob("*.json"):
        try:
            spec_data = json.loads(task_file.read_text())
            spec_tasks = spec_data.get("tasks", [])
            # Extract spec name from filename (e.g., "api-spec.json" -> "api-spec")
            spec_name = task_file.stem

            for task in spec_tasks:
                # Apply filters
                if status and task.get("status") != status:
                    continue
                if owner_role and task.get("owner_role") != owner_role:
                    continue
                if text:
                    title = task.get("title", "")
                    notes = task.get("notes", [])

                    # Search in title
                    text_found = text.lower() in title.lower()

                    # Search in notes
                    if not text_found and notes:
                        notes_text = " ".join(
                            str(note.get("content", "") if isinstance(note, dict) else note)
                            for note in notes
                        )
                        text_found = text.lower() in notes_text.lower()

                    if not text_found:
                        continue

                # Add spec field to task
                task_with_spec = {**task, "spec": spec_name}
                filtered_tasks.append(task_with_spec)

        except (json.JSONDecodeError, IOError):
            # Skip invalid task files
            continue

    # Sort by spec and then by task ID
    filtered_tasks.sort(key=lambda t: (t.get("spec", ""), t.get("id", "")))

    # Apply limit
    total_matching = len(filtered_tasks)
    limited_tasks = filtered_tasks[:limit]

    return {
        "tasks": limited_tasks,
        "count": len(limited_tasks),
        "total_matching": total_matching,
        "filters": {"status": status, "owner_role": owner_role, "text": text},
    }
