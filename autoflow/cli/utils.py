"""
Autoflow CLI - Utility Functions

Provides helper functions for state management, output formatting,
and async execution used across CLI commands.

Usage:
    from autoflow.cli.utils import (
        _get_state_manager,
        _print_json,
        _run_async,
        _format_datetime,
        _get_worktree_metadata,
        _get_review_state_metadata,
    )

    # Get state manager instance
    state_manager = _get_state_manager(config)

    # Print JSON output
    _print_json({"status": "ok", "data": [...]})

    # Run async coroutine synchronously
    result = _run_async(async_function())

    # Format datetime for display
    formatted = _format_datetime(datetime.now())

    # Get worktree metadata for a spec
    worktree = _get_worktree_metadata(spec_slug, config)

    # Get review state metadata for a spec
    review = _get_review_state_metadata(spec_slug, config)
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from autoflow.core.config import Config, get_state_dir
from autoflow.core.state import StateManager
from autoflow.utils.subprocess_helpers import run_cmd


def _get_state_manager(config: Config | None = None) -> StateManager:
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


def _format_datetime(dt: datetime | None) -> str:
    """Format a datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _slugify(value: str) -> str:
    """
    Convert a string to a URL-friendly slug.

    Converts to lowercase, replaces non-alphanumeric characters with hyphens,
    and removes consecutive hyphens.

    Args:
        value: Input string to convert

    Returns:
        URL-friendly slug string, or "spec" if result is empty
    """
    output = []
    for ch in value.lower():
        if ch.isalnum():
            output.append(ch)
        elif ch in {" ", "_", "-", "/", "."}:
            output.append("-")
    slug = "".join(output).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "spec"


def _read_json_or_default(path: Path, default: Any) -> Any:
    """
    Read a JSON file, returning a default value if the file doesn't exist or is invalid.

    This is a safe version of JSON reading that handles missing files and JSON parse
    errors by returning a provided default value instead of raising an exception.

    Args:
        path: Path to the JSON file to read
        default: Default value to return if file doesn't exist or is invalid JSON

    Returns:
        Parsed JSON data if file exists and is valid, otherwise the default value
    """
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _spec_dir(slug: str, state_dir: Path) -> Path:
    """
    Get the directory path for a spec.

    Args:
        slug: Spec slug identifier
        state_dir: Path to the state directory

    Returns:
        Path to the spec directory
    """
    return state_dir / "specs" / slug


def _worktree_path(spec_slug: str, state_dir: Path) -> Path:
    """
    Get the worktree path for a spec.

    Args:
        spec_slug: Spec slug identifier
        state_dir: Path to the state directory

    Returns:
        Path to the worktree directory
    """
    return state_dir / "worktrees" / "tasks" / spec_slug


def _worktree_branch(spec_slug: str) -> str:
    """
    Get the git branch name for a spec's worktree.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Branch name for the worktree (format: codex/{slugified_spec_slug})
    """
    return f"codex/{_slugify(spec_slug)}"


def _detect_base_branch() -> str:
    """
    Detect the git repository's base branch.

    Attempts to identify the primary branch by checking for common branch names
    (main, master) in order. Falls back to the current branch if neither is found,
    or defaults to "main" as a last resort.

    Returns:
        Name of the detected base branch ("main", "master", or current branch)
    """
    for branch in ["main", "master"]:
        result = run_cmd(["git", "rev-parse", "--verify", branch], check=False)
        if result.returncode == 0:
            return branch
    try:
        current = run_cmd(["git", "branch", "--show-current"])
        return current.stdout.strip() or "main"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "main"


def _get_worktree_metadata(spec_slug: str, config: Config | None = None) -> dict[str, Any]:
    """
    Get normalized worktree metadata for a spec.

    Loads the spec's metadata and normalizes the worktree information,
    including path, branch, and base branch. Resolves the actual worktree
    path by checking if the expected path exists.

    Args:
        spec_slug: Spec slug identifier
        config: Optional config object

    Returns:
        Dictionary containing worktree metadata with keys:
            - path: Resolved path to the worktree (empty string if not found)
            - branch: Branch name for the worktree
            - base_branch: Detected base branch name
    """
    state_dir = get_state_dir(config)
    spec_dir_path = _spec_dir(spec_slug, state_dir)
    metadata_path = spec_dir_path / "metadata.json"

    # Load spec metadata
    metadata = _read_json_or_default(metadata_path, {})
    worktree = dict(metadata.get("worktree", {}))

    # Get expected worktree path and current path from metadata
    expected_path = _worktree_path(spec_slug, state_dir)
    current_path = worktree.get("path", "")
    branch = worktree.get("branch", _worktree_branch(spec_slug))
    base_branch = worktree.get("base_branch", _detect_base_branch())

    # Resolve actual worktree path
    resolved_path = ""
    if expected_path.exists():
        resolved_path = str(expected_path)
    elif current_path:
        current = Path(current_path)
        if current.exists():
            resolved_path = str(current)

    return {
        "path": resolved_path,
        "branch": branch,
        "base_branch": base_branch,
    }


def _get_review_state_metadata(spec_slug: str, config: Config | None = None) -> dict[str, Any]:
    """
    Get review state metadata for a spec.

    Loads the review state from disk, returning a default state if the file
    doesn't exist or is invalid. The review state tracks approval status,
    reviewer information, and approval metadata.

    Args:
        spec_slug: Spec slug identifier
        config: Optional config object

    Returns:
        Review state dictionary with the following keys:
            - approved: Whether the review is approved (bool)
            - approved_by: Username of the approver (str)
            - approved_at: ISO timestamp of approval (str)
            - spec_hash: Hash of the spec at approval time (str)
            - review_count: Number of reviews performed (int)
            - invalidated_at: ISO timestamp of invalidation (str)
            - invalidated_reason: Reason for invalidation (str)
    """
    state_dir = get_state_dir(config)
    spec_dir_path = _spec_dir(spec_slug, state_dir)
    review_state_path = spec_dir_path / "review_state.json"

    default_state = {
        "approved": False,
        "approved_by": "",
        "approved_at": "",
        "spec_hash": "",
        "review_count": 0,
        "invalidated_at": "",
        "invalidated_reason": "",
    }

    return _read_json_or_default(review_state_path, default_state)
