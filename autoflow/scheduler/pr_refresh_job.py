"""
PR Refresh Job - Scheduled job for automatic PR refresh

This module provides the refresh_prs job handler that:
1. Detects stale PRs (base branch has changed)
2. Attempts to rebase PR branches onto updated base
3. Handles conflicts with automatic resolution
4. Updates PR state to track progress

Usage:
    from autoflow.scheduler.pr_refresh_job import refresh_prs

    # Job is called automatically by the scheduler
    result = await refresh_prs()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from autoflow.core.config import Config, load_config
from autoflow.core.state import StateManager
from autoflow.git.conflict_resolver import (
    ConflictResolver,
    ConflictResolutionType,
)
from autoflow.git.operations import GitOperations, create_git_operations
from autoflow.git.pr_manager import PRManager, PRRefreshStatus
from autoflow.scheduler.jobs import JobResult

logger = logging.getLogger(__name__)


def _generate_conflict_task_id(
    pr_number: int,
    index: int = 0,
) -> str:
    """
    Generate a unique task ID for a conflict fix task.

    Args:
        pr_number: Pull request number
        index: Index of the conflict task for this PR

    Returns:
        Unique task ID string
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"fix-conflict-pr{pr_number}-{timestamp}-{index:03d}"


def _create_conflict_fix_task(
    pr_number: int,
    branch: str,
    base_branch: str,
    conflict_context: dict[str, any],
    task_id: str,
) -> dict[str, any]:
    """
    Create a fix task dictionary from conflict context.

    Args:
        pr_number: Pull request number
        branch: PR branch name
        base_branch: Base branch name
        conflict_context: Conflict context from resolver
        task_id: Unique task identifier

    Returns:
        Task dictionary
    """
    # Determine priority based on number of conflicts
    total_conflicts = conflict_context.get("total_conflicts", 0)
    if total_conflicts > 10:
        priority = "critical"
    elif total_conflicts > 5:
        priority = "high"
    elif total_conflicts > 1:
        priority = "medium"
    else:
        priority = "low"

    # Build description
    conflicted_files = conflict_context.get("conflicted_files", [])
    files_str = ", ".join(conflicted_files[:3])
    if len(conflicted_files) > 3:
        files_str += f" and {len(conflicted_files) - 3} more"

    task = {
        "task_id": task_id,
        "type": "fix",
        "status": "pending",
        "priority": priority,
        "agent": "implementation-runner",
        "created_at": datetime.now().isoformat(),
        "title": f"Resolve merge conflicts in PR #{pr_number}",
        "description": (
            f"PR #{pr_number} ({branch} → {base_branch}) has "
            f"{total_conflicts} conflict(s) in {len(conflicted_files)} file(s): {files_str}"
        ),
        "conflict": {
            "pr_number": pr_number,
            "branch": branch,
            "base_branch": base_branch,
            "total_conflicts": total_conflicts,
            "conflicted_files": conflicted_files,
            "file_details": conflict_context.get("file_details", {}),
            "suggested_approach": conflict_context.get("suggested_approach", "standard_manual"),
        },
        "actions": [
            {
                "type": "resolve_conflicts",
                "description": "Resolve merge conflicts in the affected files",
                "conflicted_files": conflicted_files,
            },
            {
                "type": "verify",
                "description": "Run tests and checks to verify the fix",
                "command": "python scripts/run_tests.py",
            },
        ],
    }

    return task


async def refresh_prs(
    config: Optional[Config] = None,
    state_dir: Optional[Path] = None,
    repo_path: Optional[Path] = None,
) -> JobResult:
    """
    Refresh stale pull requests by rebasing onto updated base branches.

    This job:
    1. Detects PRs that need refresh (base branch has changed)
    2. For each stale PR:
       - Updates PR state to REFRESHING
       - Switches to the PR branch
       - Attempts to rebase onto the base branch
       - If conflicts occur, attempts automatic resolution
       - Updates PR state to REFRESHED, CONFLICT_DETECTED, or FAILED
    3. Records metrics about the refresh operation

    Args:
        config: Optional configuration (loaded if not provided)
        state_dir: Optional state directory path
        repo_path: Optional repository path (defaults to current directory)

    Returns:
        JobResult with refresh status and metrics

    Example:
        >>> result = await refresh_prs()
        >>> if result.success:
        ...     print(f"Refreshed {result.metrics['prs_refreshed']} PRs")
    """
    result = JobResult(job_name="refresh_prs")

    try:
        # Load configuration if needed
        if config is None:
            config = load_config()

        # Determine repository path
        if repo_path is None:
            repo_path = Path.cwd()

        # Initialize PR manager
        pr_manager = PRManager(
            repo_path=repo_path,
            state_dir=state_dir or Path(config.state_dir),
        )

        # Initialize git operations
        git_ops = create_git_operations(str(repo_path))

        # Get stale PRs
        stale_prs = pr_manager.detect_stale_prs()

        if not stale_prs:
            result.mark_complete(
                success=True,
                output="No PRs need refresh",
            )
            result.metrics = {
                "prs_checked": 0,
                "prs_refreshed": 0,
                "prs_failed": 0,
                "prs_with_conflicts": 0,
                "fix_tasks_created": 0,
            }
            logger.info("No PRs need refresh")
            return result

        # Refresh each stale PR
        prs_refreshed = 0
        prs_failed = 0
        prs_with_conflicts = 0
        fix_tasks_created = 0

        for pr_state in stale_prs:
            pr_number = pr_state.pr_number
            branch = pr_state.branch
            base_branch = pr_state.base_branch

            try:
                logger.info(
                    "Refreshing PR #%d: %s -> %s",
                    pr_number,
                    branch,
                    base_branch,
                )

                # Mark PR as refreshing
                pr_manager.update_pr_refresh_state(
                    pr_number,
                    PRRefreshStatus.REFRESHING,
                )

                # Switch to PR branch
                branch_info = git_ops.get_branch_info(branch)
                if not branch_info:
                    logger.warning(
                        "Branch %s not found for PR #%d",
                        branch,
                        pr_number,
                    )
                    pr_manager.update_pr_refresh_state(
                        pr_number,
                        PRRefreshStatus.FAILED,
                        error=f"Branch {branch} not found",
                    )
                    prs_failed += 1
                    continue

                # Checkout the branch
                git_ops.checkout_branch(branch)

                # Get current base branch commit
                base_info = git_ops.get_branch_info(base_branch)
                if not base_info or not base_info.commit_sha:
                    logger.warning(
                        "Could not get HEAD for base branch %s of PR #%d",
                        base_branch,
                        pr_number,
                    )
                    pr_manager.update_pr_refresh_state(
                        pr_number,
                        PRRefreshStatus.FAILED,
                        error=f"Could not get base branch {base_branch}",
                    )
                    prs_failed += 1
                    continue

                base_commit = base_info.commit_sha

                # Attempt rebase with conflict detection
                rebase_result = git_ops.rebase_with_conflict_detection(
                    branch=branch,
                    new_base=base_branch,
                )

                if not rebase_result.success:
                    if rebase_result.has_conflicts:
                        # Conflicts detected - attempt automatic resolution
                        logger.info(
                            "Conflicts detected in PR #%d, attempting resolution",
                            pr_number,
                        )

                        resolver = ConflictResolver(repo_path=repo_path)

                        # Try theirs-full strategy (accept base branch changes)
                        conflict_result = resolver.attempt_resolution(
                            strategy=ConflictResolutionType.THEIRS_FULL,
                        )

                        if conflict_result.success:
                            # Continue rebase after resolution
                            try:
                                git_ops.rebase_continue()
                                pr_manager.update_pr_refresh_state(
                                    pr_number,
                                    PRRefreshStatus.REFRESHED,
                                    last_commit=base_commit,
                                )
                                prs_refreshed += 1
                                logger.info(
                                    "PR #%d refreshed after conflict resolution",
                                    pr_number,
                                )
                            except Exception as e:
                                # Resolution failed, abort - create fix task
                                git_ops.rebase_abort()

                                # Extract conflict context for fix task
                                try:
                                    conflict_context = resolver.extract_conflict_context()
                                    task_id = _generate_conflict_task_id(pr_number)
                                    task = _create_conflict_fix_task(
                                        pr_number=pr_number,
                                        branch=branch,
                                        base_branch=base_branch,
                                        conflict_context=conflict_context,
                                        task_id=task_id,
                                    )

                                    # Save fix task
                                    state = StateManager(state_dir or Path(config.state_dir))
                                    state.save_task(task_id, task)
                                    fix_tasks_created += 1

                                    logger.info(
                                        "Created fix task %s for PR #%d conflicts",
                                        task_id,
                                        pr_number,
                                    )

                                    pr_manager.update_pr_refresh_state(
                                        pr_number,
                                        PRRefreshStatus.CONFLICT_DETECTED,
                                        error=f"Rebase continue failed: {e}. Fix task created: {task_id}",
                                    )
                                except Exception as task_error:
                                    logger.error(
                                        "Failed to create fix task for PR #%d: %s",
                                        pr_number,
                                        task_error,
                                    )
                                    pr_manager.update_pr_refresh_state(
                                        pr_number,
                                        PRRefreshStatus.CONFLICT_DETECTED,
                                        error=str(e),
                                    )

                                prs_with_conflicts += 1
                                logger.warning(
                                    "Failed to resolve conflicts in PR #%d: %s",
                                    pr_number,
                                    e,
                                )
                        else:
                            # Automatic resolution failed - create fix task
                            git_ops.rebase_abort()

                            # Extract conflict context for fix task
                            try:
                                conflict_context = resolver.extract_conflict_context()
                                task_id = _generate_conflict_task_id(pr_number)
                                task = _create_conflict_fix_task(
                                    pr_number=pr_number,
                                    branch=branch,
                                    base_branch=base_branch,
                                    conflict_context=conflict_context,
                                    task_id=task_id,
                                )

                                # Save fix task
                                state = StateManager(state_dir or Path(config.state_dir))
                                state.save_task(task_id, task)
                                fix_tasks_created += 1

                                logger.info(
                                    "Created fix task %s for PR #%d conflicts",
                                    task_id,
                                    pr_number,
                                )

                                pr_manager.update_pr_refresh_state(
                                    pr_number,
                                    PRRefreshStatus.CONFLICT_DETECTED,
                                    error=f"Automatic conflict resolution failed. Fix task created: {task_id}",
                                )
                            except Exception as task_error:
                                logger.error(
                                    "Failed to create fix task for PR #%d: %s",
                                    pr_number,
                                    task_error,
                                )
                                pr_manager.update_pr_refresh_state(
                                    pr_number,
                                    PRRefreshStatus.CONFLICT_DETECTED,
                                    error="Automatic conflict resolution failed",
                                )

                            prs_with_conflicts += 1
                            logger.warning(
                                "Automatic conflict resolution failed for PR #%d",
                                pr_number,
                            )
                    else:
                        # Rebase failed for other reason
                        pr_manager.update_pr_refresh_state(
                            pr_number,
                            PRRefreshStatus.FAILED,
                            error=rebase_result.error or "Rebase failed",
                        )
                        prs_failed += 1
                        logger.warning(
                            "Rebase failed for PR #%d: %s",
                            pr_number,
                            rebase_result.error,
                        )
                else:
                    # Rebase succeeded
                    pr_manager.update_pr_refresh_state(
                        pr_number,
                        PRRefreshStatus.REFRESHED,
                        last_commit=base_commit,
                    )
                    prs_refreshed += 1
                    logger.info("PR #%d refreshed successfully", pr_number)

            except Exception as e:
                logger.error(
                    "Failed to refresh PR #%d: %s",
                    pr_number,
                    e,
                )
                try:
                    pr_manager.update_pr_refresh_state(
                        pr_number,
                        PRRefreshStatus.FAILED,
                        error=str(e),
                    )
                except Exception:
                    pass
                prs_failed += 1

        # Prepare output
        output_parts = [
            f"Checked {len(stale_prs)} PRs",
            f"{prs_refreshed} refreshed",
        ]
        if prs_with_conflicts > 0:
            output_parts.append(f"{prs_with_conflicts} with conflicts")
        if fix_tasks_created > 0:
            output_parts.append(f"{fix_tasks_created} fix tasks created")
        if prs_failed > 0:
            output_parts.append(f"{prs_failed} failed")

        output = ", ".join(output_parts)

        # Save refresh results to memory
        state = StateManager(state_dir or Path(config.state_dir))
        state.save_memory(
            key="last_pr_refresh",
            value={
                "prs_checked": len(stale_prs),
                "prs_refreshed": prs_refreshed,
                "prs_with_conflicts": prs_with_conflicts,
                "prs_failed": prs_failed,
                "timestamp": datetime.utcnow().isoformat(),
            },
            category="pr_refresh",
            expires_in_seconds=1800,  # 30 minutes
        )

        result.mark_complete(
            success=prs_failed == 0,
            output=output,
        )
        result.metrics = {
            "prs_checked": len(stale_prs),
            "prs_refreshed": prs_refreshed,
            "prs_failed": prs_failed,
            "prs_with_conflicts": prs_with_conflicts,
            "fix_tasks_created": fix_tasks_created,
        }

        logger.info(
            "PR refresh complete: %d refreshed, %d conflicts, %d failed, %d fix tasks created",
            prs_refreshed,
            prs_with_conflicts,
            prs_failed,
            fix_tasks_created,
        )

    except Exception as e:
        result.mark_complete(
            success=False,
            error=str(e),
        )
        logger.error("PR refresh job failed: %s", e)

    return result
