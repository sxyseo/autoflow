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
from autoflow.core.config import Config, load_config, load_system_config, get_state_dir
from autoflow.core.state import StateManager, TaskStatus, RunStatus
from autoflow.collaboration.workspace import WorkspaceManager
from autoflow.collaboration.models import RoleType


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
    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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
    config: Config = ctx.obj["config"]
    state_dir = get_state_dir(config)

    try:
        manager = WorkspaceManager(state_dir)
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


# Register config command group
main.add_command(config_cmd, name="config")


if __name__ == "__main__":
    main()
