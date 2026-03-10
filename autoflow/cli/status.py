"""
Autoflow CLI - Status Command

Show Autoflow system status including tasks, runs, and configuration.

Usage:
    autoflow status
    autoflow status --detailed
    autoflow status --json
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _get_state_manager, _print_json
from autoflow.core.config import Config


@click.command()
@click.option(
    "--detailed",
    "-d",
    is_flag=True,
    help="Show detailed status information.",
)
@click.pass_context
def status(ctx: click.Context, detailed: bool) -> None:
    """
    Show Autoflow system status.

    Displays the current state of tasks, runs, and system configuration.

    \b
    Examples:
        autoflow status
        autoflow status --detailed
        autoflow status --json
    """
    config: Config | None = ctx.obj.get("config")
    state_manager = _get_state_manager(config)

    try:
        status_data = state_manager.get_status()

        if ctx.obj.get("output_json"):
            _print_json(status_data)
            return

        # Human-readable output
        click.echo("Autoflow Status")
        click.echo("=" * 50)
        click.echo(f"State Directory: {status_data['state_dir']}")
        click.echo(f"Initialized: {status_data['initialized']}")
        click.echo("")

        # Tasks
        tasks = status_data["tasks"]
        click.echo(f"Tasks: {tasks['total']} total")
        if detailed and tasks.get("by_status"):
            for status_name, count in tasks["by_status"].items():
                click.echo(f"  {status_name}: {count}")

        # Runs
        runs = status_data["runs"]
        click.echo(f"Runs: {runs['total']} total")
        if detailed and runs.get("by_status"):
            for status_name, count in runs["by_status"].items():
                click.echo(f"  {status_name}: {count}")

        # Specs
        specs = status_data["specs"]
        click.echo(f"Specs: {specs['total']} total")

        # Memory
        memory = status_data["memory"]
        click.echo(f"Memory Entries: {memory['total']} total")

        if detailed:
            if config is None:
                click.echo("")
                click.echo("Configuration:")
                click.echo("  (Configuration not available)")
            else:
                click.echo("")
                click.echo("Configuration:")
                click.echo(f"  OpenClaw Gateway: {config.openclaw.gateway_url}")
                click.echo(f"  State Directory: {config.state_dir}")
                click.echo(f"  Scheduler Enabled: {config.scheduler.enabled}")
                click.echo(f"  CI Gates Required: {config.ci.require_all}")

    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)
        ctx.exit(1)
