"""
Autoflow CLI - Task Commands

Manage tasks for AI agent execution.

Usage:
    autoflow task list
    autoflow task show <task_id>
    autoflow task list --status pending --agent claude-code
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _get_state_manager, _print_json
from autoflow.core.config import Config
from autoflow.core.state import TaskStatus


@click.group()
def task() -> None:
    """Manage tasks."""
    pass


@task.command("list")
@click.option(
    "--status",
    "-s",
    "status_filter",
    type=click.Choice([s.value for s in TaskStatus]),
    default=None,
    help="Filter by task status.",
)
@click.option(
    "--agent",
    "-a",
    type=str,
    default=None,
    help="Filter by assigned agent.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of tasks to show.",
)
@click.pass_context
def task_list(
    ctx: click.Context,
    status_filter: str | None,
    agent: str | None,
    limit: int,
) -> None:
    """
    List tasks.

    Shows tasks filtered by status and/or agent.

    \b
    Examples:
        autoflow task list
        autoflow task list --status pending
        autoflow task list --agent claude-code --limit 10
        autoflow task list -s in_progress -a codex
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    status_enum = TaskStatus(status_filter) if status_filter else None

    tasks = state_manager.list_tasks(status=status_enum, agent=agent)[:limit]

    if ctx.obj.get("output_json"):
        _print_json({"tasks": tasks, "count": len(tasks)})
        return

    click.echo("Tasks")
    click.echo("=" * 60)

    if not tasks:
        click.echo("No tasks found.")
        return

    for task_data in tasks:
        status_val = task_data.get("status", "unknown")
        click.echo(f"\n[{task_data.get('id', 'unknown')}] {task_data.get('title', 'N/A')}")
        click.echo(f"  Status: {status_val}")
        if task_data.get("assigned_agent"):
            click.echo(f"  Agent: {task_data['assigned_agent']}")


@task.command("show")
@click.argument("task_id", type=str)
@click.pass_context
def task_show(ctx: click.Context, task_id: str) -> None:
    """
    Show details of a specific task.

    \b
    Examples:
        autoflow task show task-20240310153045
        autoflow task show task-20240310153045 --json
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    state_manager = _get_state_manager(config)
    task_data = state_manager.load_task(task_id)

    if not task_data:
        click.echo(f"Error: Task '{task_id}' not found.", err=True)
        ctx.exit(1)

    if ctx.obj.get("output_json"):
        _print_json(task_data)
        return

    click.echo(f"Task: {task_id}")
    click.echo("=" * 60)
    click.echo(f"Title: {task_data.get('title', 'N/A')}")
    click.echo(f"Status: {task_data.get('status', 'N/A')}")
    click.echo(f"Description: {task_data.get('description', 'N/A')}")
    click.echo(f"Agent: {task_data.get('assigned_agent', 'N/A')}")
    click.echo(f"Created: {task_data.get('created_at', 'N/A')}")
    click.echo(f"Updated: {task_data.get('updated_at', 'N/A')}")
