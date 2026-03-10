"""
Autoflow Scheduler Daemon Module

Provides background task scheduling using APScheduler for continuous operation.
Supports cron-based scheduling, job management, and graceful shutdown.

Usage:
    from autoflow.scheduler.daemon import SchedulerDaemon

    # Create and start the daemon
    daemon = SchedulerDaemon()
    await daemon.start()

    # Or use as context manager
    async with SchedulerDaemon() as daemon:
        await daemon.add_job(my_handler, "*/5 * * * *", job_id="my-job")

    # Stop gracefully
    await daemon.stop()
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field

from autoflow.core.config import Config, SchedulerJobConfig, load_config

logger = logging.getLogger(__name__)


class DaemonStatus(StrEnum):
    """Status of the scheduler daemon."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class JobStatus(StrEnum):
    """Status of a scheduled job."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"
    RUNNING = "running"
    ERROR = "error"


class JobExecutionResult(BaseModel):
    """Result from a job execution."""

    job_id: str
    success: bool
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    output: str | None = None
    error: str | None = None
    duration_seconds: float | None = None

    def mark_complete(
        self,
        success: bool,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Mark the execution as complete."""
        self.success = success
        self.output = output
        self.error = error
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


class JobInfo(BaseModel):
    """Information about a scheduled job."""

    id: str
    handler: str
    cron: str
    status: JobStatus = JobStatus.ENABLED
    next_run: datetime | None = None
    last_run: datetime | None = None
    last_result: JobExecutionResult | None = None
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of this job."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs


class DaemonStats(BaseModel):
    """Statistics about the scheduler daemon."""

    started_at: datetime | None = None
    total_jobs: int = 0
    active_jobs: int = 0
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    last_execution_at: datetime | None = None


class SchedulerDaemonError(Exception):
    """Exception raised for scheduler daemon errors."""

    def __init__(self, message: str, job_id: str | None = None):
        self.job_id = job_id
        super().__init__(message)


class SchedulerDaemon:
    """
    Background scheduler daemon using APScheduler.

    Provides cron-based job scheduling for continuous operation of
    Autoflow tasks including agent monitoring and task distribution.

    Features:
    - Cron-based scheduling via APScheduler
    - Dynamic job addition/removal
    - Graceful shutdown handling
    - Job execution tracking
    - Integration with AutoflowOrchestrator

    Example:
        >>> daemon = SchedulerDaemon()
        >>> await daemon.start()
        >>>
        >>> # Add a custom job
        >>> await daemon.add_job(
        ...     handler=my_handler,
        ...     cron="*/5 * * * *",
        ...     job_id="my-job"
        ... )
        >>>
        >>> # Check status
        >>> print(daemon.status)
        DaemonStatus.RUNNING
        >>>
        >>> # Stop gracefully
        >>> await daemon.stop()

    Attributes:
        config: Configuration object
        status: Current daemon status
        stats: Daemon statistics
    """

    DEFAULT_GRACEFUL_TIMEOUT = 10  # Seconds to wait for graceful shutdown

    def __init__(
        self,
        config: Config | None = None,
        auto_start: bool = False,
        graceful_timeout: int = DEFAULT_GRACEFUL_TIMEOUT,
    ) -> None:
        """
        Initialize the scheduler daemon.

        Args:
            config: Optional configuration object
            auto_start: If True, start the daemon immediately
            graceful_timeout: Seconds to wait for graceful shutdown
        """
        self._config = config
        self._graceful_timeout = graceful_timeout

        # Status tracking
        self._status = DaemonStatus.STOPPED
        self._scheduler: AsyncIOScheduler | None = None

        # Job tracking
        self._jobs: dict[str, JobInfo] = {}
        self._running_executions: dict[str, JobExecutionResult] = {}

        # Statistics
        self._stats = DaemonStats()

        # Orchestrator reference (set externally)
        self._orchestrator: Any | None = None

        # Shutdown handling
        self._shutdown_event = asyncio.Event()
        self._setup_signal_handlers()

        if auto_start:
            asyncio.create_task(self.start())

    @property
    def config(self) -> Config:
        """Get configuration, loading if needed."""
        if self._config is None:
            self._config = load_config()
        return self._config

    @property
    def status(self) -> DaemonStatus:
        """Get current daemon status."""
        return self._status

    @property
    def stats(self) -> DaemonStats:
        """Get daemon statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._status == DaemonStatus.RUNNING

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda: asyncio.create_task(self._handle_shutdown_signal()),
                )
        except (RuntimeError, NotImplementedError):
            # No event loop or signal handling not supported
            pass

    async def _handle_shutdown_signal(self) -> None:
        """Handle shutdown signal gracefully."""
        logger.info("Received shutdown signal, stopping scheduler...")
        await self.stop()

    def set_orchestrator(self, orchestrator: Any) -> None:
        """
        Set the orchestrator reference for job handlers.

        Args:
            orchestrator: AutoflowOrchestrator instance
        """
        self._orchestrator = orchestrator

    async def start(self) -> None:
        """
        Start the scheduler daemon.

        Initializes APScheduler and loads configured jobs.

        Raises:
            SchedulerDaemonError: If startup fails
        """
        if self._status in (DaemonStatus.RUNNING, DaemonStatus.STARTING):
            return

        self._status = DaemonStatus.STARTING
        logger.info("Starting scheduler daemon...")

        try:
            # Create scheduler
            self._scheduler = AsyncIOScheduler()

            # Load jobs from configuration
            await self._load_configured_jobs()

            # Start the scheduler
            self._scheduler.start()

            self._status = DaemonStatus.RUNNING
            self._stats.started_at = datetime.utcnow()

            logger.info(
                "Scheduler daemon started with %d jobs",
                self._stats.active_jobs,
            )

        except Exception as e:
            self._status = DaemonStatus.ERROR
            logger.error("Failed to start scheduler daemon: %s", e)
            raise SchedulerDaemonError(f"Failed to start scheduler: {e}") from e

    async def stop(self, graceful: bool = True) -> None:
        """
        Stop the scheduler daemon.

        Args:
            graceful: If True, wait for running jobs to complete

        Raises:
            SchedulerDaemonError: If stop fails
        """
        if self._status in (DaemonStatus.STOPPED, DaemonStatus.STOPPING):
            return

        self._status = DaemonStatus.STOPPING
        logger.info("Stopping scheduler daemon...")

        try:
            if self._scheduler:
                if graceful and self._running_executions:
                    logger.info(
                        "Waiting for %d running jobs to complete...",
                        len(self._running_executions),
                    )
                    # Wait for running jobs with timeout
                    try:
                        await asyncio.wait_for(
                            self._wait_for_running_jobs(),
                            timeout=self._graceful_timeout,
                        )
                    except TimeoutError:
                        logger.warning("Graceful shutdown timed out, forcing stop")

                self._scheduler.shutdown(wait=graceful)
                self._scheduler = None

            self._status = DaemonStatus.STOPPED
            logger.info("Scheduler daemon stopped")

        except Exception as e:
            self._status = DaemonStatus.ERROR
            logger.error("Failed to stop scheduler daemon: %s", e)
            raise SchedulerDaemonError(f"Failed to stop scheduler: {e}") from e

    async def _wait_for_running_jobs(self) -> None:
        """Wait for all running jobs to complete."""
        while self._running_executions:
            await asyncio.sleep(0.5)

    async def pause(self) -> None:
        """
        Pause the scheduler daemon.

        Suspends all job execution without stopping the scheduler.
        """
        if self._status != DaemonStatus.RUNNING:
            return

        if self._scheduler:
            self._scheduler.pause()
            self._status = DaemonStatus.PAUSED
            logger.info("Scheduler daemon paused")

    async def resume(self) -> None:
        """
        Resume the scheduler daemon.

        Resumes job execution after being paused.
        """
        if self._status != DaemonStatus.PAUSED:
            return

        if self._scheduler:
            self._scheduler.resume()
            self._status = DaemonStatus.RUNNING
            logger.info("Scheduler daemon resumed")

    async def _load_configured_jobs(self) -> None:
        """Load jobs from configuration."""
        if not self.config.scheduler.enabled:
            logger.info("Scheduler disabled in configuration")
            return

        for job_config in self.config.scheduler.jobs:
            if job_config.enabled:
                try:
                    await self._add_job_from_config(job_config)
                except Exception as e:
                    logger.error(
                        "Failed to load job %s: %s",
                        job_config.id,
                        e,
                    )

        self._stats.total_jobs = len(self._jobs)
        self._stats.active_jobs = sum(
            1 for j in self._jobs.values() if j.status == JobStatus.ENABLED
        )

    async def _add_job_from_config(self, job_config: SchedulerJobConfig) -> None:
        """
        Add a job from configuration.

        Args:
            job_config: Job configuration object
        """
        handler = self._resolve_handler(job_config.handler)
        await self.add_job(
            handler=handler,
            cron=job_config.cron,
            job_id=job_config.id,
        )

    def _resolve_handler(self, handler_path: str) -> Callable:
        """
        Resolve a handler function from its path.

        Args:
            handler_path: Dotted path to handler function
                         (e.g., "autoflow.scheduler.jobs:monitor_agents")

        Returns:
            Callable handler function

        Raises:
            SchedulerDaemonError: If handler cannot be resolved
        """
        try:
            if ":" in handler_path:
                module_path, func_name = handler_path.rsplit(":", 1)
            elif "." in handler_path:
                module_path, func_name = handler_path.rsplit(".", 1)
            else:
                raise SchedulerDaemonError(f"Invalid handler path: {handler_path}")

            # Import the module
            parts = module_path.split(".")
            module = __import__(parts[0])
            for part in parts[1:]:
                module = getattr(module, part)

            handler = getattr(module, func_name)

            if not callable(handler):
                raise SchedulerDaemonError(f"Handler {handler_path} is not callable")

            return handler

        except (ImportError, AttributeError) as e:
            raise SchedulerDaemonError(
                f"Failed to resolve handler {handler_path}: {e}"
            ) from e

    async def add_job(
        self,
        handler: Callable,
        cron: str,
        job_id: str | None = None,
        name: str | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a new scheduled job.

        Args:
            handler: Callable to execute (can be sync or async)
            cron: Cron expression for schedule
            job_id: Optional job ID (auto-generated if not provided)
            name: Optional human-readable name
            kwargs: Optional keyword arguments for the handler

        Returns:
            Job ID

        Raises:
            SchedulerDaemonError: If job cannot be added

        Example:
            >>> async def my_handler():
            ...     print("Running!")
            >>> job_id = await daemon.add_job(
            ...     handler=my_handler,
            ...     cron="*/5 * * * *",
            ...     job_id="my-job"
            ... )
        """
        if not self._scheduler:
            raise SchedulerDaemonError("Scheduler not initialized")

        if job_id is None:
            import uuid

            job_id = f"job-{uuid.uuid4().hex[:8]}"

        # Create job info
        job_info = JobInfo(
            id=job_id,
            handler=f"{handler.__module__}:{handler.__name__}",
            cron=cron,
            status=JobStatus.ENABLED,
        )
        self._jobs[job_id] = job_info

        # Create wrapper that tracks execution
        wrapped_handler = self._create_wrapped_handler(job_id, handler, kwargs)

        # Create cron trigger
        trigger = CronTrigger.from_crontab(cron)

        # Add job to scheduler
        self._scheduler.add_job(
            wrapped_handler,
            trigger=trigger,
            id=job_id,
            name=name or job_id,
            kwargs=kwargs or {},
        )

        # Update next run time
        job = self._scheduler.get_job(job_id)
        if job:
            job_info.next_run = job.next_run_time

        logger.info("Added job %s with schedule: %s", job_id, cron)
        return job_id

    def _create_wrapped_handler(
        self,
        job_id: str,
        handler: Callable,
        kwargs: dict[str, Any] | None = None,
    ) -> Callable:
        """
        Create a wrapped handler that tracks execution.

        Args:
            job_id: Job ID
            handler: Original handler function
            kwargs: Keyword arguments for the handler

        Returns:
            Wrapped handler function
        """

        async def wrapped(*args, **handler_kwargs) -> JobExecutionResult:
            result = JobExecutionResult(job_id=job_id)
            self._running_executions[job_id] = result
            job_info = self._jobs.get(job_id)

            if job_info:
                job_info.status = JobStatus.RUNNING

            try:
                # Merge provided kwargs with handler kwargs
                merged_kwargs = {**(kwargs or {}), **handler_kwargs}

                # Execute handler
                if asyncio.iscoroutinefunction(handler):
                    output = await handler(**merged_kwargs)
                else:
                    output = handler(**merged_kwargs)

                result.mark_complete(
                    success=True,
                    output=str(output) if output else None,
                )

                if job_info:
                    job_info.successful_runs += 1

                logger.debug("Job %s completed successfully", job_id)

            except Exception as e:
                result.mark_complete(
                    success=False,
                    error=str(e),
                )

                if job_info:
                    job_info.failed_runs += 1
                    job_info.status = JobStatus.ERROR

                logger.error("Job %s failed: %s", job_id, e)

            finally:
                self._running_executions.pop(job_id, None)

                if job_info:
                    job_info.total_runs += 1
                    job_info.last_run = result.completed_at
                    job_info.last_result = result

                    # Reset status if not in error state
                    if job_info.status == JobStatus.RUNNING:
                        job_info.status = JobStatus.ENABLED

                    # Update next run time
                    if self._scheduler:
                        job = self._scheduler.get_job(job_id)
                        if job:
                            job_info.next_run = job.next_run_time

                # Update stats
                self._stats.total_executions += 1
                if result.success:
                    self._stats.successful_executions += 1
                else:
                    self._stats.failed_executions += 1
                self._stats.last_execution_at = result.completed_at

            return result

        return wrapped

    async def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_id: ID of the job to remove

        Returns:
            True if job was removed, False if not found
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.remove_job(job_id)
            self._jobs.pop(job_id, None)
            self._stats.total_jobs = len(self._jobs)
            self._stats.active_jobs = sum(
                1 for j in self._jobs.values() if j.status == JobStatus.ENABLED
            )
            logger.info("Removed job %s", job_id)
            return True
        except Exception:
            return False

    async def pause_job(self, job_id: str) -> bool:
        """
        Pause a scheduled job.

        Args:
            job_id: ID of the job to pause

        Returns:
            True if job was paused, False if not found
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.pause_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id].status = JobStatus.PAUSED
            logger.info("Paused job %s", job_id)
            return True
        except Exception:
            return False

    async def resume_job(self, job_id: str) -> bool:
        """
        Resume a paused job.

        Args:
            job_id: ID of the job to resume

        Returns:
            True if job was resumed, False if not found
        """
        if not self._scheduler:
            return False

        try:
            self._scheduler.resume_job(job_id)
            if job_id in self._jobs:
                self._jobs[job_id].status = JobStatus.ENABLED
                # Update next run time
                job = self._scheduler.get_job(job_id)
                if job:
                    self._jobs[job_id].next_run = job.next_run_time
            logger.info("Resumed job %s", job_id)
            return True
        except Exception:
            return False

    async def run_job_now(self, job_id: str) -> JobExecutionResult | None:
        """
        Trigger a job to run immediately.

        Args:
            job_id: ID of the job to run

        Returns:
            JobExecutionResult or None if job not found
        """
        if not self._scheduler:
            return None

        job = self._scheduler.get_job(job_id)
        if not job:
            return None

        # Get the wrapped handler
        handler = job.func

        # Run it directly
        try:
            result = await handler()
            return result
        except Exception as e:
            return JobExecutionResult(
                job_id=job_id,
                success=False,
                error=str(e),
            )

    def get_job_info(self, job_id: str) -> JobInfo | None:
        """
        Get information about a job.

        Args:
            job_id: ID of the job

        Returns:
            JobInfo or None if not found
        """
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobInfo]:
        """
        List all scheduled jobs.

        Returns:
            List of JobInfo objects
        """
        return list(self._jobs.values())

    def get_status_summary(self) -> dict[str, Any]:
        """
        Get a comprehensive status summary.

        Returns:
            Dictionary with status information
        """
        return {
            "daemon": {
                "status": self._status.value,
                "is_running": self.is_running,
                "started_at": (
                    self._stats.started_at.isoformat()
                    if self._stats.started_at
                    else None
                ),
            },
            "stats": self._stats.model_dump(),
            "jobs": {
                job_id: {
                    "handler": info.handler,
                    "cron": info.cron,
                    "status": info.status.value,
                    "next_run": (info.next_run.isoformat() if info.next_run else None),
                    "last_run": (info.last_run.isoformat() if info.last_run else None),
                    "total_runs": info.total_runs,
                    "success_rate": info.success_rate,
                }
                for job_id, info in self._jobs.items()
            },
            "running_executions": len(self._running_executions),
        }

    async def wait_until_stopped(self) -> None:
        """
        Wait until the daemon is stopped.

        Useful for running the daemon in the foreground.
        """
        await self._shutdown_event.wait()

    async def __aenter__(self) -> SchedulerDaemon:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SchedulerDaemon("
            f"status={self._status.value}, "
            f"jobs={self._stats.total_jobs}, "
            f"running={len(self._running_executions)})"
        )


async def run_daemon(
    config_path: str | None = None,
    foreground: bool = True,
) -> None:
    """
    Run the scheduler daemon.

    Args:
        config_path: Optional path to configuration file
        foreground: If True, run in foreground (block until stopped)

    Example:
        >>> asyncio.run(run_daemon())
    """
    config = load_config(config_path) if config_path else None
    daemon = SchedulerDaemon(config=config)

    async with daemon:
        if foreground:
            print("Scheduler daemon running. Press Ctrl+C to stop.")
            await daemon.wait_until_stopped()


def main() -> None:
    """CLI entry point for the scheduler daemon."""
    import argparse

    parser = argparse.ArgumentParser(description="Autoflow Scheduler Daemon")
    parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="Run as background daemon",
    )
    args = parser.parse_args()

    if args.daemon:
        # TODO: Implement true daemonization with proper PID file handling
        print("Background daemon mode not yet implemented")
        sys.exit(1)

    try:
        asyncio.run(run_daemon(config_path=args.config))
    except KeyboardInterrupt:
        print("\nScheduler daemon stopped.")


if __name__ == "__main__":
    main()
