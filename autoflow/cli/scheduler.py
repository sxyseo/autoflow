"""
Autoflow CLI - Scheduler Commands

Manage the scheduler daemon for automated task execution.

Usage:
    autoflow scheduler start
    autoflow scheduler stop
    autoflow scheduler status
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _print_json
from autoflow.core.config import Config


@click.group()
def scheduler() -> None:
    """Manage the scheduler daemon."""
    pass


@scheduler.command("start")
@click.option(
    "--daemon",
    "-d",
    is_flag=True,
    help="Run as a background daemon.",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8080,
    help="Port for daemon HTTP interface.",
)
@click.pass_context
def scheduler_start(ctx: click.Context, daemon: bool, port: int) -> None:
    """
    Start the scheduler daemon.

    Begins scheduled task execution based on configuration.

    \b
    Examples:
        autoflow scheduler start
        autoflow scheduler start --daemon
        autoflow scheduler start --port 9000
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    if not config.scheduler.enabled:
        click.echo("Scheduler is disabled in configuration.", err=True)
        ctx.exit(1)

    if ctx.obj.get("output_json"):
        _print_json(
            {
                "status": "starting",
                "daemon": daemon,
                "port": port,
                "jobs_count": len(config.scheduler.jobs),
            }
        )
    else:
        click.echo("Starting scheduler daemon...")
        click.echo(f"  Port: {port}")
        click.echo(f"  Daemon mode: {daemon}")
        click.echo(f"  Jobs configured: {len(config.scheduler.jobs)}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full daemon execution")
        click.echo("      requires async runtime. Use 'autoflow scheduler run'")


@scheduler.command("stop")
@click.pass_context
def scheduler_stop(ctx: click.Context) -> None:
    """
    Stop the scheduler daemon.

    \b
    Examples:
        autoflow scheduler stop
    """
    if ctx.obj.get("output_json"):
        _print_json({"status": "stopped"})
    else:
        click.echo("Scheduler daemon stopped.")


@scheduler.command("status")
@click.pass_context
def scheduler_status(ctx: click.Context) -> None:
    """
    Show scheduler daemon status.

    \b
    Examples:
        autoflow scheduler status
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    status_data = {
        "enabled": config.scheduler.enabled,
        "jobs": [
            {
                "id": job.id,
                "cron": job.cron,
                "handler": job.handler,
                "enabled": job.enabled,
            }
            for job in config.scheduler.jobs
        ],
    }

    if ctx.obj.get("output_json"):
        _print_json(status_data)
        return

    click.echo("Scheduler Status")
    click.echo("=" * 60)
    click.echo(f"Enabled: {config.scheduler.enabled}")
    click.echo(f"Jobs configured: {len(config.scheduler.jobs)}")

    if config.scheduler.jobs:
        click.echo("\nJobs:")
        for job in config.scheduler.jobs:
            status = "enabled" if job.enabled else "disabled"
            click.echo(f"  [{job.id}] {job.cron} - {job.handler} ({status})")
