"""
Autoflow CLI - Agent Commands

Manage AI agents for task execution.

Usage:
    autoflow agent list
    autoflow agent check claude-code
    autoflow agent check all
"""

from __future__ import annotations

from typing import Optional

import click

from autoflow.core.config import Config
from autoflow.cli.utils import _print_json


@click.group()
def agent() -> None:
    """Manage AI agents."""
    pass


@agent.command("list")
@click.pass_context
def agent_list(ctx: click.Context) -> None:
    """
    List available agents.

    Shows all configured AI agents and their status.
    """
    config: Optional[Config] = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    agents = [
        {
            "name": "claude-code",
            "command": config.agents.claude_code.command,
            "args": config.agents.claude_code.args,
            "resume_mode": config.agents.claude_code.resume_mode,
            "timeout": config.agents.claude_code.timeout_seconds,
        },
        {
            "name": "codex",
            "command": config.agents.codex.command,
            "args": config.agents.codex.args,
            "resume_mode": config.agents.codex.resume_mode,
            "timeout": config.agents.codex.timeout_seconds,
        },
        {
            "name": "openclaw",
            "command": "N/A (uses gateway)",
            "args": [],
            "resume_mode": "native",
            "timeout": 300,
        },
    ]

    if ctx.obj.get("output_json"):
        _print_json({"agents": agents})
        return

    click.echo("Available Agents")
    click.echo("=" * 60)

    for agent_info in agents:
        click.echo(f"\n{agent_info['name']}:")
        click.echo(f"  Command: {agent_info['command']}")
        if agent_info["args"]:
            click.echo(f"  Args: {' '.join(agent_info['args'])}")
        click.echo(f"  Resume Mode: {agent_info['resume_mode']}")
        click.echo(f"  Timeout: {agent_info['timeout']}s")


@agent.command("check")
@click.argument("name", type=click.Choice(["claude-code", "codex", "openclaw", "all"]))
@click.pass_context
def agent_check(ctx: click.Context, name: str) -> None:
    """
    Check if an agent is available.

    Verifies that the agent's CLI is installed and accessible.

    \b
    Examples:
        autoflow agent check claude-code
        autoflow agent check all
    """
    import shutil

    config: Optional[Config] = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    agents_to_check = (
        ["claude-code", "codex", "openclaw"]
        if name == "all"
        else [name]
    )

    results = []

    for agent_name in agents_to_check:
        if agent_name == "claude-code":
            cmd = config.agents.claude_code.command
            available = shutil.which(cmd) is not None
        elif agent_name == "codex":
            cmd = config.agents.codex.command
            available = shutil.which(cmd) is not None
        elif agent_name == "openclaw":
            # OpenClaw uses gateway, check if it's reachable
            available = True  # Placeholder - would need actual health check
            cmd = "gateway"
        else:
            available = False
            cmd = "unknown"

        results.append({
            "name": agent_name,
            "available": available,
            "command": cmd,
        })

    if ctx.obj.get("output_json"):
        _print_json({"agents": results})
        return

    for result in results:
        status = "available" if result["available"] else "not available"
        click.echo(f"{result['name']}: {status} ({result['command']})")
