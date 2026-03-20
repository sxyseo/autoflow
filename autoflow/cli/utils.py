"""
Autoflow CLI - Utility Functions

Provides helper functions for state management, output formatting,
and async execution used across CLI commands.

Usage:
    from autoflow.cli.utils import (
        _get_state_manager,
        _print_json,
        _run_async,
        _format_datetime
    )

    # Get state manager instance
    state_manager = _get_state_manager(config)

    # Print JSON output
    _print_json({"status": "ok", "data": [...]})

    # Run async coroutine synchronously
    result = _run_async(async_function())

    # Format datetime for display
    formatted = _format_datetime(datetime.now())
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
    """Convert a value into a branch-safe slug."""
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
    """Read JSON from path, returning default on missing or invalid files."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def _spec_dir(slug: str, state_dir: Path) -> Path:
    """Return the on-disk directory for a control-plane spec."""
    return state_dir / "specs" / slug


def _worktree_path(spec_slug: str, state_dir: Path) -> Path:
    """Return the expected worktree path for a spec."""
    return state_dir / "worktrees" / "tasks" / spec_slug


def _worktree_branch(spec_slug: str) -> str:
    """Return the expected git branch name for a spec worktree."""
    return f"codex/{_slugify(spec_slug)}"


def _detect_base_branch() -> str:
    """Best-effort detection of the repo's default branch."""
    for branch in ("main", "master"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return branch
    try:
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
        )
        branch = current.stdout.strip()
        if branch:
            return branch
    except OSError:
        pass
    return "main"


def _get_worktree_metadata(spec_slug: str, config: Config | None = None) -> dict[str, Any]:
    """Load normalized worktree metadata for a spec."""
    state_dir = get_state_dir(config)
    metadata_path = _spec_dir(spec_slug, state_dir) / "metadata.json"
    metadata = _read_json_or_default(metadata_path, {})
    worktree = dict(metadata.get("worktree", {}))
    expected_path = _worktree_path(spec_slug, state_dir)
    current_path = worktree.get("path", "")
    branch = worktree.get("branch", _worktree_branch(spec_slug))
    base_branch = worktree.get("base_branch", _detect_base_branch())

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
    """Load review metadata for a spec, falling back to defaults."""
    state_dir = get_state_dir(config)
    review_state_path = _spec_dir(spec_slug, state_dir) / "review_state.json"
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
