"""
Autoflow Scheduler Jobs Module

Provides job definitions for the scheduler daemon:
- monitor_agents: Health monitoring for active agent sessions
- distribute_tasks: Task distribution to available agents
- cleanup_sessions: Cleanup of stale tmux sessions
- health_check: System health verification

These jobs are designed to be called by the SchedulerDaemon via cron schedules.

Usage:
    from autoflow.scheduler.jobs import monitor_agents, distribute_tasks

    # Jobs are called automatically by the scheduler
    # Or can be invoked directly:
    result = await monitor_agents()
    result = await distribute_tasks()
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from autoflow.core.config import Config, load_config
from autoflow.core.state import RunStatus, StateManager, TaskStatus

logger = logging.getLogger(__name__)


# Global orchestrator reference (set by the scheduler daemon)
_orchestrator: Any | None = None


def set_orchestrator(orchestrator: Any) -> None:
    """
    Set the global orchestrator reference for job handlers.

    Args:
        orchestrator: AutoflowOrchestrator instance
    """
    global _orchestrator
    _orchestrator = orchestrator


def get_orchestrator() -> Any | None:
    """
    Get the global orchestrator reference.

    Returns:
        AutoflowOrchestrator instance or None
    """
    return _orchestrator


class JobResult(BaseModel):
    """Result from a scheduled job execution."""

    job_name: str
    success: bool
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    output: str | None = None
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Mark the job as complete."""
        self.success = success
        self.output = output
        self.error = error
        self.completed_at = datetime.utcnow()


@dataclass
class AgentHealthInfo:
    """Health information for an agent session."""

    agent_id: str
    agent_type: str
    status: str
    last_activity: datetime | None = None
    current_task: str | None = None
    uptime_seconds: float | None = None
    is_responsive: bool = True
    error: str | None = None


@dataclass
class TaskDistributionResult:
    """Result from task distribution."""

    tasks_distributed: int = 0
    tasks_pending: int = 0
    agents_available: int = 0
    agents_assigned: int = 0
    assignments: list[dict[str, Any]] = field(default_factory=list)


async def monitor_agents(
    config: Config | None = None,
    state_dir: Path | None = None,
) -> JobResult:
    """
    Monitor agent health and session status.

    This job:
    1. Checks health of all active agent sessions
    2. Identifies hung or unresponsive agents
    3. Updates agent status in state
    4. Triggers recovery for failed agents

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path

    Returns:
        JobResult with monitoring status and metrics

    Example:
        >>> result = await monitor_agents()
        >>> if result.success:
        ...     print(f"Checked {result.metrics['agents_checked']} agents")
    """
    result = JobResult(job_name="monitor_agents")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Initialize state manager
        state = StateManager(state_dir or Path(config.state_dir))
        state.initialize()

        # Get orchestrator reference
        orchestrator = get_orchestrator()

        # Collect health information
        agents_checked = 0
        healthy_agents = 0
        unhealthy_agents = 0
        recovered_agents = 0
        health_infos: list[AgentHealthInfo] = []

        # Check active runs in state
        active_runs = state.list_runs(status=RunStatus.RUNNING)
        active_runs.extend(state.list_runs(status=RunStatus.STARTED))

        for run_data in active_runs:
            agent_id = run_data.get("id", "unknown")
            agent_type = run_data.get("agent", "unknown")

            agents_checked += 1
            health_info = AgentHealthInfo(
                agent_id=agent_id,
                agent_type=agent_type,
                status=run_data.get("status", "unknown"),
                current_task=run_data.get("task_id"),
            )

            # Check if the run has been running too long
            started_at_str = run_data.get("started_at")
            if started_at_str:
                try:
                    started_at = datetime.fromisoformat(started_at_str)
                    uptime = (datetime.utcnow() - started_at).total_seconds()
                    health_info.uptime_seconds = uptime
                    health_info.last_activity = started_at

                    # Check for timeout (default 10 minutes)
                    timeout_seconds = config.agents.claude_code.timeout_seconds
                    if uptime > timeout_seconds:
                        health_info.is_responsive = False
                        health_info.error = f"Agent timed out after {uptime:.0f}s"
                except (ValueError, TypeError):
                    pass

            # If orchestrator available, check tmux session health
            if orchestrator and hasattr(orchestrator, "tmux_manager"):
                tmux_manager = orchestrator.tmux_manager
                session_name = f"autoflow-{agent_type}-{agent_id}"

                try:
                    session_info = await tmux_manager.get_session(session_name)
                    if session_info is None:
                        # Session doesn't exist but run is still active
                        health_info.is_responsive = False
                        health_info.error = "Tmux session not found"
                except Exception as e:
                    logger.debug(
                        "Error checking tmux session %s: %s",
                        session_name,
                        e,
                    )

            # Categorize health
            if health_info.is_responsive:
                healthy_agents += 1
            else:
                unhealthy_agents += 1

                # Attempt recovery for unhealthy agents
                if orchestrator and hasattr(orchestrator, "state"):
                    try:
                        # Mark run as failed
                        run_data["status"] = RunStatus.TIMEOUT.value
                        run_data["error"] = health_info.error
                        run_data["completed_at"] = datetime.utcnow().isoformat()
                        state.save_run(agent_id, run_data)

                        # Kill orphaned tmux session if exists
                        if hasattr(orchestrator, "tmux_manager"):
                            session_name = f"autoflow-{agent_type}-{agent_id}"
                            await orchestrator.tmux_manager.kill_session(session_name)

                        recovered_agents += 1
                        logger.info(
                            "Recovered unhealthy agent %s: %s",
                            agent_id,
                            health_info.error,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to recover agent %s: %s",
                            agent_id,
                            e,
                        )

            health_infos.append(health_info)

        # Save monitoring results to memory
        state.save_memory(
            key="last_agent_monitor",
            value={
                "agents_checked": agents_checked,
                "healthy_agents": healthy_agents,
                "unhealthy_agents": unhealthy_agents,
                "recovered_agents": recovered_agents,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="monitoring",
            expires_in_seconds=3600,  # 1 hour
        )

        result.mark_complete(
            success=True,
            output=(
                f"Checked {agents_checked} agents: "
                f"{healthy_agents} healthy, {unhealthy_agents} unhealthy, "
                f"{recovered_agents} recovered"
            ),
        )
        result.metrics = {
            "agents_checked": agents_checked,
            "healthy_agents": healthy_agents,
            "unhealthy_agents": unhealthy_agents,
            "recovered_agents": recovered_agents,
        }

        logger.info(
            "Agent monitoring complete: %d checked, %d healthy, %d unhealthy",
            agents_checked,
            healthy_agents,
            unhealthy_agents,
        )

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Agent monitoring failed: %s", e)

    return result


async def distribute_tasks(
    config: Config | None = None,
    state_dir: Path | None = None,
) -> JobResult:
    """
    Distribute pending tasks to available agents.

    This job:
    1. Gets list of pending tasks from state
    2. Identifies available agents
    3. Assigns tasks based on priority and capability
    4. Triggers task execution

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path

    Returns:
        JobResult with distribution status and metrics

    Example:
        >>> result = await distribute_tasks()
        >>> print(f"Distributed {result.metrics['tasks_distributed']} tasks")
    """
    result = JobResult(job_name="distribute_tasks")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Initialize state manager
        state = StateManager(state_dir or Path(config.state_dir))
        state.initialize()

        # Get orchestrator reference
        orchestrator = get_orchestrator()

        # Get pending tasks (sorted by priority)
        pending_tasks = state.list_tasks(status=TaskStatus.PENDING)
        pending_tasks.sort(key=lambda t: t.get("priority", 5), reverse=True)

        # Get running tasks to check capacity
        running_tasks = state.list_tasks(status=TaskStatus.IN_PROGRESS)

        # Calculate available capacity
        max_concurrent = 3  # Default max concurrent agents
        if orchestrator and hasattr(orchestrator, "config"):
            # Try to get from system config if available
            pass

        available_slots = max(0, max_concurrent - len(running_tasks))

        distribution_result = TaskDistributionResult(
            tasks_pending=len(pending_tasks),
            agents_available=available_slots,
        )

        # Distribute tasks if capacity available
        if available_slots > 0 and pending_tasks:
            tasks_to_assign = pending_tasks[:available_slots]

            for task_data in tasks_to_assign:
                task_id = task_data.get("id")
                task_title = task_data.get("title", "Untitled task")
                task_description = task_data.get("description", task_title)
                task_data.get("labels", [])

                # Determine best agent type based on task
                agent_type = _select_agent_for_task(task_data, config)

                # Assign the task
                assignment = {
                    "task_id": task_id,
                    "task_title": task_title,
                    "agent_type": agent_type,
                    "assigned_at": datetime.utcnow().isoformat(),
                }

                try:
                    # Update task status
                    task_data["status"] = TaskStatus.IN_PROGRESS.value
                    task_data["assigned_agent"] = agent_type
                    task_data["assigned_at"] = datetime.utcnow().isoformat()
                    state.save_task(task_id, task_data)

                    # If orchestrator available, start execution
                    if orchestrator:
                        # Create async task for execution
                        asyncio.create_task(
                            _execute_distributed_task(
                                orchestrator=orchestrator,
                                task_id=task_id,
                                task_description=task_description,
                                agent_type=agent_type,
                            )
                        )

                    distribution_result.tasks_distributed += 1
                    distribution_result.assignments.append(assignment)

                    logger.info(
                        "Distributed task %s to %s agent: %s",
                        task_id,
                        agent_type,
                        task_title[:50],
                    )

                except Exception as e:
                    logger.error(
                        "Failed to distribute task %s: %s",
                        task_id,
                        e,
                    )

        # Save distribution results
        state.save_memory(
            key="last_task_distribution",
            value={
                "tasks_distributed": distribution_result.tasks_distributed,
                "tasks_pending": distribution_result.tasks_pending,
                "agents_available": distribution_result.agents_available,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="distribution",
            expires_in_seconds=600,  # 10 minutes
        )

        output = (
            f"Distributed {distribution_result.tasks_distributed} tasks, "
            f"{distribution_result.tasks_pending} pending"
        )

        result.mark_complete(success=True, output=output)
        result.metrics = {
            "tasks_distributed": distribution_result.tasks_distributed,
            "tasks_pending": distribution_result.tasks_pending,
            "agents_available": distribution_result.agents_available,
            "assignments": distribution_result.assignments,
        }

        logger.info(
            "Task distribution complete: %d distributed, %d pending",
            distribution_result.tasks_distributed,
            distribution_result.tasks_pending,
        )

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Task distribution failed: %s", e)

    return result


def _select_agent_for_task(
    task_data: dict[str, Any],
    config: Config,
) -> str:
    """
    Select the best agent type for a task.

    Args:
        task_data: Task data dictionary
        config: Configuration object

    Returns:
        Agent type string (e.g., "claude-code", "codex")
    """
    labels = task_data.get("labels", [])
    description = task_data.get("description", "").lower()
    title = task_data.get("title", "").lower()

    # Check for explicit agent preference
    preferred_agent = task_data.get("metadata", {}).get("preferred_agent")
    if preferred_agent:
        return preferred_agent

    # Select based on task characteristics
    if "review" in labels or "review" in description or "review" in title:
        return "claude-code"  # Claude is better at code review

    if "implement" in labels or "implement" in description:
        return "claude-code"  # Claude is good at implementation

    if "test" in labels or "test" in description:
        return "claude-code"  # Claude is good at test writing

    if "refactor" in labels or "refactor" in description:
        return "claude-code"  # Claude is good at refactoring

    # Check if codex is preferred for this type of task
    if "quick" in labels or "fast" in description:
        return "codex"  # Codex can be faster for simple tasks

    # Default to claude-code
    return "claude-code"


async def _execute_distributed_task(
    orchestrator: Any,
    task_id: str,
    task_description: str,
    agent_type: str,
) -> None:
    """
    Execute a distributed task using the orchestrator.

    Args:
        orchestrator: AutoflowOrchestrator instance
        task_id: Task ID
        task_description: Task description
        agent_type: Agent type to use
    """
    try:
        result = await orchestrator.run_task(
            task=task_description,
            skill_name="IMPLEMENTER",
            agent_type=agent_type,
            metadata={"task_id": task_id, "source": "distribution"},
        )

        if result.success:
            logger.info(
                "Distributed task %s completed successfully",
                task_id,
            )
        else:
            logger.warning(
                "Distributed task %s failed: %s",
                task_id,
                result.error,
            )

    except Exception as e:
        logger.error(
            "Failed to execute distributed task %s: %s",
            task_id,
            e,
        )


async def cleanup_sessions(
    config: Config | None = None,
    state_dir: Path | None = None,
    max_age_hours: int = 24,
) -> JobResult:
    """
    Clean up stale tmux sessions and expired state.

    This job:
    1. Identifies tmux sessions older than max_age_hours
    2. Cleans up completed/failed runs from state
    3. Removes expired memory entries
    4. Cleans up old backup files

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path
        max_age_hours: Maximum age of sessions to keep

    Returns:
        JobResult with cleanup status and metrics
    """
    result = JobResult(job_name="cleanup_sessions")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Initialize state manager
        state = StateManager(state_dir or Path(config.state_dir))
        state.initialize()

        # Get orchestrator reference
        orchestrator = get_orchestrator()

        sessions_cleaned = 0
        runs_cleaned = 0
        memory_cleaned = 0
        backups_cleaned = 0

        # Clean up expired memory
        memory_cleaned = state.cleanup_expired()

        # Clean up old backups
        backups_cleaned = state.compact_backups(max_age_days=7)

        # Clean up stale tmux sessions
        if orchestrator and hasattr(orchestrator, "tmux_manager"):
            tmux_manager = orchestrator.tmux_manager

            # Get all autoflow sessions
            try:
                sessions = await tmux_manager.list_sessions(prefix="autoflow-")

                cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)

                for session_info in sessions:
                    # Check session age
                    created_at = session_info.get("created_at")
                    if created_at:
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            if created_dt.timestamp() < cutoff_time:
                                await tmux_manager.kill_session(session_info["name"])
                                sessions_cleaned += 1
                                logger.info(
                                    "Cleaned up stale session: %s",
                                    session_info["name"],
                                )
                        except (ValueError, TypeError):
                            pass

            except Exception as e:
                logger.debug("Error listing tmux sessions: %s", e)

        # Clean up old completed/failed runs
        runs = state.list_runs()
        cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)

        for run_data in runs:
            status = run_data.get("status")
            if status in (
                RunStatus.COMPLETED.value,
                RunStatus.FAILED.value,
                RunStatus.TIMEOUT.value,
                RunStatus.CANCELLED.value,
            ):
                completed_at_str = run_data.get("completed_at")
                if completed_at_str:
                    try:
                        completed_at = datetime.fromisoformat(completed_at_str)
                        if completed_at.timestamp() < cutoff_time:
                            run_id = run_data.get("id")
                            state.delete_task(run_id)  # Use delete_task for runs too
                            runs_cleaned += 1
                    except (ValueError, TypeError):
                        pass

        output = (
            f"Cleaned: {sessions_cleaned} sessions, "
            f"{runs_cleaned} runs, "
            f"{memory_cleaned} memory entries, "
            f"{backups_cleaned} backups"
        )

        result.mark_complete(success=True, output=output)
        result.metrics = {
            "sessions_cleaned": sessions_cleaned,
            "runs_cleaned": runs_cleaned,
            "memory_cleaned": memory_cleaned,
            "backups_cleaned": backups_cleaned,
        }

        logger.info("Cleanup complete: %s", output)

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Cleanup failed: %s", e)

    return result


async def health_check(
    config: Config | None = None,
    state_dir: Path | None = None,
) -> JobResult:
    """
    Perform system health check.

    This job:
    1. Checks state directory accessibility
    2. Verifies tmux availability
    3. Checks agent adapter availability
    4. Reports system status

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path

    Returns:
        JobResult with health check status
    """
    result = JobResult(job_name="health_check")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Initialize state manager
        state = StateManager(state_dir or Path(config.state_dir))

        health_status = {
            "state_accessible": False,
            "state_initialized": False,
            "tmux_available": False,
            "agents_available": [],
        }

        # Check state directory
        try:
            state.initialize()
            health_status["state_accessible"] = True
            health_status["state_initialized"] = state.state_dir.exists()
        except Exception as e:
            logger.warning("State directory check failed: %s", e)

        # Check tmux availability
        try:
            from autoflow.tmux.manager import TmuxManager

            if await TmuxManager.check_tmux_available():
                health_status["tmux_available"] = True
        except Exception:
            pass

        # Check agent adapters
        try:
            from autoflow.agents.claude_code import ClaudeCodeAdapter

            adapter = ClaudeCodeAdapter()
            if await adapter.check_health():
                health_status["agents_available"].append("claude-code")
        except Exception:
            pass

        try:
            from autoflow.agents.codex import CodexAdapter

            adapter = CodexAdapter()
            if await adapter.check_health():
                health_status["agents_available"].append("codex")
        except Exception:
            pass

        # Determine overall health
        is_healthy = (
            health_status["state_accessible"]
            and len(health_status["agents_available"]) > 0
        )

        # Save health status
        state.save_memory(
            key="system_health",
            value={
                **health_status,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="health",
            expires_in_seconds=300,  # 5 minutes
        )

        output = (
            f"State: {'OK' if health_status['state_accessible'] else 'ERROR'}, "
            f"Tmux: {'OK' if health_status['tmux_available'] else 'N/A'}, "
            f"Agents: {', '.join(health_status['agents_available']) or 'None'}"
        )

        result.mark_complete(success=is_healthy, output=output)
        result.metrics = health_status

        if not is_healthy:
            result.error = "System health check failed"

        logger.info("Health check: %s", output)

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Health check failed: %s", e)

    return result


# Job registry for easy reference
JOB_REGISTRY = {
    "monitor_agents": {
        "handler": monitor_agents,
        "default_cron": "*/5 * * * *",  # Every 5 minutes
        "description": "Monitor agent health and recover failed agents",
    },
    "distribute_tasks": {
        "handler": distribute_tasks,
        "default_cron": "*/10 * * * *",  # Every 10 minutes
        "description": "Distribute pending tasks to available agents",
    },
    "cleanup_sessions": {
        "handler": cleanup_sessions,
        "default_cron": "0 * * * *",  # Every hour
        "description": "Clean up stale sessions and expired state",
    },
    "health_check": {
        "handler": health_check,
        "default_cron": "*/15 * * * *",  # Every 15 minutes
        "description": "Perform system health check",
    },
}
