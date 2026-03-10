"""
Autoflow CLI - Unified Command Line Interface

Provides commands for managing autonomous AI development workflows:
- Initialize and configure Autoflow
- Run tasks with AI agents
- Manage skills and schedulers
- Review code and verify CI gates

Usage:
    autoflow --help
    autoflow init
    autoflow status
    autoflow run "Fix the login bug"
    autoflow agent list
    autoflow skill list
    autoflow scheduler start
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click

from autoflow import __version__
from autoflow.analytics.cli import analytics
from autoflow.core.config import Config, load_config, load_system_config, get_state_dir
from autoflow.core.state import StateManager, TaskStatus, RunStatus
from autoflow.collaboration.team import TeamManager
from autoflow.collaboration.workspace import WorkspaceManager
from autoflow.collaboration.models import RoleType
from autoflow.collaboration.activity import ActivityTracker
from autoflow.collaboration.notifications import NotificationManager


# Click context settings
CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 120,
    "auto_envvar_prefix": "AUTOFLOW",
}


def _get_state_manager(config: Optional[Config] = None) -> StateManager:
    """Get a StateManager instance."""
    state_dir = get_state_dir(config)
    return StateManager(state_dir)


def _get_state_manager_from_ctx(ctx: click.Context) -> StateManager:
    """Get a StateManager instance from click context.

    This function respects the --state-dir CLI option if provided,
    otherwise falls back to the config's state_dir setting.

    Args:
        ctx: Click context object

    Returns:
        StateManager instance with appropriate state directory
    """
    # Check if state_dir was explicitly provided via CLI option
    state_dir_option = ctx.obj.get("state_dir")
    if state_dir_option:
        return StateManager(Path(state_dir_option))

    # Otherwise use config's state_dir
    config: Config = ctx.obj["config"]
    return _get_state_manager(config)


def _print_json(data: Any, indent: int = 2) -> None:
    """Print data as formatted JSON."""
    click.echo(json.dumps(data, indent=indent, default=str))


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # If we're already in an async context, create a new loop
        return asyncio.run(coro)
    else:
        return asyncio.run(coro)


def _format_datetime(dt: Optional[datetime]) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _load_all_tasks_from_specs(config: Optional[Config] = None) -> list[dict[str, Any]]:
    """
    Load all tasks from all spec task files.

    Scans .autoflow/tasks/ directory and loads tasks from each spec's task file.
    Each spec's tasks are stored in .autoflow/tasks/{spec_slug}.json

    Args:
        config: Optional config object

    Returns:
        List of all tasks with added 'spec' field indicating source spec
    """
    state_dir = get_state_dir(config)
    tasks_dir = state_dir / "tasks"

    all_tasks = []

    if not tasks_dir.exists():
        return all_tasks

    for task_file in tasks_dir.glob("*.json"):
        try:
            with open(task_file, encoding="utf-8") as f:
                data = json.load(f)

            # Extract spec slug from filename
            spec_slug = task_file.stem

            # Add tasks with spec information
            for task in data.get("tasks", []):
                task_with_spec = task.copy()
                task_with_spec["spec"] = spec_slug
                all_tasks.append(task_with_spec)

        except (json.JSONDecodeError, IOError):
            # Skip invalid files
            continue

    # Sort by spec and then by task order
    all_tasks.sort(key=lambda t: (t.get("spec", ""), t.get("id", "")))
    return all_tasks


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


# === Init Command ===

@main.command()
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
    state_manager = _get_state_manager_from_ctx(ctx)

    if state_manager.state_dir.exists() and not force:
        if not ctx.obj["output_json"]:
            click.echo(f"State directory already exists: {state_manager.state_dir}")
            click.echo("Use --force to re-initialize.")
        else:
            _print_json({
                "status": "exists",
                "state_dir": str(state_manager.state_dir),
                "message": "State directory already exists. Use --force to re-initialize.",
            })
        ctx.exit(1)

    try:
        state_manager.initialize()

        if not ctx.obj["output_json"]:
            click.echo(f"Initialized Autoflow at: {state_manager.state_dir}")
            click.echo("")
            click.echo("Directory structure:")
            click.echo(f"  {state_manager.state_dir}/")
            click.echo(f"    specs/    - Specification files")
            click.echo(f"    tasks/    - Task definitions")
            click.echo(f"    runs/     - Execution runs")
            click.echo(f"    memory/   - Persistent memory")
            click.echo(f"    backups/  - Backup files")
        else:
            _print_json({
                "status": "initialized",
                "state_dir": str(state_manager.state_dir),
                "directories": [
                    str(state_manager.specs_dir),
                    str(state_manager.tasks_dir),
                    str(state_manager.runs_dir),
                    str(state_manager.memory_dir),
                    str(state_manager.backup_dir),
                ],
            })
    except Exception as e:
        click.echo(f"Error initializing: {e}", err=True)
        ctx.exit(1)


# === Status Command ===

@main.command()
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
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    try:
        status_data = state_manager.get_status()

        if ctx.obj["output_json"]:
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
            click.echo("")
            click.echo("Configuration:")
            click.echo(f"  OpenClaw Gateway: {config.openclaw.gateway_url}")
            click.echo(f"  State Directory: {config.state_dir}")
            click.echo(f"  Scheduler Enabled: {config.scheduler.enabled}")
            click.echo(f"  CI Gates Required: {config.ci.require_all}")

    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)
        ctx.exit(1)


# === Run Command ===

@main.command()
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

    config: Config = ctx.obj["config"]
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

        if ctx.obj["output_json"]:
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


# === Agent Commands ===

@main.group()
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
    config: Config = ctx.obj["config"]

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

    if ctx.obj["output_json"]:
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
    """
    import shutil

    config: Config = ctx.obj["config"]

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

    if ctx.obj["output_json"]:
        _print_json({"agents": results})
        return

    for result in results:
        status = "available" if result["available"] else "not available"
        click.echo(f"{result['name']}: {status} ({result['command']})")


# === Skill Commands ===

@main.group()
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
def skill_list(ctx: click.Context, skills_dir: Optional[Path]) -> None:
    """
    List available skills.

    Shows all skills discovered in the skills directory.
    """
    config: Config = ctx.obj["config"]

    # Determine skills directories
    skill_dirs = []
    if skills_dir:
        skill_dirs.append(skills_dir)
    skill_dirs.extend(config.openclaw.extra_dirs)

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

    if ctx.obj["output_json"]:
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
def skill_show(ctx: click.Context, name: str, skills_dir: Optional[Path]) -> None:
    """
    Show details of a specific skill.

    Displays the full skill definition including workflow and rules.
    """
    config: Config = ctx.obj["config"]

    # Determine skills directories
    skill_dirs = []
    if skills_dir:
        skill_dirs.append(skills_dir)
    skill_dirs.extend(config.openclaw.extra_dirs)

    for skill_dir in skill_dirs:
        skill_path = Path(skill_dir).expanduser() / name / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text()

            if ctx.obj["output_json"]:
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


# === Task Commands ===

@main.group()
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
    status_filter: Optional[str],
    agent: Optional[str],
    limit: int,
) -> None:
    """
    List tasks.

    Shows tasks filtered by status and/or agent.
    """
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    status_enum = TaskStatus(status_filter) if status_filter else None

    tasks = state_manager.list_tasks(status=status_enum, agent=agent)[:limit]

    if ctx.obj["output_json"]:
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
    """
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    task_data = state_manager.load_task(task_id)

    if not task_data:
        click.echo(f"Error: Task '{task_id}' not found.", err=True)
        ctx.exit(1)

    if ctx.obj["output_json"]:
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


# === Scheduler Commands ===

@main.group()
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
    """
    config: Config = ctx.obj["config"]

    if not config.scheduler.enabled:
        click.echo("Scheduler is disabled in configuration.", err=True)
        ctx.exit(1)

    if ctx.obj["output_json"]:
        _print_json({
            "status": "starting",
            "daemon": daemon,
            "port": port,
            "jobs_count": len(config.scheduler.jobs),
        })
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
    """Stop the scheduler daemon."""
    if ctx.obj["output_json"]:
        _print_json({"status": "stopped"})
    else:
        click.echo("Scheduler daemon stopped.")


@scheduler.command("status")
@click.pass_context
def scheduler_status(ctx: click.Context) -> None:
    """Show scheduler daemon status."""
    config: Config = ctx.obj["config"]

    status_data = {
        "enabled": config.scheduler.enabled,
        "jobs": [
            {"id": job.id, "cron": job.cron, "handler": job.handler, "enabled": job.enabled}
            for job in config.scheduler.jobs
        ],
    }

    if ctx.obj["output_json"]:
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


# === CI Commands ===

@main.group()
def ci() -> None:
    """Run CI verification gates."""
    pass


@ci.command("verify")
@click.option(
    "--all",
    "-a",
    "run_all",
    is_flag=True,
    help="Run all verification gates.",
)
@click.option(
    "--test",
    is_flag=True,
    help="Run test gate.",
)
@click.option(
    "--lint",
    is_flag=True,
    help="Run lint gate.",
)
@click.option(
    "--security",
    is_flag=True,
    help="Run security gate.",
)
@click.option(
    "--typecheck",
    is_flag=True,
    help="Run type check gate.",
)
@click.pass_context
def ci_verify(
    ctx: click.Context,
    run_all: bool,
    test: bool,
    lint: bool,
    security: bool,
    typecheck: bool,
) -> None:
    """
    Run CI verification gates.

    Executes specified verification gates and reports results.
    """
    gates_to_run = []

    if run_all or (not test and not lint and not security and not typecheck):
        gates_to_run = ["test", "lint", "security", "typecheck"]
    else:
        if test:
            gates_to_run.append("test")
        if lint:
            gates_to_run.append("lint")
        if security:
            gates_to_run.append("security")
        if typecheck:
            gates_to_run.append("typecheck")

    if ctx.obj["output_json"]:
        _print_json({
            "status": "placeholder",
            "gates": gates_to_run,
            "message": "CI verification requires async execution. This is a placeholder.",
        })
    else:
        click.echo("CI Verification")
        click.echo("=" * 60)
        click.echo(f"Gates to run: {', '.join(gates_to_run)}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full CI verification")
        click.echo("      requires async runtime.")


# === Review Commands ===

@main.group()
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
    """
    if ctx.obj["output_json"]:
        _print_json({
            "status": "placeholder",
            "agents": list(agents),
            "strategy": strategy,
            "message": "Code review requires async execution. This is a placeholder.",
        })
    else:
        click.echo("Code Review")
        click.echo("=" * 60)
        click.echo(f"Agents: {', '.join(agents)}")
        click.echo(f"Strategy: {strategy}")
        click.echo("")
        click.echo("Note: This is a CLI placeholder. Full code review")
        click.echo("      requires async runtime.")


# === Config Commands ===

@main.group()
def config_cmd() -> None:
    """Configuration commands."""
    pass


@config_cmd.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration."""
    config: Config = ctx.obj["config"]

    if ctx.obj["output_json"]:
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


# === Dashboard Command ===

@main.command()
@click.option(
    "--host",
    "-H",
    type=str,
    default="127.0.0.1",
    help="Host to bind the dashboard server to.",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Port to run the dashboard server on.",
)
@click.option(
    "--reload",
    "-r",
    is_flag=True,
    help="Enable auto-reload for development.",
)
@click.option(
    "--workers",
    "-w",
    type=int,
    default=1,
    help="Number of worker processes.",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["critical", "error", "warning", "info", "debug"]),
    default="info",
    help="Log level for the server.",
)
@click.pass_context
def dashboard(
    ctx: click.Context,
    host: str,
    port: int,
    reload: bool,
    workers: int,
    log_level: str,
) -> None:
    """
    Start the web dashboard server.

    Launches the FastAPI web dashboard for monitoring Autoflow tasks,
    runs, and system status in real-time through a web interface.

    \b
    Features:
        - Real-time task and run monitoring
        - System status and statistics
        - WebSocket support for live updates
        - Interactive API documentation at /docs

    \b
    Examples:
        autoflow dashboard
        autoflow dashboard --host 0.0.0.0 --port 8080
        autoflow dashboard --reload
        autoflow dashboard --workers 4

    \b
    Access the dashboard at:
        http://localhost:8000
        http://localhost:8000/docs (API documentation)
    """
    config: Config = ctx.obj["config"]
    verbose = ctx.obj.get("verbose", 0)

    try:
        import uvicorn

        if ctx.obj["output_json"]:
            _print_json({
                "status": "starting",
                "host": host,
                "port": port,
                "reload": reload,
                "workers": workers,
                "log_level": log_level,
                "dashboard_url": f"http://{host}:{port}",
                "docs_url": f"http://{host}:{port}/docs",
            })
            return

        # Human-readable output
        click.echo("Starting Autoflow Dashboard...")
        click.echo("")
        click.echo(f"  Host: {host}")
        click.echo(f"  Port: {port}")
        click.echo(f"  Workers: {workers}")
        click.echo(f"  Log Level: {log_level}")
        if reload:
            click.echo(f"  Auto-reload: enabled")
        click.echo("")
        click.echo(f"  Dashboard: http://{host}:{port}")
        click.echo(f"  API Docs:  http://{host}:{port}/docs")
        click.echo("")
        click.echo("Press Ctrl+C to stop the server")
        click.echo("")

        # Import the FastAPI app
        from autoflow.web.app import app

        # Run uvicorn
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=reload,
            workers=workers if not reload else 1,  # Reload only works with single worker
            log_level=log_level,
        )

    except ImportError as e:
        click.echo(
            f"Error: uvicorn is not installed. "
            f"Install it with: pip install uvicorn[standard]",
            err=True
        )
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error starting dashboard: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        ctx.exit(1)

# === Search Tasks Command ===

@main.command("search-tasks")
@click.option(
    "--status",
    "-s",
    "status_filter",
    type=str,
    default=None,
    help="Filter by task status (e.g., todo, in_progress, done, blocked).",
)
@click.option(
    "--owner-role",
    "-o",
    type=str,
    default=None,
    help="Filter by owner role (e.g., implementation-runner, reviewer).",
)
@click.option(
    "--text",
    "-t",
    type=str,
    default=None,
    help="Text search in title and notes (case-insensitive substring).",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of tasks to show.",
)
@click.pass_context
def search_tasks_cmd(
    ctx: click.Context,
    status_filter: Optional[str],
    owner_role: Optional[str],
    text: Optional[str],
    limit: int,
) -> None:
    """
    Search and filter tasks across all specs.

    This command searches through all spec task files in .autoflow/tasks/ and
    returns matching tasks. Tasks can be filtered by status, owner role, and
    text content. Results are displayed in a human-readable format by default,
    or JSON format with --json.

    \b
    Common Use Cases:
        # Find all todo tasks
        autoflow search-tasks --status todo

        # Find tasks for a specific role
        autoflow search-tasks --owner-role implementation-runner

        # Search for tasks containing specific text
        autoflow search-tasks --text "database"

        # Combine multiple filters
        autoflow search-tasks --status todo --owner-role frontend-dev

    \b
    Examples:
        # Show first 5 todo tasks
        autoflow search-tasks --status todo --limit 5

        # Find in-progress tasks for reviewer
        autoflow search-tasks --status in_progress --owner-role reviewer

        # Search for API-related tasks
        autoflow search-tasks --text "api" --limit 10

        # Get JSON output for scripting
        autoflow search-tasks --status done --json

        # Complex search with multiple filters
        autoflow search-tasks --status todo --text "auth" --owner-role backend-dev --limit 20

    \b
    Filter Behavior:
        --status      Exact match on task status field
                      Common values: todo, in_progress, done, blocked

        --owner-role  Exact match on owner_role field
                      Examples: implementation-runner, reviewer, frontend-dev, backend-dev

        --text        Case-insensitive substring search
                      Searches in: title, notes (both strings and dict values)

        --limit       Maximum number of results to display
                      Default: 20, Use 0 for unlimited

        Multiple filters are combined with AND logic (all must match).
        Results are sorted by spec name and task ID.

    \b
    Output Format (default):
        [task-id] Task Title
          Spec: spec-name
          Status: status
          Owner: owner-role

    \b
    Output Format (--json):
        {
          "tasks": [...],
          "count": 10,
          "total_matching": 42,
          "filters": {...}
        }
    """
    config: Config = ctx.obj["config"]

    # Load all tasks from all specs
    all_tasks = _load_all_tasks_from_specs(config)

    # Apply filters
    filtered_tasks = []
    for task in all_tasks:
        # Status filter (exact match)
        if status_filter and task.get("status") != status_filter:
            continue

        # Owner role filter (exact match)
        if owner_role and task.get("owner_role") != owner_role:
            continue

        # Text filter (case-insensitive substring in title and notes)
        if text:
            text_lower = text.lower()
            title_match = text_lower in task.get("title", "").lower()

            # Check in notes (if present)
            notes_match = False
            notes = task.get("notes", [])
            if notes:
                # Notes can be a list of strings or dict objects
                for note in notes:
                    if isinstance(note, str):
                        if text_lower in note.lower():
                            notes_match = True
                            break
                    elif isinstance(note, dict):
                        # Check string values in note dict
                        note_text = " ".join(str(v) for v in note.values())
                        if text_lower in note_text.lower():
                            notes_match = True
                            break

            if not title_match and not notes_match:
                continue

        filtered_tasks.append(task)

    # Apply limit
    limited_tasks = filtered_tasks[:limit]

    if ctx.obj["output_json"]:
        _print_json({
            "tasks": limited_tasks,
            "count": len(limited_tasks),
            "total_matching": len(filtered_tasks),
            "filters": {
                "status": status_filter,
                "owner_role": owner_role,
                "text": text,
            },
        })
        return

    # Human-readable output
    click.echo("Search Results")
    click.echo("=" * 60)
    click.echo(f"Found {len(filtered_tasks)} matching task(s)")
    if len(filtered_tasks) > limit:
        click.echo(f"Showing {len(limited_tasks)} (use --limit to see more)")
    click.echo("")

    if not limited_tasks:
        click.echo("No tasks found matching the criteria.")
        return

    for task in limited_tasks:
        task_id = task.get("id", "unknown")
        title = task.get("title", "N/A")
        status = task.get("status", "unknown")
        owner = task.get("owner_role", "N/A")
        spec = task.get("spec", "N/A")

        click.echo(f"\n[{task_id}] {title}")
        click.echo(f"  Spec: {spec}")
        click.echo(f"  Status: {status}")
        if owner != "N/A":
            click.echo(f"  Owner: {owner}")


# === Memory Commands ===

@main.group()
def memory() -> None:
    """Manage persistent memory."""
    pass


@memory.command("list")
@click.option(
    "--category",
    "-c",
    type=str,
    default=None,
    help="Filter by category.",
)
@click.pass_context
def memory_list(ctx: click.Context, category: Optional[str]) -> None:
    """List memory entries."""
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    memories = state_manager.list_memory(category=category)

    if ctx.obj["output_json"]:
        _print_json({"memories": memories, "count": len(memories)})
        return

    click.echo("Memory Entries")
    click.echo("=" * 60)

    if not memories:
        click.echo("No memory entries found.")
        return

    for mem in memories:
        click.echo(f"\n[{mem.get('key', 'unknown')}]")
        click.echo(f"  Category: {mem.get('category', 'N/A')}")
        click.echo(f"  Created: {mem.get('created_at', 'N/A')}")


@memory.command("get")
@click.argument("key", type=str)
@click.pass_context
def memory_get(ctx: click.Context, key: str) -> None:
    """Get a memory entry by key."""
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    value = state_manager.load_memory(key)

    if value is None:
        click.echo(f"Error: Memory '{key}' not found.", err=True)
        ctx.exit(1)

    if ctx.obj["output_json"]:
        _print_json({"key": key, "value": value})
    else:
        click.echo(f"{key}: {value}")


@memory.command("set")
@click.argument("key", type=str)
@click.argument("value", type=str)
@click.option(
    "--category",
    "-c",
    type=str,
    default="general",
    help="Category for the memory.",
)
@click.pass_context
def memory_set(ctx: click.Context, key: str, value: str, category: str) -> None:
    """Set a memory entry."""
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    state_manager.initialize()
    state_manager.save_memory(key, value, category=category)

    if ctx.obj["output_json"]:
        _print_json({"key": key, "value": value, "category": category, "status": "saved"})
    else:
        click.echo(f"Saved: {key} = {value}")


@memory.command("delete")
@click.argument("key", type=str)
@click.pass_context
def memory_delete(ctx: click.Context, key: str) -> None:
    """Delete a memory entry."""
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    if state_manager.delete_memory(key):
        if ctx.obj["output_json"]:
            _print_json({"key": key, "status": "deleted"})
        else:
            click.echo(f"Deleted: {key}")
    else:
        click.echo(f"Error: Memory '{key}' not found.", err=True)
        ctx.exit(1)


# === Workspace Commands ===

@main.group()
def workspace() -> None:
    """Manage workspaces for team collaboration."""
    pass


@workspace.command("create")
@click.argument("workspace_id", type=str)
@click.argument("name", type=str)
@click.argument("team_id", type=str)
@click.option(
    "--description",
    "-d",
    type=str,
    default="",
    help="Workspace description.",
)
@click.option(
    "--settings",
    "-s",
    type=str,
    default=None,
    help="Workspace settings as JSON string.",
)
@click.pass_context
def workspace_create(
    ctx: click.Context,
    workspace_id: str,
    name: str,
    team_id: str,
    description: str,
    settings: Optional[str],
) -> None:
    """
    Create a new workspace.

    Creates a shared workspace for team collaboration with role-based access control.

    \b
    Examples:
        autoflow workspace create workspace-001 "Project X" team-001
        autoflow workspace create workspace-002 "Main Project" team-001 --description "Primary workspace"
        autoflow workspace create workspace-003 "Dev Team" team-002 --settings '{"private": true}'
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Parse settings if provided
        settings_dict = {}
        if settings:
            try:
                settings_dict = json.loads(settings)
            except json.JSONDecodeError as e:
                click.echo(f"Error: Invalid JSON in settings: {e}", err=True)
                ctx.exit(1)

        # Create workspace
        workspace = manager.create_workspace(
            workspace_id=workspace_id,
            name=name,
            team_id=team_id,
            description=description,
            settings=settings_dict if settings_dict else None,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "status": "created",
                "workspace": workspace.model_dump(mode="json"),
            })
        else:
            click.echo(f"Created workspace: {workspace.id}")
            click.echo(f"  Name: {workspace.name}")
            click.echo(f"  Team: {workspace.team_id}")
            if description:
                click.echo(f"  Description: {description}")
            click.echo(f"  Created: {_format_datetime(workspace.created_at)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error creating workspace: {e}", err=True)
        ctx.exit(1)


@workspace.command("list")
@click.option(
    "--team",
    "-t",
    "team_id",
    type=str,
    default=None,
    help="Filter by team ID.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of workspaces to show.",
)
@click.pass_context
def workspace_list(
    ctx: click.Context,
    team_id: Optional[str],
    limit: int,
) -> None:
    """
    List workspaces.

    Shows all workspaces, optionally filtered by team.

    \b
    Examples:
        autoflow workspace list
        autoflow workspace list --team team-001
        autoflow workspace list --limit 50
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        workspaces = manager.list_workspaces(team_id=team_id, limit=limit)

        if ctx.obj["output_json"]:
            _print_json({
                "workspaces": [ws.model_dump(mode="json") for ws in workspaces],
                "count": len(workspaces),
            })
            return

        click.echo("Workspaces")
        click.echo("=" * 60)

        if not workspaces:
            click.echo("No workspaces found.")
            return

        for workspace in workspaces:
            click.echo(f"\n[{workspace.id}] {workspace.name}")
            click.echo(f"  Team: {workspace.team_id}")
            if workspace.description:
                click.echo(f"  Description: {workspace.description}")
            click.echo(f"  Created: {_format_datetime(workspace.created_at)}")

    except Exception as e:
        click.echo(f"Error listing workspaces: {e}", err=True)
        ctx.exit(1)


@workspace.command("show")
@click.argument("workspace_id", type=str)
@click.pass_context
def workspace_show(ctx: click.Context, workspace_id: str) -> None:
    """
    Show details of a specific workspace.

    Displays detailed information about a workspace including settings and metadata.

    \b
    Examples:
        autoflow workspace show workspace-001
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        workspace = manager.get_workspace(workspace_id)

        if not workspace:
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        if ctx.obj["output_json"]:
            _print_json(workspace.model_dump(mode="json"))
            return

        click.echo(f"Workspace: {workspace.id}")
        click.echo("=" * 60)
        click.echo(f"Name: {workspace.name}")
        click.echo(f"Team: {workspace.team_id}")
        click.echo(f"Description: {workspace.description or 'N/A'}")
        click.echo(f"Created: {_format_datetime(workspace.created_at)}")
        click.echo(f"Updated: {_format_datetime(workspace.updated_at)}")

        if workspace.settings:
            click.echo("\nSettings:")
            for key, value in workspace.settings.items():
                click.echo(f"  {key}: {value}")

        if workspace.metadata:
            click.echo("\nMetadata:")
            for key, value in workspace.metadata.items():
                click.echo(f"  {key}: {value}")

    except Exception as e:
        click.echo(f"Error showing workspace: {e}", err=True)
        ctx.exit(1)


@workspace.command("delete")
@click.argument("workspace_id", type=str)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force deletion without confirmation.",
)
@click.pass_context
def workspace_delete(ctx: click.Context, workspace_id: str, force: bool) -> None:
    """
    Delete a workspace.

    Permanently deletes a workspace and all its associated data.

    \b
    Examples:
        autoflow workspace delete workspace-001
        autoflow workspace delete workspace-001 --force
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Check if workspace exists
        if not manager.workspace_exists(workspace_id):
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        # Confirm deletion
        if not force:
            click.echo(f"This will delete workspace: {workspace_id}")
            if not click.confirm("Are you sure?"):
                click.echo("Deletion cancelled.")
                ctx.exit(0)

        # Delete workspace
        deleted = manager.delete_workspace(workspace_id)

        if deleted:
            if ctx.obj["output_json"]:
                _print_json({
                    "status": "deleted",
                    "workspace_id": workspace_id,
                })
            else:
                click.echo(f"Deleted workspace: {workspace_id}")
        else:
            click.echo(f"Error: Failed to delete workspace '{workspace_id}'.", err=True)
            ctx.exit(1)

    except Exception as e:
        click.echo(f"Error deleting workspace: {e}", err=True)
        ctx.exit(1)


@workspace.command("members")
@click.argument("workspace_id", type=str)
@click.option(
    "--role",
    "-r",
    "role_filter",
    type=click.Choice([r.value for r in RoleType]),
    default=None,
    help="Filter by role type.",
)
@click.pass_context
def workspace_members(
    ctx: click.Context,
    workspace_id: str,
    role_filter: Optional[str],
) -> None:
    """
    List members of a workspace.

    Shows all members with their roles, optionally filtered by role type.

    \b
    Examples:
        autoflow workspace members workspace-001
        autoflow workspace members workspace-001 --role admin
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Check if workspace exists
        if not manager.workspace_exists(workspace_id):
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        # Parse role filter
        role_enum = RoleType(role_filter) if role_filter else None

        # Get members
        members = manager.list_members(workspace_id, role_type=role_enum)

        if ctx.obj["output_json"]:
            _print_json({
                "workspace_id": workspace_id,
                "members": [m.model_dump(mode="json") for m in members],
                "count": len(members),
            })
            return

        click.echo(f"Members of {workspace_id}")
        click.echo("=" * 60)

        if not members:
            click.echo("No members found.")
            return

        for member in members:
            click.echo(f"\n{member.user_id}")
            click.echo(f"  Role: {member.role_type.value}")
            if member.granted_by:
                click.echo(f"  Granted by: {member.granted_by}")
            click.echo(f"  Granted: {_format_datetime(member.granted_at)}")
            if member.expires_at:
                click.echo(f"  Expires: {_format_datetime(member.expires_at)}")

    except Exception as e:
        click.echo(f"Error listing members: {e}", err=True)
        ctx.exit(1)


@workspace.command("add-member")
@click.argument("workspace_id", type=str)
@click.argument("user_id", type=str)
@click.option(
    "--role",
    "-r",
    "role_type",
    type=click.Choice([r.value for r in RoleType]),
    default=RoleType.MEMBER.value,
    help="Role to assign (default: member).",
)
@click.option(
    "--granted-by",
    "-g",
    type=str,
    default=None,
    help="User ID who is granting this role.",
)
@click.pass_context
def workspace_add_member(
    ctx: click.Context,
    workspace_id: str,
    user_id: str,
    role_type: str,
    granted_by: Optional[str],
) -> None:
    """
    Add a member to a workspace.

    Adds a user to a workspace with the specified role.

    \b
    Examples:
        autoflow workspace add-member workspace-001 user-001
        autoflow workspace add-member workspace-001 user-002 --role admin
        autoflow workspace add-member workspace-001 user-003 --role reviewer --granted-by user-001
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Check if workspace exists
        if not manager.workspace_exists(workspace_id):
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        # Add member
        role = manager.add_member(
            workspace_id=workspace_id,
            user_id=user_id,
            role_type=RoleType(role_type),
            granted_by=granted_by,
        )

        if ctx.obj["output_json"]:
            _print_json({
                "status": "added",
                "workspace_id": workspace_id,
                "user_id": user_id,
                "role": role.model_dump(mode="json"),
            })
        else:
            click.echo(f"Added member to workspace: {workspace_id}")
            click.echo(f"  User: {user_id}")
            click.echo(f"  Role: {role.role_type.value}")
            click.echo(f"  Granted: {_format_datetime(role.granted_at)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error adding member: {e}", err=True)
        ctx.exit(1)


@workspace.command("remove-member")
@click.argument("workspace_id", type=str)
@click.argument("user_id", type=str)
@click.pass_context
def workspace_remove_member(
    ctx: click.Context,
    workspace_id: str,
    user_id: str,
) -> None:
    """
    Remove a member from a workspace.

    Removes a user's membership and all associated permissions from a workspace.

    \b
    Examples:
        autoflow workspace remove-member workspace-001 user-001
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Check if workspace exists
        if not manager.workspace_exists(workspace_id):
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        # Remove member
        removed = manager.remove_member(workspace_id, user_id)

        if removed:
            if ctx.obj["output_json"]:
                _print_json({
                    "status": "removed",
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                })
            else:
                click.echo(f"Removed member from workspace: {workspace_id}")
                click.echo(f"  User: {user_id}")
        else:
            click.echo(f"Error: User '{user_id}' is not a member of workspace '{workspace_id}'.", err=True)
            ctx.exit(1)

    except Exception as e:
        click.echo(f"Error removing member: {e}", err=True)
        ctx.exit(1)


@workspace.command("update-member")
@click.argument("workspace_id", type=str)
@click.argument("user_id", type=str)
@click.option(
    "--role",
    "-r",
    "role_type",
    type=click.Choice([r.value for r in RoleType]),
    required=True,
    help="New role type.",
)
@click.option(
    "--granted-by",
    "-g",
    type=str,
    default=None,
    help="User ID who is granting this role.",
)
@click.pass_context
def workspace_update_member(
    ctx: click.Context,
    workspace_id: str,
    user_id: str,
    role_type: str,
    granted_by: Optional[str],
) -> None:
    """
    Update a member's role in a workspace.

    Changes the role of an existing workspace member.

    \b
    Examples:
        autoflow workspace update-member workspace-001 user-001 --role admin
        autoflow workspace update-member workspace-001 user-002 --role reviewer --granted-by user-001
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = WorkspaceManager(state_manager.state_dir)
        manager.initialize()

        # Check if workspace exists
        if not manager.workspace_exists(workspace_id):
            click.echo(f"Error: Workspace '{workspace_id}' not found.", err=True)
            ctx.exit(1)

        # Update member role
        role = manager.update_member_role(
            workspace_id=workspace_id,
            user_id=user_id,
            role_type=RoleType(role_type),
            granted_by=granted_by,
        )

        if role:
            if ctx.obj["output_json"]:
                _print_json({
                    "status": "updated",
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "role": role.model_dump(mode="json"),
                })
            else:
                click.echo(f"Updated member role in workspace: {workspace_id}")
                click.echo(f"  User: {user_id}")
                click.echo(f"  New role: {role.role_type.value}")
        else:
            click.echo(f"Error: User '{user_id}' is not a member of workspace '{workspace_id}'.", err=True)
            ctx.exit(1)

    except Exception as e:
        click.echo(f"Error updating member: {e}", err=True)
        ctx.exit(1)


# === Team Commands ===

@main.group()
def team() -> None:
    """Manage teams for collaboration."""
    pass


@team.command("create")
@click.argument("team_id", type=str)
@click.argument("name", type=str)
@click.option(
    "--description",
    "-d",
    type=str,
    default="",
    help="Team description.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_create(
    ctx: click.Context,
    team_id: str,
    name: str,
    description: str,
    output_json: bool,
) -> None:
    """
    Create a new team.

    Creates a team for organizing users and shared workspaces.

    \b
    Examples:
        autoflow team create team-001 "Engineering"
        autoflow team create team-002 "DevOps" --description "Operations team"
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        # Create team
        team = manager.create_team(
            team_id=team_id,
            name=name,
            description=description,
        )

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "status": "created",
                "team": team.model_dump(mode="json"),
            })
        else:
            click.echo(f"Created team: {team.id}")
            click.echo(f"  Name: {team.name}")
            if description:
                click.echo(f"  Description: {description}")
            click.echo(f"  Created: {_format_datetime(team.created_at)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error creating team: {e}", err=True)
        ctx.exit(1)


@team.command("list")
@click.option(
    "--limit",
    "-l",
    type=int,
    default=20,
    help="Maximum number of teams to show.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_list(
    ctx: click.Context,
    limit: int,
    output_json: bool,
) -> None:
    """
    List teams.

    Shows all teams in the system.

    \b
    Examples:
        autoflow team list
        autoflow team list --limit 50
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        teams = manager.list_teams(limit=limit)

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "teams": [t.model_dump(mode="json") for t in teams],
                "count": len(teams),
            })
            return

        if not teams:
            click.echo("No teams found.")
            return

        click.echo(f"Teams ({len(teams)}):")
        for team in teams:
            click.echo(f"\n  [{team.id}]")
            click.echo(f"  Name: {team.name}")
            if team.description:
                click.echo(f"  Description: {team.description}")
            click.echo(f"  Members: {len(team.member_ids)}")
            click.echo(f"  Created: {_format_datetime(team.created_at)}")

    except Exception as e:
        click.echo(f"Error listing teams: {e}", err=True)
        ctx.exit(1)


@team.command("add-member")
@click.argument("team_id", type=str)
@click.argument("user_id", type=str)
@click.option(
    "--role",
    "-r",
    "role_type",
    type=click.Choice(["owner", "admin", "member", "reviewer", "viewer"], case_sensitive=False),
    default="member",
    help="Role to assign to the user.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_add_member(
    ctx: click.Context,
    team_id: str,
    user_id: str,
    role_type: str,
    output_json: bool,
) -> None:
    """
    Add a member to a team.

    Adds a user to a team with the specified role.

    \b
    Examples:
        autoflow team add-member team-001 user-001
        autoflow team add-member team-001 user-002 --role admin
        autoflow team add-member team-001 user-003 --role reviewer
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        # Convert role string to RoleType enum
        role_enum = RoleType[role_type.upper()]

        # Add member
        role = manager.add_member(
            team_id=team_id,
            user_id=user_id,
            role_type=role_enum,
        )

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "status": "added",
                "team_id": team_id,
                "user_id": user_id,
                "role": role.model_dump(mode="json"),
            })
        else:
            click.echo(f"Added member to team: {team_id}")
            click.echo(f"  User: {user_id}")
            click.echo(f"  Role: {role.role_type.value}")
            click.echo(f"  Granted: {_format_datetime(role.granted_at)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error adding member: {e}", err=True)
        ctx.exit(1)


@team.command("set-role")
@click.argument("team_id", type=str)
@click.argument("user_id", type=str)
@click.argument("role", type=str)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_set_role(
    ctx: click.Context,
    team_id: str,
    user_id: str,
    role: str,
    output_json: bool,
) -> None:
    """
    Set a member's role in a team.

    Changes the role of an existing team member, or adds them if they're not already a member.

    \b
    Examples:
        autoflow team set-role team-001 user-001 admin
        autoflow team set-role team-001 user-002 member
        autoflow team set-role team-001 user-003 reviewer
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        # Convert role string to RoleType enum
        role_enum = RoleType[role.upper()]

        # Set member role
        updated_role = manager.set_member_role(
            team_id=team_id,
            user_id=user_id,
            role_type=role_enum,
        )

        if updated_role is None:
            click.echo(f"Error: Team '{team_id}' not found.", err=True)
            ctx.exit(1)

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "status": "updated",
                "team_id": team_id,
                "user_id": user_id,
                "role": updated_role.model_dump(mode="json"),
            })
        else:
            click.echo(f"Updated role in team: {team_id}")
            click.echo(f"  User: {user_id}")
            click.echo(f"  New role: {updated_role.role_type.value}")
            click.echo(f"  Updated: {_format_datetime(updated_role.granted_at)}")

    except KeyError:
        click.echo(f"Error: Invalid role '{role}'. Valid roles: owner, admin, member, reviewer, viewer", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error setting role: {e}", err=True)
        ctx.exit(1)


@team.command("members")
@click.argument("team_id", type=str)
@click.option(
    "--role",
    "-r",
    "role_type",
    type=click.Choice(["owner", "admin", "member", "reviewer", "viewer"], case_sensitive=False),
    default=None,
    help="Filter by role type.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_members(
    ctx: click.Context,
    team_id: str,
    role_type: Optional[str],
    output_json: bool,
) -> None:
    """
    List members of a team.

    Shows all members of a team, optionally filtered by role.

    \b
    Examples:
        autoflow team members team-001
        autoflow team members team-001 --role admin
        autoflow team members team-001 --role reviewer
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        # Convert role string to RoleType enum if provided
        role_enum = RoleType[role_type.upper()] if role_type else None

        # Get team
        team = manager.get_team(team_id)
        if team is None:
            click.echo(f"Error: Team '{team_id}' not found.", err=True)
            ctx.exit(1)

        # List members
        members = manager.list_members(team_id=team_id, role_type=role_enum)

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "team_id": team_id,
                "team_name": team.name,
                "members": [m.model_dump(mode="json") for m in members],
                "count": len(members),
            })
            return

        if not members:
            if role_type:
                click.echo(f"No members with role '{role_type}' in team: {team_id}")
            else:
                click.echo(f"No members in team: {team_id}")
            return

        click.echo(f"Members of {team.name} ({team_id}):")
        for member in members:
            click.echo(f"\n  [{member.user_id}]")
            click.echo(f"  Role: {member.role_type.value}")
            click.echo(f"  Granted: {_format_datetime(member.granted_at)}")
            if member.granted_by:
                click.echo(f"  Granted by: {member.granted_by}")
            if member.expires_at:
                click.echo(f"  Expires: {_format_datetime(member.expires_at)}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
    except Exception as e:
        click.echo(f"Error listing members: {e}", err=True)
        ctx.exit(1)


@team.command("remove-member")
@click.argument("team_id", type=str)
@click.argument("user_id", type=str)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def team_remove_member(
    ctx: click.Context,
    team_id: str,
    user_id: str,
    output_json: bool,
) -> None:
    """
    Remove a member from a team.

    Removes a user from a team.

    \b
    Examples:
        autoflow team remove-member team-001 user-001
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = TeamManager(state_manager.state_dir)
        manager.initialize()

        # Remove member
        removed = manager.remove_member(
            team_id=team_id,
            user_id=user_id,
        )

        if not removed:
            click.echo(f"Error: User '{user_id}' is not a member of team '{team_id}'.", err=True)
            ctx.exit(1)

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "status": "removed",
                "team_id": team_id,
                "user_id": user_id,
            })
        else:
            click.echo(f"Removed member from team: {team_id}")
            click.echo(f"  User: {user_id}")

    except Exception as e:
        click.echo(f"Error removing member: {e}", err=True)
        ctx.exit(1)


# === Activity Commands ===

@main.group()
def activity() -> None:
    """Manage activity feed and track events."""
    pass


@activity.command("list")
@click.option(
    "--limit",
    "-l",
    type=int,
    default=50,
    help="Maximum number of activities to return.",
)
@click.option(
    "--user",
    "-u",
    "user_id",
    type=str,
    default=None,
    help="Filter by user ID.",
)
@click.option(
    "--workspace",
    "-w",
    "workspace_id",
    type=str,
    default=None,
    help="Filter by workspace ID.",
)
@click.option(
    "--type",
    "-t",
    "activity_type",
    type=str,
    default=None,
    help="Filter by activity type.",
)
@click.option(
    "--entity",
    "-e",
    "entity_id",
    type=str,
    default=None,
    help="Filter by entity ID.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def activity_list(
    ctx: click.Context,
    limit: int,
    user_id: Optional[str],
    workspace_id: Optional[str],
    activity_type: Optional[str],
    entity_id: Optional[str],
    output_json: bool,
) -> None:
    """
    List recent activities.

    Shows a feed of recent activities with optional filtering by user, workspace, type, or entity.

    \b
    Examples:
        autoflow activity list
        autoflow activity list --limit 20
        autoflow activity list --user user-001
        autoflow activity list --workspace workspace-001 --type task_created
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        tracker = ActivityTracker(state_manager.state_dir)
        tracker.initialize()

        # Query activities based on filters
        if user_id:
            activities = tracker.get_activities_by_user(
                user_id=user_id,
                limit=limit,
            )
        elif workspace_id:
            activities = tracker.get_activities_by_workspace(
                workspace_id=workspace_id,
                limit=limit,
            )
        elif activity_type:
            activities = tracker.get_activities_by_type(
                activity_type=activity_type,
                limit=limit,
            )
        elif entity_id:
            activities = tracker.get_activities_for_entity(
                entity_id=entity_id,
                limit=limit,
            )
        else:
            activities = tracker.get_recent_activities(
                limit=limit,
            )

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "activities": [a.model_dump(mode="json") for a in activities],
                "count": len(activities),
            })
        else:
            if not activities:
                click.echo("No activities found.")
                return

            click.echo(f"Recent activities ({len(activities)}):")
            for activity in activities:
                click.echo(f"\n  [{activity.id}]")
                click.echo(f"  Type: {activity.activity_type}")
                click.echo(f"  Actor: {activity.actor_id}")
                if activity.workspace_id:
                    click.echo(f"  Workspace: {activity.workspace_id}")
                if activity.entity_id:
                    click.echo(f"  Entity: {activity.entity_id}")
                click.echo(f"  Timestamp: {_format_datetime(activity.timestamp)}")
                if activity.description:
                    click.echo(f"  Description: {activity.description}")

    except Exception as e:
        click.echo(f"Error listing activities: {e}", err=True)
        ctx.exit(1)


@activity.group()
def notifications() -> None:
    """Manage notifications."""
    pass


@notifications.command("list")
@click.argument("user_id", type=str)
@click.option(
    "--unread",
    "-u",
    is_flag=True,
    help="Show only unread notifications.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=50,
    help="Maximum number of notifications to return.",
)
@click.option(
    "--offset",
    "-o",
    type=int,
    default=0,
    help="Offset for pagination.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output in JSON format.",
)
@click.pass_context
def notifications_list(
    ctx: click.Context,
    user_id: str,
    unread: bool,
    limit: int,
    offset: int,
    output_json: bool,
) -> None:
    """
    List notifications for a user.

    Shows notifications for a specific user, optionally filtering for unread only.

    \b
    Examples:
        autoflow activity notifications list user-001
        autoflow activity notifications list user-001 --unread
        autoflow activity notifications list user-001 --limit 20
    """
    state_manager = _get_state_manager_from_ctx(ctx)

    try:
        manager = NotificationManager(state_manager.state_dir)
        manager.initialize()

        # Get notifications
        if unread:
            notifications_list = manager.get_unread_notifications(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
        else:
            notifications_list = manager.get_user_notifications(
                user_id=user_id,
                limit=limit,
                offset=offset,
            )

        if output_json or ctx.obj["output_json"]:
            _print_json({
                "notifications": [n.model_dump(mode="json") for n in notifications_list],
                "count": len(notifications_list),
            })
        else:
            if not notifications_list:
                if unread:
                    click.echo(f"No unread notifications for user: {user_id}")
                else:
                    click.echo(f"No notifications for user: {user_id}")
                return

            if unread:
                click.echo(f"Unread notifications for {user_id} ({len(notifications_list)}):")
            else:
                click.echo(f"Notifications for {user_id} ({len(notifications_list)}):")

            for notification in notifications_list:
                click.echo(f"\n  [{notification.id}]")
                click.echo(f"  Type: {notification.type}")
                click.echo(f"  Title: {notification.title}")
                if notification.message:
                    click.echo(f"  Message: {notification.message}")
                click.echo(f"  Status: {notification.status}")
                click.echo(f"  Created: {_format_datetime(notification.created_at)}")
                if notification.read_at:
                    click.echo(f"  Read: {_format_datetime(notification.read_at)}")

    except Exception as e:
        click.echo(f"Error listing notifications: {e}", err=True)
        ctx.exit(1)


# Register config command group
main.add_command(config_cmd, name="config")

# Register analytics command group
main.add_command(analytics)


if __name__ == "__main__":
    main()
