"""
Autoflow CLI - Review Commands

Run multi-agent code review for quality assurance.

Usage:
    autoflow review run
    autoflow review run --agent claude-code --strategy consensus
    autoflow review run --agent claude-code --agent codex
"""

from __future__ import annotations

import click

from autoflow.cli.utils import _print_json


@click.group()
def review() -> None:
    """Code review commands."""
    pass


@review.command("run")
@click.option(
    "--agent",
    "-a",
    "agents",
    multiple=True,
    type=click.Choice(["claude-code", "codex", "openclaw"]),
    default=["claude-code", "codex"],
    help="Agents to use for review.",
)
@click.option(
    "--strategy",
    "-s",
    type=click.Choice(["consensus", "majority", "single", "weighted"]),
    default="majority",
    help="Review approval strategy.",
)
@click.pass_context
def review_run(
    ctx: click.Context,
    agents: tuple[str, ...],
    strategy: str,
) -> None:
    """
    Run multi-agent code review.

    Uses multiple AI agents to review pending changes.

    \b
    Examples:
        autoflow review run
        autoflow review run --agent claude-code --strategy consensus
        autoflow review run --agent claude-code --agent codex
    """
    if ctx.obj.get("output_json"):
        _print_json(
            {
                "status": "placeholder",
                "agents": list(agents),
                "strategy": strategy,
                "message": "Code review requires async execution. This is a placeholder.",
            }
        )
    else:
        click.echo("Code Review")
        click.echo("=" * 60)
        click.echo(f"Agents: {', '.join(agents)}")
        click.echo(f"Strategy: {strategy}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full code review")
        click.echo("      requires async runtime.")
