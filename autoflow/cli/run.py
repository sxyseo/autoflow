"""
Autoflow CLI - Run Command

Run a task with an AI agent.

Usage:
    autoflow run "Fix the login bug"
    autoflow run "Add tests" --agent codex
    autoflow run --skill CONTINUOUS_ITERATOR
    autoflow run --resume
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from autoflow.core.config import Config
from autoflow.core.state import TaskStatus
from autoflow.cli.utils import _get_state_manager, _print_json


@click.command()
@click.argument("task", required=False)
@click.option(
    "--agent",
    "-a",
    type=click.Choice(["claude-code", "codex", "openclaw"]),
    default="claude-code",
    help="Agent to use for execution.",
)
@click.option(
    "--skill",
    "-k",
    type=str,
    default=None,
    help="Skill to execute.",
)
@click.option(
    "--workdir",
    "-w",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Working directory for the task.",
)
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=300,
    help="Timeout in seconds.",
)
@click.option(
    "--resume",
    "-r",
    is_flag=True,
    help="Resume the last session.",
)
@click.pass_context
def run(
    ctx: click.Context,
    task: Optional[str],
    agent: str,
    skill: Optional[str],
    workdir: Optional[Path],
    timeout: int,
    resume: bool,
) -> None:
    """
    Run a task with an AI agent.

    Executes a task using the specified agent and optionally a skill.
    Supports session resumption for continued work.

    \b
    Examples:
        autoflow run "Fix the login bug"
        autoflow run "Add tests" --agent codex
        autoflow run --skill CONTINUOUS_ITERATOR
        autoflow run --resume
    """
    if not task and not skill and not resume:
        click.echo("Error: Either TASK, --skill, or --resume is required.", err=True)
        ctx.exit(1)

    config: Optional[Config] = ctx.obj.get("config")
    state_manager = _get_state_manager(config)

    try:
        # Create a task record
        task_id = f"task-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        task_data = {
            "id": task_id,
            "title": task or f"Execute skill: {skill}",
            "description": task or "",
            "status": TaskStatus.IN_PROGRESS.value,
            "assigned_agent": agent,
            "metadata": {
                "skill": skill,
                "workdir": str(workdir) if workdir else None,
                "timeout": timeout,
                "resume": resume,
            },
        }

        state_manager.initialize()
        state_manager.save_task(task_id, task_data)

        if ctx.obj.get("output_json"):
            _print_json({
                "status": "started",
                "task_id": task_id,
                "agent": agent,
                "skill": skill,
            })
        else:
            click.echo(f"Started task: {task_id}")
            click.echo(f"  Agent: {agent}")
            if skill:
                click.echo(f"  Skill: {skill}")
            click.echo(f"  Status: {TaskStatus.IN_PROGRESS.value}")
            click.echo("")
            click.echo("Note: This is a CLI placeholder. Full execution requires")
            click.echo("      agent adapters to be configured and available.")

    except Exception as e:
        click.echo(f"Error running task: {e}", err=True)
        ctx.exit(1)
