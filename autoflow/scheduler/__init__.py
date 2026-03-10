"""
Autoflow Scheduler - Background Task Scheduling

This module provides cron-based scheduling for continuous operation:
- SchedulerDaemon: Background daemon with APScheduler
- Job definitions: Monitoring and task distribution

Enables automated task distribution and agent health monitoring.

Usage:
    from autoflow.scheduler import SchedulerDaemon
    from autoflow.scheduler.jobs import monitor_agents, distribute_tasks

    daemon = SchedulerDaemon()
    await daemon.start()

    # Or run jobs directly:
    result = await monitor_agents()
"""

from autoflow.scheduler.daemon import (
    DaemonStatus,
    DaemonStats,
    JobExecutionResult,
    JobInfo,
    JobStatus,
    SchedulerDaemon,
    SchedulerDaemonError,
    run_daemon,
)
from autoflow.scheduler.jobs import (
    JOB_REGISTRY,
    JobResult,
    cleanup_sessions,
    distribute_tasks,
    get_orchestrator,
    health_check,
    monitor_agents,
    set_orchestrator,
)
from autoflow.scheduler.pr_refresh_job import refresh_prs

__all__ = [
    # Daemon
    "SchedulerDaemon",
    "SchedulerDaemonError",
    "run_daemon",
    # Status enums
    "DaemonStatus",
    "JobStatus",
    # Data models
    "DaemonStats",
    "JobInfo",
    "JobExecutionResult",
    # Jobs
    "JobResult",
    "JOB_REGISTRY",
    "monitor_agents",
    "distribute_tasks",
    "cleanup_sessions",
    "health_check",
    "refresh_prs",
    "set_orchestrator",
    "get_orchestrator",
]
