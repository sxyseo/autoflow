"""
Autoflow CLI - Main Entry Point

Main command group and context setup for the Autoflow CLI.
This module provides the core Click group that all CLI commands attach to.

Usage:
    autoflow --help
    autoflow --version
    autoflow --config /path/to/config.yaml <command>
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from autoflow import __version__
from autoflow.cli.agent import agent
from autoflow.cli.init import init
from autoflow.cli.run import run
from autoflow.cli.scheduler import scheduler
from autoflow.cli.skill import skill
from autoflow.cli.status import status
from autoflow.cli.task import task
from autoflow.core.config import Config, load_config


# Click context settings
CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
    "auto_envvar_prefix": "AUTOFLOW",
}


@click.group(
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.option(
    "--version",
    "-V",
    is_flag=True,
    help="Show version and exit.",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=False, path_type=Path),
    default=None,
    envvar="AUTOFLOW_CONFIG",
    help="Path to configuration file.",
)
@click.option(
    "--state-dir",
    "-s",
    type=click.Path(exists=False, path_type=Path),
    default=None,
    envvar="AUTOFLOW_STATE_DIR",
    help="Path to state directory.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="Increase verbosity (can be used multiple times).",
)
@click.pass_context
def main(
    ctx: click.Context,
    version: bool,
    config_path: Optional[Path],
    state_dir: Optional[Path],
    output_json: bool,
    verbose: int,
) -> None:
    """
    Autoflow - Autonomous AI Development System

    An open-source system for autonomous code development, testing,
    review, and deployment with minimal human intervention.

    \b
    Quick Start:
        autoflow init              # Initialize Autoflow
        autoflow status            # Check system status
        autoflow run "Fix bug"     # Run a task
        autoflow scheduler start   # Start the scheduler

    \b
    Examples:
        autoflow --help
        autoflow agent list
        autoflow skill run CONTINUOUS_ITERATOR
        autoflow ci verify --all

    For more information, visit: https://github.com/autoflow/autoflow
    """
    ctx.ensure_object(dict)

    if version:
        click.echo(f"autoflow version {__version__}")
        ctx.exit(0)

    # Store options in context
    ctx.obj["config_path"] = config_path
    ctx.obj["state_dir"] = state_dir
    ctx.obj["output_json"] = output_json
    ctx.obj["verbose"] = verbose

    # Load configuration
    try:
        config = load_config(str(config_path) if config_path else None)
        ctx.obj["config"] = config
    except Exception as e:
        if verbose:
            click.echo(f"Warning: Could not load config: {e}", err=True)
        ctx.obj["config"] = Config()

    # If no command specified, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)


# Register subcommands
main.add_command(init)
main.add_command(run)
main.add_command(status)
main.add_command(agent)
main.add_command(skill)
main.add_command(task)
main.add_command(scheduler)
