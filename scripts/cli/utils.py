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
from typing import Any, Callable

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


def spec_dir(slug: str) -> Path:
    """
    Get the directory path for a spec.

    Args:
        slug: Spec slug identifier

    Returns:
        Path to the spec directory
    """
    if not validate_slug_safe(slug):
        raise SystemExit(f"invalid spec slug: {slug}")
    return SPECS_DIR / slug


def spec_files(slug: str) -> dict[str, Path]:
    """
    Get all file paths associated with a spec.

    Args:
        slug: Spec slug identifier

    Returns:
        Dictionary containing paths to all spec-related files:
        - dir: Spec directory path
        - spec: Spec markdown file
        - metadata: Metadata JSON file
        - handoff: Handoff markdown file
        - handoffs_dir: Handoffs directory
        - review_state: Review state JSON file
        - events: Events JSONL file
        - qa_fix_request: QA fix request markdown file
        - qa_fix_request_json: QA fix request JSON file
    """
    directory = spec_dir(slug)
    return {
        "dir": directory,
        "spec": directory / "spec.md",
        "metadata": directory / "metadata.json",
        "handoff": directory / "handoff.md",
        "handoffs_dir": directory / "handoffs",
        "review_state": directory / REVIEW_STATE_FILE,
        "events": directory / EVENTS_FILE,
        "qa_fix_request": directory / QA_FIX_REQUEST_FILE,
        "qa_fix_request_json": directory / QA_FIX_REQUEST_JSON_FILE,
    }


def worktree_path(spec_slug: str, repository: str | None = None) -> Path:
    """
    Get the worktree path for a spec.

    Args:
        spec_slug: Spec slug identifier
        repository: Optional repository ID for multi-repo worktrees

    Returns:
        Path to the worktree directory

    Raises:
        SystemExit: If the spec slug is invalid
    """
    if not validate_slug_safe(spec_slug):
        raise SystemExit(f"invalid spec slug: {spec_slug}")
    if repository:
        return WORKTREES_DIR / repository / spec_slug
    return WORKTREES_DIR / spec_slug


def worktree_branch(spec_slug: str) -> str:
    """
    Get the git branch name for a spec's worktree.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Branch name for the worktree (format: codex/{slugified_spec_slug})
    """
    return f"codex/{slugify(spec_slug)}"


def load_spec_metadata(spec_slug: str) -> dict[str, Any]:
    """
    Load metadata for a spec.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Dictionary containing spec metadata

    Raises:
        SystemExit: If the spec does not exist
    """
    path = spec_files(spec_slug)["metadata"]
    if not path.exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    return read_json(path)


def save_spec_metadata(spec_slug: str, metadata: dict[str, Any]) -> Path:
    """
    Save metadata for a spec.

    Updates the updated_at timestamp before saving.

    Args:
        spec_slug: Spec slug identifier
        metadata: Metadata dictionary to save

    Returns:
        Path to the metadata file that was written
    """
    metadata["updated_at"] = now_stamp()
    path = spec_files(spec_slug)["metadata"]
    write_json(path, metadata)
    return path


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


# Task file management functions

def task_file(spec_slug: str) -> Path:
    """
    Get the task file path for a spec.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Path to the task JSON file
    """
    if not validate_slug_safe(spec_slug):
        raise SystemExit(f"invalid spec slug: {spec_slug}")
    return TASKS_DIR / f"{spec_slug}.json"


# Task metadata cache for performance optimization

_tasks_metadata_cache: dict[str, dict[str, Any]] = {}
_cache_loaded_task_specs: set[str] = set()


def _populate_tasks_cache(spec_slug: str) -> None:
    """Load task metadata for a specific spec_slug into the cache.

    This implements lazy-loading: tasks are only loaded from disk when needed.
    Subsequent calls for the same spec_slug will use the cached data (O(1) lookup).

    Opportunistic Caching:
        Since we must scan all task files to find tasks for the requested spec,
        we opportunistically cache tasks for ALL specs encountered during the scan.
        This means the first call for any spec effectively caches tasks for all specs,
        making subsequent calls for other specs essentially free (O(1) lookup).

    Cache Invalidation:
        If the spec is already in _cache_loaded_task_specs, we skip the filesystem scan
        entirely and return immediately. This ensures that after the first load,
        all subsequent calls are pure memory lookups.

    Args:
        spec_slug: The spec identifier to load tasks for.
    """
    global _tasks_metadata_cache, _cache_loaded_task_specs

    # Skip if this spec has already been loaded (cache hit)
    if spec_slug in _cache_loaded_task_specs:
        return

    # Ensure the spec has an entry in the cache
    if spec_slug not in _tasks_metadata_cache:
        _tasks_metadata_cache[spec_slug] = {}

    # Load tasks from filesystem for this spec
    # Note: We must scan all task files to find tasks matching this spec
    if not TASKS_DIR.exists():
        _cache_loaded_task_specs.add(spec_slug)
        return

    # First pass: discover all specs and collect their task data
    # This enables opportunistic caching of all specs in one scan
    spec_tasks = {}
    for task_file_path in sorted(TASKS_DIR.iterdir()):
        if not task_file_path.is_file() or not task_file_path.suffix == ".json":
            continue
        # Extract spec_slug from filename (e.g., "my-spec.json" -> "my-spec")
        file_spec = task_file_path.stem
        if file_spec:
            task_data = read_json(task_file_path)
            if task_data:
                spec_tasks[file_spec] = task_data

    # Second pass: add all discovered tasks to cache
    # This implements opportunistic caching for all specs encountered
    for discovered_spec, tasks in spec_tasks.items():
        _tasks_metadata_cache[discovered_spec] = tasks
        _cache_loaded_task_specs.add(discovered_spec)


def invalidate_tasks_cache() -> None:
    """Invalidate the task metadata cache."""
    global _tasks_metadata_cache, _cache_loaded_task_specs
    _tasks_metadata_cache.clear()
    _cache_loaded_task_specs.clear()


def load_tasks(spec_slug: str) -> dict[str, Any]:
    """
    Load the tasks file for a spec using a lazy-loaded cache.

    Reads and parses the tasks JSON file containing all tasks, their status,
    and metadata. Exits with an error if the tasks file doesn't exist.

    Cache Behavior:
        This function uses an in-memory cache indexed by spec_slug to avoid
        repeated disk I/O. On first call for a spec_slug, it loads the tasks
        from disk. Subsequent calls return the cached data directly from memory.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Tasks dictionary with the following structure:
        - tasks: List of task dictionaries, each containing:
            - id: Unique task identifier (str)
            - title: Task title (str)
            - status: Task status from VALID_TASK_STATUSES (str)
            - ...additional task metadata
        - ...other top-level keys

    Raises:
        SystemExit: If the tasks file doesn't exist
    """
    global _tasks_metadata_cache, _cache_loaded_task_specs

    _populate_tasks_cache(spec_slug)
    if spec_slug in _cache_loaded_task_specs:
        return _tasks_metadata_cache.get(spec_slug, {})

    path = task_file(spec_slug)
    if not path.exists():
        raise SystemExit(f"missing task file: {path}")
    tasks_data = read_json(path)
    _tasks_metadata_cache[spec_slug] = tasks_data
    _cache_loaded_task_specs.add(spec_slug)
    return tasks_data


def save_tasks(
    spec_slug: str,
    data: dict[str, Any],
    *,
    reason: str = "task_state_updated",
    sync_review_state_callback: Callable[[str, str], dict[str, Any]] | None = None,
) -> None:
    """
    Save task data for a spec and optionally synchronize review state.

    Updates the task data with a timestamp, writes it to the task file,
    invalidates the cache, and optionally triggers review state synchronization
    via a callback function. The reason parameter allows tracking why the task
    state was updated.

    Args:
        spec_slug: Slug identifier for the spec
        data: Task data dictionary to save
        reason: Optional reason for task state update (default: "task_state_updated")
        sync_review_state_callback: Optional callback to sync review state after saving.
                                     If provided, called with (spec_slug, reason).
    """
    data["updated_at"] = now_stamp()
    write_json(task_file(spec_slug), data)
    invalidate_tasks_cache()
    if sync_review_state_callback:
        sync_review_state_callback(spec_slug, reason=reason)


# Run metadata cache for performance optimization

_run_metadata_cache: dict[str, list[dict[str, Any]]] = {}
_cache_loaded_specs: set[str] = set()


def _populate_run_cache_for_spec(spec_slug: str) -> None:
    """Load run metadata for a specific spec_slug into the cache.

    This implements lazy-loading: runs are only loaded from disk when needed.
    Subsequent calls for the same spec_slug will use the cached data (O(1) lookup).

    Opportunistic Caching:
        Since we must scan all run directories to find runs for the requested spec,
        we opportunistically cache runs for ALL specs encountered during the scan.
        This means the first call for any spec effectively caches runs for all specs,
        making subsequent calls for other specs essentially free (O(1) lookup).

    Cache Invalidation:
        If the spec is already in _cache_loaded_specs, we skip the filesystem scan
        entirely and return immediately. This ensures that after the first load,
        all subsequent calls are pure memory lookups.

    Args:
        spec_slug: The spec identifier to load runs for.
    """
    global _run_metadata_cache, _cache_loaded_specs

    # Skip if this spec has already been loaded (cache hit)
    if spec_slug in _cache_loaded_specs:
        return

    # Ensure the spec has an entry in the cache
    if spec_slug not in _run_metadata_cache:
        _run_metadata_cache[spec_slug] = []

    # Load runs from filesystem for this spec
    # Note: We must scan all directories to find runs matching this spec
    if not RUNS_DIR.exists():
        _cache_loaded_specs.add(spec_slug)
        return

    # First pass: discover all specs and collect their run IDs
    # This enables opportunistic caching of all specs in one scan
    spec_runs = {}
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            metadata = read_json(metadata_path)
            run_spec = metadata.get("spec", "")
            if run_spec:
                if run_spec not in spec_runs:
                    spec_runs[run_spec] = []
                spec_runs[run_spec].append(metadata)

    # Second pass: add all discovered runs to cache
    # This implements opportunistic caching for all specs encountered
    for discovered_spec, runs in spec_runs.items():
        if discovered_spec not in _run_metadata_cache:
            _run_metadata_cache[discovered_spec] = []
        _run_metadata_cache[discovered_spec].extend(runs)
        _cache_loaded_specs.add(discovered_spec)


def _populate_run_cache() -> None:
    """Populate the run metadata cache from the filesystem for all specs.

    This is the non-lazy version that loads all runs at once.
    Prefer using _populate_run_cache_for_spec() for lazy-loading.
    """
    global _run_metadata_cache, _cache_loaded_specs

    # Load all specs that haven't been loaded yet
    if not RUNS_DIR.exists():
        return

    # First, discover all spec_slugs
    all_specs = set()
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            metadata = read_json(metadata_path)
            spec_slug = metadata.get("spec", "")
            if spec_slug:
                all_specs.add(spec_slug)

    # Load each spec that hasn't been loaded yet
    for spec_slug in all_specs:
        _populate_run_cache_for_spec(spec_slug)


def invalidate_run_cache() -> None:
    """Invalidate the run metadata cache.

    Call this function whenever runs are created, modified, or deleted to ensure
    the cache remains consistent with the filesystem state. This is a simple but
    correct approach: we clear all cached data, and it will be reloaded on demand.

    Cache Invalidation Strategy:
        - Simple: clear all cached data (not selective invalidation)
        - Safe: ensures cache consistency after any run modification
        - Lazy: data is reloaded on next access (not immediately)
        - Called by: create_run_record() after creating new run directories

    Note: While invalidating the entire cache may seem aggressive, it's the
    correct approach because:
        1. Run creation is relatively rare (not a hot path)
        2. Cache rebuild is lazy (amortized cost)
        3. Simplicity avoids complex invalidation bugs
        4. Performance impact is minimal (cache rebuilds are fast)
    """
    global _run_metadata_cache, _cache_loaded_specs
    _run_metadata_cache.clear()
    _cache_loaded_specs.clear()


def run_metadata_path(run_id: str) -> Path:
    """
    Get the path to a run's metadata file.

    Args:
        run_id: Unique identifier for the run

    Returns:
        Path to the run.json metadata file for the run
    """
    return RUNS_DIR / run_id / "run.json"


def load_run_metadata(run_id: str) -> dict[str, Any]:
    """
    Load metadata for a run.

    Args:
        run_id: Unique identifier for the run

    Returns:
        Dictionary containing run metadata

    Raises:
        SystemExit: If the run does not exist
    """
    path = run_metadata_path(run_id)
    if not path.exists():
        raise SystemExit(f"unknown run: {run_id}")
    return read_json(path)


def write_run_metadata(run_id: str, metadata: dict[str, Any]) -> None:
    """
    Write metadata for a run.

    Updates the updated_at timestamp before saving and invalidates the cache.

    Args:
        run_id: Unique identifier for the run
        metadata: Metadata dictionary to save
    """
    metadata["updated_at"] = now_stamp()
    write_json(run_metadata_path(run_id), metadata)
    invalidate_run_cache()


def run_last_activity(metadata: dict[str, Any]) -> datetime | None:
    """
    Get the last activity timestamp from run metadata.

    Checks multiple timestamp fields in order of priority:
    - heartbeat_at: Most recent heartbeat from the run
    - updated_at: Last metadata update
    - created_at: Initial run creation time

    Args:
        metadata: Run metadata dictionary

    Returns:
        Datetime of last activity, or None if no timestamp found
    """
    for field in ("heartbeat_at", "updated_at", "created_at"):
        parsed = parse_stamp(metadata.get(field, ""))
        if parsed:
            return parsed
    return None


def run_stale_reason(
    metadata: dict[str, Any],
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> str:
    """
    Determine if a run is stale and return the reason.

    A run is considered stale if:
    - It has an active status (created/running)
    - Its tmux session no longer exists
    - No heartbeat has been received within the stale_after_seconds window

    Args:
        metadata: Run metadata dictionary
        stale_after_seconds: Seconds of inactivity before considering stale

    Returns:
        String reason for staleness:
        - "": Not stale
        - "tmux_session_missing": Tmux session no longer exists
        - "missing_heartbeat": No heartbeat timestamp found
        - "heartbeat_expired": Heartbeat too old
    """
    if metadata.get("status") not in RUN_LEASE_ACTIVE_STATUSES:
        return ""
    session_name = metadata.get("tmux_session", "")
    if session_name and not tmux_session_exists(session_name):
        return "tmux_session_missing"
    last_activity = run_last_activity(metadata)
    if not last_activity:
        return "missing_heartbeat"
    age_seconds = (now_utc() - last_activity).total_seconds()
    if age_seconds > stale_after_seconds:
        return "heartbeat_expired"
    return ""


def run_is_stale(
    metadata: dict[str, Any],
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> bool:
    """
    Check if a run is stale.

    Args:
        metadata: Run metadata dictionary
        stale_after_seconds: Seconds of inactivity before considering stale

    Returns:
        True if the run is stale, False otherwise
    """
    return bool(run_stale_reason(metadata, stale_after_seconds=stale_after_seconds))


def stale_runs_for_spec(
    spec_slug: str,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> list[dict[str, Any]]:
    """
    Get all stale runs for a spec.

    Args:
        spec_slug: Spec slug identifier
        stale_after_seconds: Seconds of inactivity before considering stale

    Returns:
        List of stale run metadata dictionaries
    """
    _populate_run_cache_for_spec(spec_slug)
    return [
        item
        for item in _run_metadata_cache.get(spec_slug, [])
        if run_is_stale(item, stale_after_seconds=stale_after_seconds)
    ]
