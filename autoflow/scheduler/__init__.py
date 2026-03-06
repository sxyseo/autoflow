"""
Autoflow Scheduler - Background Task Scheduling

This module provides cron-based scheduling for continuous operation:
- SchedulerDaemon: Background daemon with APScheduler
- Job definitions: Monitoring and task distribution

Enables automated task distribution and agent health monitoring.

Usage:
    from autoflow.scheduler import SchedulerDaemon

    daemon = SchedulerDaemon()
    await daemon.start()
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
]
