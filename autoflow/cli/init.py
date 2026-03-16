"""
Autoflow CLI - Init Command

Initialize Autoflow state directory with proper structure.

Usage:
    autoflow init
    autoflow init --force
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _get_state_manager, _print_json
from autoflow.core.config import Config


@click.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force re-initialization even if state exists.",
)
@click.pass_context
def init(ctx: click.Context, force: bool) -> None:
    """
    Initialize Autoflow state directory.

    Creates the required directory structure and default configuration
    for running Autoflow.

    \b
    Creates:
        .autoflow/          State directory
        .autoflow/specs/    Specification files
        .autoflow/tasks/    Task definitions
        .autoflow/runs/     Execution runs
        .autoflow/memory/   Persistent memory
    """
    config: Config | None = ctx.obj.get("config")
    state_manager = _get_state_manager(config)

    if state_manager.state_dir.exists() and not force:
        if not ctx.obj.get("output_json"):
            click.echo(f"State directory already exists: {state_manager.state_dir}")
            click.echo("Use --force to re-initialize.")
        else:
            _print_json(
                {
                    "status": "exists",
                    "state_dir": str(state_manager.state_dir),
                    "message": "State directory already exists. Use --force to re-initialize.",
                }
            )
        ctx.exit(1)

    try:
        state_manager.initialize()

        if not ctx.obj.get("output_json"):
            click.echo(f"Initialized Autoflow at: {state_manager.state_dir}")
            click.echo("")
            click.echo("Directory structure:")
            click.echo(f"  {state_manager.state_dir}/")
            click.echo("    specs/    - Specification files")
            click.echo("    tasks/    - Task definitions")
            click.echo("    runs/     - Execution runs")
            click.echo("    memory/   - Persistent memory")
            click.echo("    backups/  - Backup files")
        else:
            _print_json(
                {
                    "status": "initialized",
                    "state_dir": str(state_manager.state_dir),
                    "directories": [
                        str(state_manager.specs_dir),
                        str(state_manager.tasks_dir),
                        str(state_manager.runs_dir),
                        str(state_manager.memory_dir),
                        str(state_manager.backup_dir),
                    ],
                }
            )
    except Exception as e:
        click.echo(f"Error initializing: {e}", err=True)
        ctx.exit(1)
