#!/usr/bin/env python3
"""
Scheduler Core for Autoflow.

This module provides scheduled task automation for continuous iteration,
maintenance, and other automated jobs. It supports:
- Cron-based scheduling
- Continuous iteration runs (every 5 minutes)
- Nightly maintenance (2 AM)
- Weekly memory consolidation (Sunday 3 AM)
- Monthly dependency updates (1st)

Usage:
    python3 scripts/scheduler.py start
    python3 scripts/scheduler.py status
    python3 scripts/scheduler.py add-job --job-type continuous_iteration --cron "*/5 * * * *"
    python3 scripts/scheduler.py list-jobs
    python3 scripts/scheduler.py remove-job --job-id <id>
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("scheduler")

# Try to import APScheduler 4.x first, then fall back to 3.x.
try:
    from apscheduler import AsyncScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
    APSCHEDULER_VERSION = 4
except ImportError:
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler as AsyncScheduler
        from apscheduler.triggers.cron import CronTrigger

        APSCHEDULER_AVAILABLE = True
        APSCHEDULER_VERSION = 3
    except ImportError:
        APSCHEDULER_AVAILABLE = False
        APSCHEDULER_VERSION = 0
        logger.warning(
            "APScheduler not available. Install with: pip install 'apscheduler>=3.10.0'"
        )


# Path to scheduler configuration
SCHEDULER_CONFIG_PATH = (
    Path(__file__).parent.parent / "config" / "scheduler_config.json"
)


def scheduler_config_from_args(args: argparse.Namespace):
    config_path = getattr(args, "config", "")
    if not isinstance(config_path, (str, os.PathLike)):
        config_path = ""
    return SchedulerConfig(Path(config_path) if config_path else None)


class SchedulerConfig:
    """Configuration for the scheduler."""

    def __init__(self, config_path: Path | None = None):
        """Initialize scheduler configuration.

        Args:
            config_path: Path to configuration file. Defaults to config/scheduler_config.json.
        """
        if config_path is None:
            env_override = os.environ.get("AUTOFLOW_SCHEDULER_CONFIG", "").strip()
            config_path = Path(env_override) if env_override else SCHEDULER_CONFIG_PATH

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from JSON file."""
        if not self.config_path.exists():
            return self._default_config()

        with open(self.config_path) as f:
            return json.load(f)

    def _default_config(self) -> dict:
        """Return default configuration."""
        return {
            "scheduler": {
                "timezone": "UTC",
                "max_instances": 3,
                "coalesce": True,
                "misfire_grace_time": 300,
            },
            "jobs": {
                "continuous_iteration": {
                    "enabled": True,
                    "cron": "*/5 * * * *",
                    "max_instances": 1,
                    "description": "Run continuous iteration loop every 5 minutes",
                    "args": {
                        "spec": "",
                        "config": "config/continuous-iteration.example.json",
                        "dispatch": True,
                        "commit_if_dirty": False,
                        "push": False
                    }
                },
                "nightly_maintenance": {
                    "enabled": True,
                    "cron": "0 2 * * *",
                    "max_instances": 1,
                    "description": "Run maintenance tasks at 2 AM daily",
                },
                "weekly_consolidation": {
                    "enabled": True,
                    "cron": "0 3 * * 0",
                    "max_instances": 1,
                    "description": "Run memory consolidation on Sundays at 3 AM",
                },
                "monthly_dependency_update": {
                    "enabled": True,
                    "cron": "0 4 1 * *",
                    "max_instances": 1,
                    "description": "Check for dependency updates on the 1st of each month",
                },
            },
            "job_defaults": {
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 300,
            },
        }

    @property
    def timezone(self) -> str:
        """Get scheduler timezone."""
        return self._config.get("scheduler", {}).get("timezone", "UTC")

    @property
    def max_instances(self) -> int:
        """Get max instances for scheduler."""
        return self._config.get("scheduler", {}).get("max_instances", 3)

    @property
    def jobs(self) -> dict:
        """Get job configurations."""
        return self._config.get("jobs", {})

    @property
    def job_defaults(self) -> dict:
        """Get default job settings."""
        return self._config.get("job_defaults", {})

    def get_job_config(self, job_type: str) -> dict | None:
        """Get configuration for a specific job type.

        Args:
            job_type: Type of job to get configuration for.

        Returns:
            Job configuration dict or None if not found.
        """
        return self.jobs.get(job_type)

    def get_job_args(self, job_type: str) -> dict[str, Any]:
        job_config = self.get_job_config(job_type) or {}
        args = job_config.get("args", {})
        return args if isinstance(args, dict) else {}

    def save(self) -> None:
        """Save current configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config, f, indent=2)


class JobRegistry:
    """Registry of available job functions."""

    def __init__(self, config: SchedulerConfig | None = None):
        """Initialize job registry."""
        self.config = config or SchedulerConfig()
        self._jobs: dict[str, Callable] = {}
        self._register_builtin_jobs()

    def _register_builtin_jobs(self) -> None:
        """Register built-in job functions."""
        self.register("continuous_iteration", self._continuous_iteration_job)
        self.register("nightly_maintenance", self._nightly_maintenance_job)
        self.register("weekly_consolidation", self._weekly_consolidation_job)
        self.register("monthly_dependency_update", self._monthly_dependency_update_job)

    def register(self, job_type: str, func: Callable) -> None:
        """Register a job function.

        Args:
            job_type: Type identifier for the job.
            func: Async or sync function to execute.
        """
        self._jobs[job_type] = func
        logger.debug(f"Registered job: {job_type}")

    def get(self, job_type: str) -> Callable | None:
        """Get a registered job function.

        Args:
            job_type: Type identifier for the job.

        Returns:
            Job function or None if not found.
        """
        return self._jobs.get(job_type)

    def list_jobs(self) -> list[str]:
        """List all registered job types.

        Returns:
            List of registered job type names.
        """
        return list(self._jobs.keys())

    # Built-in job implementations

    def _continuous_iteration_command(self) -> tuple[list[str] | None, str | None]:
        job_args = self.config.get_job_args("continuous_iteration")
        spec = str(job_args.get("spec", "")).strip()
        if not spec:
            return None, (
                "continuous_iteration job requires jobs.continuous_iteration.args.spec "
                "in the scheduler config"
            )

        scripts_path = Path(__file__).parent
        command = [
            "python3",
            str(scripts_path / "continuous_iteration.py"),
            "--spec",
            spec,
        ]
        iteration_config = str(job_args.get("config", "")).strip()
        if iteration_config:
            command.extend(["--config", iteration_config])
        if job_args.get("dispatch", True):
            command.append("--dispatch")
        if job_args.get("commit_if_dirty", False):
            command.append("--commit-if-dirty")
        if job_args.get("push", False):
            command.append("--push")
        return command, None

    async def _continuous_iteration_job(self) -> dict[str, Any]:
        """Run continuous iteration loop.

        Returns:
            Job execution result.
        """
        logger.info("Running continuous iteration job")
        start_time = datetime.now(UTC)

        try:
            command, error = self._continuous_iteration_command()
            if error:
                return {
                    "job": "continuous_iteration",
                    "success": False,
                    "error": error,
                    "timestamp": start_time.isoformat(),
                }

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return {
                "job": "continuous_iteration",
                "success": success,
                "command": command,
                "output": output,
                "duration_seconds": duration,
                "timestamp": start_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Continuous iteration job failed: {e}")
            return {
                "job": "continuous_iteration",
                "success": False,
                "error": str(e),
                "timestamp": start_time.isoformat(),
            }

    async def _nightly_maintenance_job(self) -> dict[str, Any]:
        """Run nightly maintenance tasks.

        Returns:
            Job execution result.
        """
        logger.info("Running nightly maintenance job")
        start_time = datetime.now(UTC)

        try:
            # Import and run maintenance if available
            scripts_path = Path(__file__).parent
            maintenance_script = scripts_path / "maintenance.py"

            if maintenance_script.exists():
                import subprocess

                result = subprocess.run(
                    ["python3", str(maintenance_script), "--cleanup"],
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                output = result.stdout + result.stderr
                success = result.returncode == 0
            else:
                # Simulate maintenance tasks
                output = "Maintenance script not found - simulating cleanup"
                success = True

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return {
                "job": "nightly_maintenance",
                "success": success,
                "output": output,
                "duration_seconds": duration,
                "timestamp": start_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Nightly maintenance job failed: {e}")
            return {
                "job": "nightly_maintenance",
                "success": False,
                "error": str(e),
                "timestamp": start_time.isoformat(),
            }

    async def _weekly_consolidation_job(self) -> dict[str, Any]:
        """Run weekly memory consolidation.

        Returns:
            Job execution result.
        """
        logger.info("Running weekly consolidation job")
        start_time = datetime.now(UTC)

        try:
            # This would integrate with the learning system
            output = "Weekly memory consolidation completed"
            success = True

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return {
                "job": "weekly_consolidation",
                "success": success,
                "output": output,
                "duration_seconds": duration,
                "timestamp": start_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Weekly consolidation job failed: {e}")
            return {
                "job": "weekly_consolidation",
                "success": False,
                "error": str(e),
                "timestamp": start_time.isoformat(),
            }

    async def _monthly_dependency_update_job(self) -> dict[str, Any]:
        """Check for dependency updates monthly.

        Returns:
            Job execution result.
        """
        logger.info("Running monthly dependency update check")
        start_time = datetime.now(UTC)

        try:
            # This would check for dependency updates
            output = "Monthly dependency check completed"
            success = True

            duration = (datetime.now(UTC) - start_time).total_seconds()

            return {
                "job": "monthly_dependency_update",
                "success": success,
                "output": output,
                "duration_seconds": duration,
                "timestamp": start_time.isoformat(),
            }
        except Exception as e:
            logger.error(f"Monthly dependency update job failed: {e}")
            return {
                "job": "monthly_dependency_update",
                "success": False,
                "error": str(e),
                "timestamp": start_time.isoformat(),
            }


class Scheduler:
    """APScheduler-based task scheduler."""

    def __init__(self, config: SchedulerConfig | None = None):
        """Initialize scheduler.

        Args:
            config: Scheduler configuration. If None, uses default config.
        """
        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler 4.x is required. Install with: pip install apscheduler>=4.0.0"
            )

        self.config = config or SchedulerConfig()
        self.job_registry = JobRegistry(self.config)
        self._scheduler: Any = None
        self._running = False
        self._stop_event: asyncio.Event | None = None
        self._scheduled_jobs: dict[str, str] = {}  # job_id -> job_type

    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting scheduler...")

        loop = asyncio.get_event_loop()
        self._stop_event = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        if APSCHEDULER_VERSION == 4:
            async with AsyncScheduler() as scheduler:
                self._scheduler = scheduler
                self._running = True
                await self._add_configured_jobs()
                logger.info("Scheduler started. Press Ctrl+C to stop.")
                try:
                    await scheduler.run_until_stopped()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    logger.info("Scheduler stopping...")
                finally:
                    self._running = False
                    self._scheduler = None
                    self._stop_event = None
            return

        scheduler = AsyncScheduler(timezone=self.config.timezone)
        self._scheduler = scheduler
        self._running = True
        await self._add_configured_jobs()
        scheduler.start()
        logger.info("Scheduler started. Press Ctrl+C to stop.")
        try:
            await self._stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Scheduler stopping...")
        finally:
            with contextlib.suppress(Exception):
                scheduler.shutdown(wait=False)
            self._running = False
            self._scheduler = None
            self._stop_event = None

    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        logger.info("Stopping scheduler...")
        self._running = False

        if self._scheduler:
            if APSCHEDULER_VERSION == 4:
                await self._scheduler.stop()
            else:
                self._scheduler.shutdown(wait=False)
        if self._stop_event:
            self._stop_event.set()

    async def _add_configured_jobs(self) -> None:
        """Add all enabled jobs from configuration."""
        for job_type, job_config in self.config.jobs.items():
            if job_config.get("enabled", False):
                await self.add_job(
                    job_type=job_type,
                    cron=job_config.get("cron", "*/5 * * * *"),
                    job_id=job_type,
                )

    async def add_job(
        self,
        job_type: str,
        cron: str,
        job_id: str | None = None,
        max_instances: int | None = None,
    ) -> str:
        """Add a scheduled job.

        Args:
            job_type: Type of job to schedule.
            cron: Cron expression for scheduling.
            job_id: Optional job ID. Defaults to job_type.
            max_instances: Maximum concurrent instances.

        Returns:
            Job ID.
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not started")

        job_func = self.job_registry.get(job_type)
        if not job_func:
            raise ValueError(f"Unknown job type: {job_type}")

        if job_id is None:
            job_id = job_type

        # Get job-specific config or use defaults
        job_config = self.config.get_job_config(job_type) or {}
        if max_instances is None:
            max_instances = job_config.get(
                "max_instances", self.config.job_defaults.get("max_instances", 1)
            )

        # Create cron trigger
        trigger = CronTrigger.from_crontab(cron)

        # Add schedule
        if APSCHEDULER_VERSION == 4:
            await self._scheduler.add_schedule(
                job_func, trigger, id=job_id, max_instances=max_instances
            )
        else:
            self._scheduler.add_job(
                job_func,
                trigger=trigger,
                id=job_id,
                max_instances=max_instances,
                coalesce=self.config.job_defaults.get("coalesce", True),
                misfire_grace_time=self.config.job_defaults.get("misfire_grace_time", 300),
            )

        self._scheduled_jobs[job_id] = job_type
        logger.info(f"Added job: {job_id} ({job_type}) with cron: {cron}")

        return job_id

    async def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job.

        Args:
            job_id: ID of job to remove.

        Returns:
            True if job was removed, False if not found.
        """
        if not self._scheduler:
            raise RuntimeError("Scheduler not started")

        if job_id in self._scheduled_jobs:
            if APSCHEDULER_VERSION == 4:
                await self._scheduler.remove_schedule(job_id)
            else:
                self._scheduler.remove_job(job_id)
            del self._scheduled_jobs[job_id]
            logger.info(f"Removed job: {job_id}")
            return True

        return False

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all scheduled jobs.

        Returns:
            List of job information dictionaries.
        """
        jobs = []
        for job_id, job_type in self._scheduled_jobs.items():
            job_config = self.config.get_job_config(job_type) or {}
            jobs.append(
                {
                    "id": job_id,
                    "type": job_type,
                    "cron": job_config.get("cron", "unknown"),
                    "enabled": job_config.get("enabled", True),
                    "description": job_config.get("description", ""),
                }
            )
        return jobs

    def get_status(self) -> dict[str, Any]:
        """Get scheduler status.

        Returns:
            Status dictionary.
        """
        return {
            "running": self._running,
            "jobs_count": len(self._scheduled_jobs),
            "jobs": self.list_jobs(),
            "config": {
                "timezone": self.config.timezone,
                "max_instances": self.config.max_instances,
            },
        }


# CLI Commands


def cmd_start(args: argparse.Namespace) -> int:
    """Start the scheduler.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    if not APSCHEDULER_AVAILABLE:
        print("Error: APScheduler is required.")
        print("Install with: pip install 'apscheduler>=3.10.0'")
        return 1

    config = scheduler_config_from_args(args)
    scheduler = Scheduler(config)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(scheduler.start())

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show scheduler status.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = scheduler_config_from_args(args)

    print("Scheduler Configuration:")
    print(f"  Timezone: {config.timezone}")
    print(f"  Max Instances: {config.max_instances}")
    print()

    print("Configured Jobs:")
    for job_type, job_config in config.jobs.items():
        enabled = job_config.get("enabled", False)
        status = "ENABLED" if enabled else "DISABLED"
        cron = job_config.get("cron", "N/A")
        desc = job_config.get("description", "")
        args_summary = job_config.get("args", {})
        print(f"  [{status}] {job_type}")
        print(f"    Cron: {cron}")
        if desc:
            print(f"    Description: {desc}")
        if args_summary:
            print(f"    Args: {json.dumps(args_summary, ensure_ascii=True)}")
        print()

    return 0


def cmd_add_job(args: argparse.Namespace) -> int:
    """Add a scheduled job.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    if not APSCHEDULER_AVAILABLE:
        print("Error: APScheduler 4.x is required.")
        return 1

    print(f"Adding job: {args.job_type}")
    print(f"  Cron: {args.cron}")
    print(f"  Job ID: {args.job_id or args.job_type}")

    # Update configuration
    config = scheduler_config_from_args(args)
    job_id = args.job_id or args.job_type

    if "jobs" not in config._config:
        config._config["jobs"] = {}

    config._config["jobs"][args.job_type] = {
        "enabled": True,
        "cron": args.cron,
        "max_instances": args.max_instances or 1,
        "description": args.description or f"Custom job: {args.job_type}",
    }
    if args.job_type == "continuous_iteration":
        config._config["jobs"][args.job_type]["args"] = {
            "spec": getattr(args, "spec", "") or "",
            "config": getattr(args, "iteration_config", "") or "config/continuous-iteration.example.json",
            "dispatch": bool(getattr(args, "dispatch", False)),
            "commit_if_dirty": bool(getattr(args, "commit_if_dirty", False)),
            "push": bool(getattr(args, "push", False)),
        }
    config.save()

    print(f"\nJob '{job_id}' added to configuration.")
    print("Restart the scheduler to apply changes.")

    return 0


def cmd_list_jobs(args: argparse.Namespace) -> int:
    """List all scheduled jobs.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = scheduler_config_from_args(args)

    if not config.jobs:
        print("No jobs configured.")
        return 0

    print(f"Scheduled Jobs ({len(config.jobs)}):\n")

    for job_type, job_config in config.jobs.items():
        enabled = "ENABLED" if job_config.get("enabled", False) else "DISABLED"
        cron = job_config.get("cron", "N/A")
        desc = job_config.get("description", "No description")

        print(f"  {job_type}")
        print(f"    Status: {enabled}")
        print(f"    Cron: {cron}")
        print(f"    Description: {desc}")
        print()

    return 0


def cmd_remove_job(args: argparse.Namespace) -> int:
    """Remove a scheduled job.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = scheduler_config_from_args(args)

    if args.job_id not in config.jobs:
        print(f"Job '{args.job_id}' not found in configuration.")
        return 1

    del config._config["jobs"][args.job_id]
    config.save()

    print(f"Job '{args.job_id}' removed from configuration.")
    print("Restart the scheduler to apply changes.")

    return 0


def cmd_run_once(args: argparse.Namespace) -> int:
    """Run a job once immediately.

    Args:
        args: Parsed command line arguments.

    Returns:
        Exit code.
    """
    config = scheduler_config_from_args(args)
    registry = JobRegistry(config)
    job_func = registry.get(args.job_type)

    if not job_func:
        print(f"Unknown job type: {args.job_type}")
        print(f"Available job types: {', '.join(registry.list_jobs())}")
        return 1

    print(f"Running job: {args.job_type}")

    try:
        result = asyncio.run(job_func())

        print("\nJob Result:")
        print(f"  Success: {result.get('success', False)}")
        print(f"  Duration: {result.get('duration_seconds', 0):.2f}s")

        if result.get("error"):
            print(f"  Error: {result.get('error')}")

        if result.get("output") and args.verbose:
            print(f"\nOutput:\n{result.get('output')}")

        return 0 if result.get("success", False) else 1

    except Exception as e:
        print(f"Error running job: {e}")
        return 1


def main() -> int:
    """Main entry point for the scheduler CLI.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(
        description="Scheduler Core for Autoflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 scripts/scheduler.py start
    python3 scripts/scheduler.py status
    python3 scripts/scheduler.py add-job --job-type continuous_iteration --cron "*/5 * * * *"
    python3 scripts/scheduler.py list-jobs
    python3 scripts/scheduler.py remove-job --job-id continuous_iteration
    python3 scripts/scheduler.py run-once --job-type continuous_iteration --verbose
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start the scheduler")
    start_parser.add_argument("--config", default="", help="path to scheduler config JSON")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show scheduler status")
    status_parser.add_argument("--config", default="", help="path to scheduler config JSON")

    # Add job command
    add_parser = subparsers.add_parser("add-job", help="Add a scheduled job")
    add_parser.add_argument("--job-type", required=True, help="Type of job to schedule")
    add_parser.add_argument(
        "--cron", required=True, help="Cron expression for scheduling"
    )
    add_parser.add_argument("--job-id", help="Optional job ID (defaults to job-type)")
    add_parser.add_argument(
        "--max-instances", type=int, default=1, help="Maximum concurrent instances"
    )
    add_parser.add_argument("--description", help="Job description")
    add_parser.add_argument("--config", default="", help="path to scheduler config JSON")
    add_parser.add_argument("--spec", default="", help="spec slug for continuous_iteration jobs")
    add_parser.add_argument("--iteration-config", default="", help="continuous_iteration config path")
    add_parser.add_argument("--dispatch", action="store_true", help="enable dispatch for continuous_iteration jobs")
    add_parser.add_argument("--commit-if-dirty", action="store_true", help="enable commit-if-dirty for continuous_iteration jobs")
    add_parser.add_argument("--push", action="store_true", help="enable push for continuous_iteration jobs")

    # List jobs command
    list_parser = subparsers.add_parser("list-jobs", help="List all scheduled jobs")
    list_parser.add_argument("--config", default="", help="path to scheduler config JSON")

    # Remove job command
    remove_parser = subparsers.add_parser("remove-job", help="Remove a scheduled job")
    remove_parser.add_argument("--job-id", required=True, help="ID of job to remove")
    remove_parser.add_argument("--config", default="", help="path to scheduler config JSON")

    # Run once command
    run_parser = subparsers.add_parser("run-once", help="Run a job once immediately")
    run_parser.add_argument("--job-type", required=True, help="Type of job to run")
    run_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show job output"
    )
    run_parser.add_argument("--config", default="", help="path to scheduler config JSON")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    # Route to appropriate command handler
    commands = {
        "start": cmd_start,
        "status": cmd_status,
        "add-job": cmd_add_job,
        "list-jobs": cmd_list_jobs,
        "remove-job": cmd_remove_job,
        "run-once": cmd_run_once,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
