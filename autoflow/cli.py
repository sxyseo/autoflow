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


# Register config command group
main.add_command(config_cmd, name="config")


# === Intake Commands ===

@main.group()
def intake() -> None:
    """Manage issue intake from external sources."""
    pass


@intake.command("import")
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Source ID to import from (default: all configured sources).",
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["full", "incremental", "since-last"]),
    default="incremental",
    help="Import mode.",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show what would be imported without making changes.",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Maximum number of issues to import.",
)
@click.pass_context
def intake_import(
    ctx: click.Context,
    source: Optional[str],
    mode: str,
    dry_run: bool,
    limit: Optional[int],
) -> None:
    """
    Import issues from external sources.

    Fetches issues from configured sources (GitHub, GitLab, Linear)
    and converts them to Autoflow specs and tasks.

    \b
    Examples:
        autoflow intake import
        autoflow intake import --source github-example
        autoflow intake import --mode full --limit 50
        autoflow intake import --dry-run
    """
    from autoflow.intake import IntakePipeline, IngestionMode

    config: Config = ctx.obj["config"]

    if not config.intake.sources:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": "No intake sources configured. Add sources to your config file.",
            })
        else:
            click.echo("Error: No intake sources configured.", err=True)
            click.echo("Add sources to your config file (see config/intake.example.json5)")
        ctx.exit(1)

    try:
        # Get the sources to import from
        sources = (
            [s for s in config.intake.sources if s.id == source]
            if source
            else config.intake.sources
        )

        if not sources:
            if ctx.obj["output_json"]:
                _print_json({
                    "status": "error",
                    "message": f"Source '{source}' not found.",
                })
            else:
                click.echo(f"Error: Source '{source}' not found.", err=True)
            ctx.exit(1)

        # Map CLI mode to IngestionMode
        mode_map = {
            "full": IngestionMode.FULL,
            "incremental": IngestionMode.INCREMENTAL,
            "since-last": IngestionMode.SINCE_LAST,
        }
        ingestion_mode = mode_map[mode]

        # Create pipeline config
        pipeline_config = {
            "sources": sources,
            "state_dir": str(config.state_dir),
            "dry_run": dry_run,
            "limit": limit,
        }

        # Create and run pipeline (synchronously)
        # Note: The pipeline is async, so we need to run it in an event loop
        async def run_import():
            pipeline = IntakePipeline(config=pipeline_config)  # type: ignore
            result = await pipeline.ingest(mode=ingestion_mode, source_id=source)
            return result

        result = _run_async(run_import())

        if ctx.obj["output_json"]:
            _print_json({
                "status": "success",
                "imported": result.stats.issues_processed,
                "specs_created": result.stats.specs_created,
                "tasks_created": result.stats.tasks_created,
                "errors": len(result.errors),
                "dry_run": dry_run,
            })
        else:
            click.echo("Issue Import")
            click.echo("=" * 60)
            click.echo(f"Mode: {mode}")
            if dry_run:
                click.echo("DRY RUN - No changes were made")
            click.echo("")
            click.echo(f"Issues processed: {result.stats.issues_processed}")
            click.echo(f"Specs created: {result.stats.specs_created}")
            click.echo(f"Tasks created: {result.stats.tasks_created}")
            click.echo(f"Errors: {len(result.errors)}")

            if result.errors:
                click.echo("\nErrors:")
                for error in result.errors[:5]:  # Show first 5 errors
                    click.echo(f"  - {error}")

    except Exception as e:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": str(e),
            })
        else:
            click.echo(f"Error importing issues: {e}", err=True)
        ctx.exit(1)


@intake.command("sync")
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Source ID to sync (default: all configured sources).",
)
@click.option(
    "--direction",
    "-d",
    type=click.Choice(["push", "pull", "bidirectional"]),
    default="push",
    help="Sync direction.",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show what would be synced without making changes.",
)
@click.pass_context
def intake_sync(
    ctx: click.Context,
    source: Optional[str],
    direction: str,
    dry_run: bool,
) -> None:
    """
    Sync issue status with external sources.

    Pushes Autoflow task status back to external issues or pulls
    updates from external sources.

    \b
    Examples:
        autoflow intake sync
        autoflow intake sync --source github-example
        autoflow intake sync --direction pull
        autoflow intake sync --dry-run
    """
    from autoflow.intake import SyncManager, SyncDirection

    config: Config = ctx.obj["config"]

    if not config.intake.sources:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": "No intake sources configured.",
            })
        else:
            click.echo("Error: No intake sources configured.", err=True)
        ctx.exit(1)

    try:
        # Get the sources to sync
        sources = (
            [s for s in config.intake.sources if s.id == source]
            if source
            else config.intake.sources
        )

        if not sources:
            if ctx.obj["output_json"]:
                _print_json({
                    "status": "error",
                    "message": f"Source '{source}' not found.",
                })
            else:
                click.echo(f"Error: Source '{source}' not found.", err=True)
            ctx.exit(1)

        # Map CLI direction to SyncDirection
        direction_map = {
            "push": SyncDirection.PUSH,
            "pull": SyncDirection.PULL,
            "bidirectional": SyncDirection.BIDIRECTIONAL,
        }
        sync_direction = direction_map[direction]

        # Create sync manager config
        sync_config = {
            "sources": sources,
            "state_dir": str(config.state_dir),
            "dry_run": dry_run,
        }

        # Create and run sync (synchronously)
        async def run_sync():
            manager = SyncManager(config=sync_config)  # type: ignore
            result = await manager.sync(direction=sync_direction, source_id=source)
            return result

        result = _run_async(run_sync())

        if ctx.obj["output_json"]:
            _print_json({
                "status": "success",
                "direction": direction,
                "issues_updated": result.stats.issues_updated,
                "tasks_updated": result.stats.tasks_updated,
                "errors": len(result.errors),
                "dry_run": dry_run,
            })
        else:
            click.echo("Issue Sync")
            click.echo("=" * 60)
            click.echo(f"Direction: {direction}")
            if dry_run:
                click.echo("DRY RUN - No changes were made")
            click.echo("")
            click.echo(f"Issues updated: {result.stats.issues_updated}")
            click.echo(f"Tasks updated: {result.stats.tasks_updated}")
            click.echo(f"Errors: {len(result.errors)}")

            if result.errors:
                click.echo("\nErrors:")
                for error in result.errors[:5]:  # Show first 5 errors
                    click.echo(f"  - {error}")

    except Exception as e:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": str(e),
            })
        else:
            click.echo(f"Error syncing issues: {e}", err=True)
        ctx.exit(1)


@intake.command("status")
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Source ID to show status for (default: all sources).",
)
@click.option(
    "--detailed",
    "-d",
    is_flag=True,
    help="Show detailed status information.",
)
@click.pass_context
def intake_status(
    ctx: click.Context,
    source: Optional[str],
    detailed: bool,
) -> None:
    """
    Show issue intake system status.

    Displays the current state of configured sources, recent imports,
    and sync information.

    \b
    Examples:
        autoflow intake status
        autoflow intake status --source github-example
        autoflow intake status --detailed
    """
    from autoflow.intake import SyncManager

    config: Config = ctx.obj["config"]
    state_manager = _get_state_manager(config)

    try:
        # Filter sources if specified
        sources = (
            [s for s in config.intake.sources if s.id == source]
            if source
            else config.intake.sources
        )

        if not sources:
            click.echo(f"Error: Source '{source}' not found.", err=True)
            ctx.exit(1)

        if ctx.obj["output_json"]:
            source_data = []
            for s in sources:
                source_data.append({
                    "id": s.id,
                    "type": s.type,
                    "name": s.name,
                    "enabled": s.enabled,
                    "url": s.url,
                })
            _print_json({
                "sources": source_data,
                "count": len(sources),
                "state_dir": str(config.state_dir),
            })
        else:
            click.echo("Issue Intake Status")
            click.echo("=" * 60)
            click.echo(f"State Directory: {config.state_dir}")
            click.echo(f"Sources Configured: {len(sources)}")
            click.echo("")

            for s in sources:
                status_icon = "✓" if s.enabled else "✗"
                click.echo(f"{status_icon} [{s.id}] {s.type}: {s.name}")
                click.echo(f"  URL: {s.url}")

                if detailed:
                    # Get sync state for this source
                    sync_state_file = (
                        Path(config.state_dir) / "intake" / "sync" / f"{s.id}.json"
                    )
                    if sync_state_file.exists():
                        import json
                        with open(sync_state_file) as f:
                            sync_state = json.load(f)
                        click.echo(f"  Last Sync: {sync_state.get('last_sync_at', 'Never')}")
                        click.echo(f"  Mappings: {len(sync_state.get('mappings', []))}")

                click.echo("")

    except Exception as e:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": str(e),
            })
        else:
            click.echo(f"Error getting status: {e}", err=True)
        ctx.exit(1)


@intake.command("webhook")
@click.option(
    "--host",
    "-H",
    type=str,
    default="127.0.0.1",
    help="Host to bind the server to.",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8080,
    help="Port to listen on.",
)
@click.option(
    "--path",
    type=str,
    default="/webhook",
    help="Webhook endpoint path.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    help="Disable webhook signature verification.",
)
@click.pass_context
def intake_webhook(
    ctx: click.Context,
    host: str,
    port: int,
    path: str,
    no_verify: bool,
) -> None:
    """
    Start the webhook server for receiving issue events.

    Starts a FastAPI-based webhook server that receives and processes
    issue events from GitHub, GitLab, and Linear.

    \b
    Examples:
        autoflow intake webhook
        autoflow intake webhook --host 0.0.0.0 --port 8080
        autoflow intake webhook --path /hooks
        autoflow intake webhook --no-verify
    """
    from autoflow.intake import WebhookServer, WebhookConfig

    config: Config = ctx.obj["config"]

    try:
        # Create webhook config
        webhook_config = WebhookConfig(
            host=host,
            port=port,
            path=path,
            verify_signatures=not no_verify,
        )

        # Create and start server
        server = WebhookServer(config=webhook_config)

        if ctx.obj["output_json"]:
            _print_json({
                "status": "starting",
                "host": host,
                "port": port,
                "path": path,
                "verify_signatures": not no_verify,
            })
        else:
            click.echo("Starting Webhook Server")
            click.echo("=" * 60)
            click.echo(f"Host: {host}")
            click.echo(f"Port: {port}")
            click.echo(f"Path: {path}")
            click.echo(f"Signature Verification: {not no_verify}")
            click.echo("")
            click.echo(f"Webhook URL: http://{host}:{port}{path}")
            click.echo("")
            click.echo("Press Ctrl+C to stop the server")
            click.echo("")

        # Start the server (blocking)
        _run_async(server.start())

    except ImportError as e:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": "Missing dependencies",
                "error": str(e),
            })
        else:
            click.echo("Error: Missing required dependencies.", err=True)
            click.echo("Install them with: pip install fastapi uvicorn", err=True)
            click.echo(f"Details: {e}", err=True)
        ctx.exit(1)

    except Exception as e:
        if ctx.obj["output_json"]:
            _print_json({
                "status": "error",
                "message": str(e),
            })
        else:
            click.echo(f"Error starting webhook server: {e}", err=True)
        ctx.exit(1)


if __name__ == "__main__":
    main()
