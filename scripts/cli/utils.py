"""
Autoflow CLI Scripts - Utility Functions

Provides helper functions for state management, path handling,
output formatting, and command execution used across CLI scripts.

Usage:
    from scripts.cli.utils import (
        STATE_DIR,
        SPECS_DIR,
        now_utc,
        now_stamp,
        slugify,
        run_cmd,
        write_json,
        read_json,
    )

    # Get current UTC time
    current = now_utc()

    # Create a URL-friendly slug
    slug = slugify("My Feature Name")

    # Run a command
    result = run_cmd(["git", "status"])

    # Write JSON data
    write_json(Path("output.json"), {"data": "value"})
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoflow.core.sanitization import sanitize_dict, sanitize_value

# Directory paths
ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / ".autoflow"
SPECS_DIR = STATE_DIR / "specs"
TASKS_DIR = STATE_DIR / "tasks"
RUNS_DIR = STATE_DIR / "runs"
LOGS_DIR = STATE_DIR / "logs"
WORKTREES_DIR = STATE_DIR / "worktrees" / "tasks"
MEMORY_DIR = STATE_DIR / "memory"
STRATEGY_MEMORY_DIR = MEMORY_DIR / "strategy"
REPOSITORIES_DIR = STATE_DIR / "repositories"
DEPENDENCIES_DIR = STATE_DIR / "dependencies"

# File paths
DISCOVERY_FILE = STATE_DIR / "discovered_agents.json"
SYSTEM_CONFIG_FILE = STATE_DIR / "system.json"
SYSTEM_CONFIG_TEMPLATE = ROOT / "config" / "system.example.json"
AGENTS_FILE = STATE_DIR / "agents.json"
BMAD_DIR = ROOT / "templates" / "bmad"

# Filename constants
REVIEW_STATE_FILE = "review_state.json"
EVENTS_FILE = "events.jsonl"
QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
QA_FIX_REQUEST_JSON_FILE = "QA_FIX_REQUEST.json"
AGENT_RESULT_FILE = "agent_result.json"

# Status constants
VALID_TASK_STATUSES = {
    "todo",
    "in_progress",
    "in_review",
    "needs_changes",
    "blocked",
    "done",
}
RUN_RESULTS = {"success", "needs_changes", "blocked", "failed"}
INACTIVE_RUN_STATUSES = {
    "completed",
    "abandoned",
    "cancelled",
    "cleaned",
    "recovered",
    "stale",
}
RUN_LEASE_ACTIVE_STATUSES = {"created", "running"}

# Default timing constants
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
DEFAULT_STALE_AFTER_SECONDS = 120


def now_utc() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        Current datetime in UTC timezone
    """
    return datetime.now(UTC)


def now_stamp() -> str:
    """
    Get current UTC timestamp in ISO 8601 format.

    Returns:
        Timestamp string in format YYYYMMDDTHHMMSSZ
    """
    return now_utc().strftime("%Y%m%dT%H%M%SZ")


def parse_stamp(value: str) -> datetime | None:
    """
    Parse an Autoflow timestamp into a UTC datetime.

    Args:
        value: Timestamp string in format YYYYMMDDTHHMMSSZ

    Returns:
        Parsed datetime in UTC, or None if parsing fails
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def slugify(value: str) -> str:
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


def validate_slug_safe(slug: str) -> bool:
    """
    Validate that a slug does not contain path traversal patterns.

    Returns True if the slug is safe, False if it contains dangerous patterns
    that could lead to path traversal attacks.

    Checks for:
    - '..' sequences (parent directory)
    - './' sequences (current directory)
    - Absolute paths starting with '/'
    - Backslash separators (Windows paths)
    - Null bytes

    Args:
        slug: The slug string to validate

    Returns:
        bool: True if safe, False if dangerous
    """
    # Check for null bytes
    if "\0" in slug:
        return False

    # Check for parent directory patterns
    if ".." in slug:
        return False

    # Check for current directory patterns
    if "./" in slug:
        return False

    # Check for absolute paths
    if slug.startswith("/"):
        return False

    # Check for Windows path separators
    if "\\" in slug:
        return False

    # Check for drive letters (Windows absolute paths like C:)
    if len(slug) >= 2 and slug[1] == ":":
        return False

    return True


def write_json(path: Path, data: Any) -> None:
    """
    Write data to a JSON file.

    Sanitizes sensitive data before writing to prevent information disclosure.
    Creates parent directories if they don't exist. Writes with indentation
    and ensures ASCII encoding.

    Args:
        path: Path to the JSON file to write
        data: Data to serialize as JSON
    """
    resolved_path = path.resolve()
    preserve_runtime_config = resolved_path in {
        SYSTEM_CONFIG_FILE.resolve(),
        AGENTS_FILE.resolve(),
    } or (
        resolved_path.name == "run.json"
        and resolved_path.parent.parent == RUNS_DIR.resolve()
    )
    sanitized_data = (
        data
        if preserve_runtime_config
        else (
            sanitize_dict(data)
            if isinstance(data, dict)
            else sanitize_value(data) if isinstance(data, list) else data
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sanitized_data, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def print_json(data: Any) -> None:
    """
    Print JSON data to stdout with sanitization.

    Sanitizes sensitive data before printing to prevent information disclosure.

    Args:
        data: JSON-serializable data to print
    """
    sanitized_data = (
        sanitize_dict(data)
        if isinstance(data, dict)
        else sanitize_value(data) if isinstance(data, list) else data
    )
    print(json.dumps(sanitized_data, indent=2, ensure_ascii=True))


def read_json(path: Path) -> Any:
    """
    Read and parse a JSON file.

    Args:
        path: Path to the JSON file to read

    Returns:
        Parsed JSON data as Python objects

    Raises:
        json.JSONDecodeError: If the file contains invalid JSON
    """
    return json.loads(path.read_text(encoding="utf-8"))


def run_cmd(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command as a subprocess.

    Args:
        args: Command arguments to execute
        cwd: Working directory for the command (defaults to ROOT if None)
        check: Whether to raise exception on non-zero exit code

    Returns:
        Completed process with stdout and stderr captured

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def tmux_session_exists(session_name: str) -> bool:
    """
    Return True when a tmux session exists.

    Args:
        session_name: Name of the tmux session to check

    Returns:
        True if the session exists, False otherwise
    """
    if not session_name or not shutil.which("tmux"):
        return False
    result = run_cmd(["tmux", "has-session", "-t", session_name], check=False)
    return result.returncode == 0


def ensure_state() -> None:
    """
    Ensure all required Autoflow state directories exist.

    Creates the following directories if they don't exist:
    - State directory (.autoflow)
    - Specs directory
    - Tasks directory
    - Runs directory
    - Logs directory
    - Worktrees directory
    - Memory directory
    - Strategy memory directory
    """
    for path in [
        STATE_DIR,
        SPECS_DIR,
        TASKS_DIR,
        RUNS_DIR,
        LOGS_DIR,
        WORKTREES_DIR,
        MEMORY_DIR,
        STRATEGY_MEMORY_DIR,
        REPOSITORIES_DIR,
        DEPENDENCIES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
