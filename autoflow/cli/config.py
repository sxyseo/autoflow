"""
Autoflow CLI - Config Commands

Manage Autoflow configuration settings.

Usage:
    autoflow config show
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _print_json
from autoflow.core.config import Config


@click.group()
def config() -> None:
    """Configuration commands."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """
    Show current configuration.

    Displays the current Autoflow configuration including
    agent settings, scheduler configuration, and CI gate settings.

    \b
    Examples:
        autoflow config show
        autoflow config show --json
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    if ctx.obj.get("output_json"):
        _print_json(config.model_dump())
        return

    click.echo("Current Configuration")
    click.echo("=" * 60)
    click.echo(f"State Directory: {config.state_dir}")
    click.echo(f"OpenClaw Gateway: {config.openclaw.gateway_url}")
    click.echo(f"OpenClaw Config: {config.openclaw.config_path}")
    click.echo(f"Scheduler Enabled: {config.scheduler.enabled}")
    click.echo(f"CI Require All: {config.ci.require_all}")
    click.echo("")
    click.echo("Agents:")
    click.echo(f"  claude-code: {config.agents.claude_code.command}")
    click.echo(f"  codex: {config.agents.codex.command}")
