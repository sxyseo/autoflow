"""
Autoflow CLI - Skill Commands

Manage skills for specialized AI agent capabilities.

Usage:
    autoflow skill list
    autoflow skill show CONTINUOUS_ITERATOR
"""

from __future__ import annotations

from pathlib import Path

import click

from autoflow.cli.utils import _print_json
from autoflow.core.config import Config


@click.group()
def skill() -> None:
    """Manage skills."""
    pass


@skill.command("list")
@click.option(
    "--skills-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory containing skill definitions.",
)
@click.pass_context
def skill_list(ctx: click.Context, skills_dir: Path | None) -> None:
    """
    List available skills.

    Shows all skills discovered in the skills directory.

    \b
    Examples:
        autoflow skill list
        autoflow skill list --skills-dir /path/to/skills
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    # Determine skills directories
    skill_dirs = []
    if skills_dir:
        skill_dirs.append(skills_dir)
    skill_dirs.extend(Path(d) for d in config.openclaw.extra_dirs)

    skills = []

    for skill_dir in skill_dirs:
        skill_path = Path(skill_dir).expanduser()
        if not skill_path.exists():
            continue

        for skill_folder in skill_path.iterdir():
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if skill_file.exists():
                    skills.append({
                        "name": skill_folder.name,
                        "path": str(skill_file),
                        "directory": str(skill_folder),
                    })

    if ctx.obj.get("output_json"):
        _print_json({"skills": skills, "count": len(skills)})
        return

    click.echo("Available Skills")
    click.echo("=" * 60)

    if not skills:
        click.echo("No skills found.")
        click.echo(f"Searched directories: {', '.join(str(d) for d in skill_dirs)}")
        return

    for skill_info in skills:
        click.echo(f"\n{skill_info['name']}:")
        click.echo(f"  Path: {skill_info['path']}")


@skill.command("show")
@click.argument("name", type=str)
@click.option(
    "--skills-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory containing skill definitions.",
)
@click.pass_context
def skill_show(ctx: click.Context, name: str, skills_dir: Path | None) -> None:
    """
    Show details of a specific skill.

    Displays the full skill definition including workflow and rules.

    \b
    Examples:
        autoflow skill show CONTINUOUS_ITERATOR
        autoflow skill show CODE_REVIEW --skills-dir /path/to/skills
    """
    config: Config | None = ctx.obj.get("config")

    if config is None:
        click.echo("Error: Configuration not loaded.", err=True)
        ctx.exit(1)

    # Determine skills directories
    skill_dirs = []
    if skills_dir:
        skill_dirs.append(skills_dir)
    skill_dirs.extend(Path(d) for d in config.openclaw.extra_dirs)

    for skill_dir in skill_dirs:
        skill_path = Path(skill_dir).expanduser() / name / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text()

            if ctx.obj.get("output_json"):
                _print_json({
                    "name": name,
                    "path": str(skill_path),
                    "content": content,
                })
            else:
                click.echo(f"Skill: {name}")
                click.echo(f"Path: {skill_path}")
                click.echo("=" * 60)
                click.echo(content)
            return

    click.echo(f"Error: Skill '{name}' not found.", err=True)
    ctx.exit(1)
