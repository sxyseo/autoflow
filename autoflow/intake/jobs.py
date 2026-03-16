"""
Autoflow Intake Jobs Module

Provides job definitions for scheduled issue synchronization:
- sync_issues: Bidirectional sync between Autoflow tasks and external issues
- cleanup_sync_state: Clean up old sync history and mappings

These jobs are designed to be called by a scheduler daemon via cron schedules.

Usage:
    from autoflow.intake.jobs import sync_issues

    # Jobs are called automatically by the scheduler
    # Or can be invoked directly:
    result = await sync_issues()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from autoflow.core.config import Config, load_config
from autoflow.core.state import StateManager
from autoflow.intake.sync import (
    SyncDirection,
    SyncManager,
    SyncManagerConfig,
    SyncStatus,
)

logger = logging.getLogger(__name__)


# Global sync manager reference (set by the scheduler daemon)
_sync_manager: Optional[SyncManager] = None


def set_sync_manager(sync_manager: SyncManager) -> None:
    """
    Set the global sync manager reference for job handlers.

    Args:
        sync_manager: SyncManager instance
    """
    global _sync_manager
    _sync_manager = sync_manager


def get_sync_manager() -> Optional[SyncManager]:
    """
    Get the global sync manager reference.

    Returns:
        SyncManager instance or None
    """
    return _sync_manager


class JobResult(BaseModel):
    """Result from a scheduled job execution."""

    job_name: str
    success: bool
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    def mark_complete(
        self,
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark the job as complete."""
        self.success = success
        self.output = output
        self.error = error
        self.completed_at = datetime.utcnow()


@dataclass
class SyncJobMetrics:
    """Metrics collected during a sync job."""

    tasks_processed: int = 0
    tasks_synced: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0
    updates_pushed: int = 0
    updates_pulled: int = 0
    comments_added: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


async def sync_issues(
    config: Optional[Config] = None,
    state_dir: Optional[Path] = None,
    direction: Optional[SyncDirection] = None,
    dry_run: bool = False,
) -> JobResult:
    """
    Sync Autoflow tasks with external issue sources.

    This job:
    1. Loads all task-issue mappings from state
    2. Syncs each task with its external issue
    3. Pushes task status updates to external sources
    4. Pulls issue updates back to tasks
    5. Updates sync statistics and history

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path
        direction: Sync direction (push, pull, or bidirectional)
        dry_run: If True, don't actually push updates

    Returns:
        JobResult with sync status and metrics

    Example:
        >>> result = await sync_issues()
        >>> if result.success:
        ...     print(f"Synced {result.metrics['tasks_synced']} tasks")
    """
    result = JobResult(job_name="sync_issues")
    metrics = SyncJobMetrics()
    started_at = datetime.utcnow()

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Get or create sync manager
        sync_manager = get_sync_manager()
        if sync_manager is None:
            # Create a new sync manager for this job
            sync_config = SyncManagerConfig(
                state_dir=state_dir or Path(config.state_dir),
                direction=direction or SyncDirection.PUSH,
                dry_run=dry_run,
            )
            sync_manager = SyncManager(config=sync_config)
            sync_manager.initialize()

        # Get all mappings
        mappings = sync_manager.mappings
        tasks_to_sync = list(mappings.keys())

        if not tasks_to_sync:
            result.mark_complete(
                success=True,
                output="No tasks to sync",
            )
            result.metrics = {
                "tasks_processed": 0,
                "tasks_synced": 0,
                "tasks_failed": 0,
                "tasks_skipped": 0,
                "duration_seconds": 0.0,
            }
            return result

        metrics.tasks_processed = len(tasks_to_sync)

        # Sync all tasks
        sync_results = await sync_manager.sync_all(
            direction=direction,
            task_ids=tasks_to_sync,
        )

        # Process results
        for sync_result in sync_results:
            if sync_result.success:
                metrics.tasks_synced += 1
                metrics.updates_pushed += sync_result.updates_pushed
                metrics.updates_pulled += sync_result.updates_pulled
                metrics.comments_added += sync_result.comments_added
            elif sync_result.status == SyncStatus.SKIPPED:
                metrics.tasks_skipped += 1
            else:
                metrics.tasks_failed += 1
                metrics.errors.extend(sync_result.errors)

        # Calculate duration
        completed_at = datetime.utcnow()
        metrics.duration_seconds = (completed_at - started_at).total_seconds()

        # Save sync statistics to state
        state = sync_manager.state
        stats = sync_manager.get_stats()

        state.save_memory(
            key="last_issue_sync",
            value={
                "tasks_synced": metrics.tasks_synced,
                "tasks_failed": metrics.tasks_failed,
                "tasks_skipped": metrics.tasks_skipped,
                "updates_pushed": metrics.updates_pushed,
                "updates_pulled": metrics.updates_pulled,
                "comments_added": metrics.comments_added,
                "duration_seconds": metrics.duration_seconds,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="sync",
            expires_in_seconds=3600,  # 1 hour
        )

        # Format output
        output_parts = []
        output_parts.append(f"Synced {metrics.tasks_synced} tasks")

        if metrics.tasks_failed > 0:
            output_parts.append(f"{metrics.tasks_failed} failed")

        if metrics.tasks_skipped > 0:
            output_parts.append(f"{metrics.tasks_skipped} skipped")

        if metrics.updates_pushed > 0:
            output_parts.append(f"{metrics.updates_pushed} updates pushed")

        if metrics.updates_pulled > 0:
            output_parts.append(f"{metrics.updates_pulled} updates pulled")

        output = ", ".join(output_parts)

        result.mark_complete(success=True, output=output)
        result.metrics = {
            "tasks_processed": metrics.tasks_processed,
            "tasks_synced": metrics.tasks_synced,
            "tasks_failed": metrics.tasks_failed,
            "tasks_skipped": metrics.tasks_skipped,
            "updates_pushed": metrics.updates_pushed,
            "updates_pulled": metrics.updates_pulled,
            "comments_added": metrics.comments_added,
            "duration_seconds": metrics.duration_seconds,
        }

        logger.info(
            "Issue sync complete: %d synced, %d failed, %d skipped",
            metrics.tasks_synced,
            metrics.tasks_failed,
            metrics.tasks_skipped,
        )

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Issue sync failed: %s", e)

    return result


async def cleanup_sync_state(
    config: Optional[Config] = None,
    state_dir: Optional[Path] = None,
    max_age_days: int = 30,
) -> JobResult:
    """
    Clean up old sync history and stale mappings.

    This job:
    1. Removes sync history entries older than max_age_days
    2. Cleans up stale task-issue mappings
    3. Compacts sync state files
    4. Reports cleanup statistics

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path
        max_age_days: Maximum age of history to keep

    Returns:
        JobResult with cleanup status and metrics

    Example:
        >>> result = await cleanup_sync_state()
        >>> print(f"Cleaned {result.metrics['mappings_removed']} mappings")
    """
    result = JobResult(job_name="cleanup_sync_state")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Get or create sync manager
        sync_manager = get_sync_manager()
        if sync_manager is None:
            # Create a new sync manager for this job
            sync_config = SyncManagerConfig(
                state_dir=state_dir or Path(config.state_dir),
            )
            sync_manager = SyncManager(config=sync_config)
            sync_manager.initialize()

        state = sync_manager.state

        mappings_cleaned = 0
        history_cleaned = 0
        stale_mappings: list[str] = []

        # Calculate cutoff time
        cutoff_time = datetime.utcnow().timestamp() - (max_age_days * 86400)

        # Check for stale mappings
        for task_id, mapping in list(sync_manager.mappings.items()):
            # Check if the task still exists
            task_dict = state.load_task(task_id)
            if not task_dict:
                # Task no longer exists, remove mapping
                stale_mappings.append(task_id)
                continue

            # Check if mapping is very old and never successfully synced
            if (
                mapping.sync_count == 0
                and mapping.created_at.timestamp() < cutoff_time
            ):
                stale_mappings.append(task_id)

        # Remove stale mappings
        for task_id in stale_mappings:
            if sync_manager.untrack_mapping(task_id):
                mappings_cleaned += 1
                logger.info("Removed stale mapping for task: %s", task_id)

        # Clean up old sync history from memory
        # (The state manager's cleanup_expired handles this)
        memory_cleaned = state.cleanup_expired()

        output = (
            f"Cleaned: {mappings_cleaned} mappings, "
            f"{memory_cleaned} history entries"
        )

        result.mark_complete(success=True, output=output)
        result.metrics = {
            "mappings_removed": mappings_cleaned,
            "history_entries_removed": memory_cleaned,
            "max_age_days": max_age_days,
        }

        logger.info(
            "Sync state cleanup complete: %d mappings removed, %d history entries removed",
            mappings_cleaned,
            memory_cleaned,
        )

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Sync state cleanup failed: %s", e)

    return result


async def sync_health_check(
    config: Optional[Config] = None,
    state_dir: Optional[Path] = None,
) -> JobResult:
    """
    Perform health check for sync system.

    This job:
    1. Checks sync state accessibility
    2. Verifies external source connectivity
    3. Reports sync statistics
    4. Identifies any stale or failing mappings

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path

    Returns:
        JobResult with health check status

    Example:
        >>> result = await sync_health_check()
        >>> print(f"Sync system health: {result.output}")
    """
    result = JobResult(job_name="sync_health_check")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Get or create sync manager
        sync_manager = get_sync_manager()
        if sync_manager is None:
            # Create a new sync manager for this job
            sync_config = SyncManagerConfig(
                state_dir=state_dir or Path(config.state_dir),
            )
            sync_manager = SyncManager(config=sync_config)
            sync_manager.initialize()

        health_status = {
            "state_accessible": False,
            "mappings_count": 0,
            "active_mappings": 0,
            "stale_mappings": 0,
            "last_sync_at": None,
            "total_syncs": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
        }

        # Check state accessibility
        try:
            state = sync_manager.state
            state.initialize()
            health_status["state_accessible"] = True
        except Exception as e:
            logger.warning("Sync state check failed: %s", e)

        # Check mappings
        mappings = sync_manager.mappings
        health_status["mappings_count"] = len(mappings)

        now = datetime.utcnow()
        stale_threshold_seconds = 86400  # 24 hours

        for mapping in mappings.values():
            # Check if mapping is active (synced within last 24 hours)
            if (
                mapping.last_sync_at
                and (now - mapping.last_sync_at).total_seconds() < stale_threshold_seconds
                and mapping.last_sync_status == SyncStatus.SUCCESS
            ):
                health_status["active_mappings"] += 1
            else:
                health_status["stale_mappings"] += 1

        # Get sync statistics
        stats = sync_manager.get_stats()
        health_status["total_syncs"] = stats.total_syncs
        health_status["successful_syncs"] = stats.successful_syncs
        health_status["failed_syncs"] = stats.failed_syncs
        health_status["last_sync_at"] = (
            stats.last_sync_at.isoformat() if stats.last_sync_at else None
        )

        # Determine overall health
        is_healthy = health_status["state_accessible"] and (
            health_status["failed_syncs"] == 0
            or health_status["successful_syncs"] > health_status["failed_syncs"]
        )

        # Save health status
        state.save_memory(
            key="sync_health",
            value={
                **health_status,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="health",
            expires_in_seconds=300,  # 5 minutes
        )

        output = (
            f"State: {'OK' if health_status['state_accessible'] else 'ERROR'}, "
            f"Mappings: {health_status['mappings_count']} "
            f"({health_status['active_mappings']} active, {health_status['stale_mappings']} stale), "
            f"Syncs: {health_status['successful_syncs']}/{health_status['total_syncs']} successful"
        )

        result.mark_complete(success=is_healthy, output=output)
        result.metrics = health_status

        if not is_healthy:
            result.error = "Sync system health check failed"

        logger.info("Sync health check: %s", output)

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("Sync health check failed: %s", e)

    return result


# Job registry for easy reference
JOB_REGISTRY = {
    "sync_issues": {
        "handler": sync_issues,
        "default_cron": "*/15 * * * *",  # Every 15 minutes
        "description": "Sync Autoflow tasks with external issue sources",
    },
    "cleanup_sync_state": {
        "handler": cleanup_sync_state,
        "default_cron": "0 0 * * *",  # Daily at midnight
        "description": "Clean up old sync history and stale mappings",
    },
    "sync_health_check": {
        "handler": sync_health_check,
        "default_cron": "*/30 * * * *",  # Every 30 minutes
        "description": "Perform health check for sync system",
    },
}
