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

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
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


def detect_base_branch() -> str:
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
    current = run_cmd(["git", "branch", "--show-current"]).stdout.strip()
    return current or "main"


def normalize_worktree_metadata(spec_slug: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Normalize worktree metadata to ensure consistent structure.

    Updates the worktree path to use the expected location if it exists,
    otherwise preserves the current path. Ensures branch and base_branch
    fields are populated with defaults if missing.

    Args:
        spec_slug: Spec slug identifier
        metadata: Optional metadata dictionary to normalize (loads from disk if not provided)

    Returns:
        Normalized metadata dictionary with consistent worktree structure
    """
    payload = dict(metadata or load_spec_metadata(spec_slug))
    worktree = dict(payload.get("worktree", {}))
    expected = worktree_path(spec_slug)
    current_path = worktree.get("path", "")
    branch = worktree.get("branch", worktree_branch(spec_slug))
    base_branch = worktree.get("base_branch", detect_base_branch())
    resolved_path = ""
    if expected.exists():
        resolved_path = str(expected)
    elif current_path:
        current = Path(current_path)
        if current.exists():
            resolved_path = str(current)
    payload["worktree"] = {
        "path": resolved_path,
        "branch": branch,
        "base_branch": base_branch,
    }
    return payload


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


# ============================================================================
# Review State Helper Functions
# ============================================================================


def review_state_default() -> dict[str, Any]:
    """
    Get the default review state structure.

    Returns:
        Default review state dictionary with the following keys:
        - approved: Whether the review is approved (bool)
        - approved_by: Username of the approver (str)
        - approved_at: ISO timestamp of approval (str)
        - spec_hash: Hash of the spec at approval time (str)
        - review_count: Number of reviews performed (int)
        - feedback: List of feedback comments (list)
        - invalidated_at: ISO timestamp of invalidation (str)
        - invalidated_reason: Reason for invalidation (str)
    """
    return {
        "approved": False,
        "approved_by": "",
        "approved_at": "",
        "spec_hash": "",
        "review_count": 0,
        "feedback": [],
        "invalidated_at": "",
        "invalidated_reason": "",
    }


def load_review_state(spec_slug: str) -> dict[str, Any]:
    """
    Load the review state for a spec.

    Reads the review state from disk, returning a default state if the file
    doesn't exist or is invalid. The review state tracks approval status,
    reviewer information, and approval metadata.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Review state dictionary with the following keys:
        - approved: Whether the review is approved (bool)
        - approved_by: Username of the approver (str)
        - approved_at: ISO timestamp of approval (str)
        - spec_hash: Hash of the spec at approval time (str)
        - review_count: Number of reviews performed (int)
    """
    return read_json_or_default(spec_files(spec_slug)["review_state"], review_state_default())


def save_review_state(spec_slug: str, state: dict[str, Any]) -> None:
    """
    Save the review state for a spec.

    Persists the review state to disk as JSON. Creates parent directories
    if they don't exist. The review state tracks approval status, reviewer
    information, and approval metadata.

    Args:
        spec_slug: Spec slug identifier
        state: Review state dictionary containing:
            - approved: Whether the review is approved (bool)
            - approved_by: Username of the approver (str)
            - approved_at: ISO timestamp of approval (str)
            - spec_hash: Hash of the spec at approval time (str)
            - review_count: Number of reviews performed (int)
    """
    write_json(spec_files(spec_slug)["review_state"], state)


def compute_file_hash(path: Path) -> str:
    """
    Compute MD5 hash of a file's content.

    Reads the file as UTF-8 text and returns its MD5 hash as a hexadecimal string.
    Returns empty string if the file doesn't exist.

    Args:
        path: Path to the file to hash

    Returns:
        Hexadecimal MD5 hash string, or empty string if file doesn't exist
    """
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


def planning_contract(spec_slug: str) -> dict[str, Any]:
    """
    Generate a planning contract from task data.

    Extracts and structures task information needed for planning, including:
    - Task ID and title
    - Dependencies
    - Owner role
    - Acceptance criteria

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Dictionary containing list of tasks with planning-relevant fields
    """
    task_data = load_tasks(spec_slug)
    tasks = []
    for task in task_data.get("tasks", []):
        tasks.append(
            {
                "id": task["id"],
                "title": task["title"],
                "depends_on": task.get("depends_on", []),
                "owner_role": task["owner_role"],
                "acceptance_criteria": task.get("acceptance_criteria", []),
            }
        )
    return {"tasks": tasks}


def compute_spec_hash(spec_slug: str) -> str:
    """
    Compute a combined hash of spec content and planning contract.

    Generates a hash that combines:
    - MD5 hash of the spec.md file content
    - MD5 hash of the planning contract (JSON representation of tasks)

    The combined hash ensures that any change to either the spec content
    or the task structure will be detected.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Hexadecimal MD5 hash string combining spec and task hashes
    """
    files = spec_files(spec_slug)
    spec_hash = compute_file_hash(files["spec"])
    task_hash = hashlib.md5(
        json.dumps(planning_contract(spec_slug), sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    combined = f"{spec_hash}:{task_hash}"
    return hashlib.md5(combined.encode("utf-8"), usedforsecurity=False).hexdigest()


def record_event(spec_slug: str, event_type: str, payload: dict[str, Any]) -> None:
    """
    Record an event to the spec's event log.

    Events are stored as JSONL (one JSON object per line) in the events.jsonl file.
    Each event includes a timestamp, event type, and payload data.

    Args:
        spec_slug: Slug identifier for the spec
        event_type: Type of event being recorded (e.g., "task_started", "task_completed")
        payload: Event data as a dictionary

    Event Log Format:
        Each line is a JSON object with:
        {
            "at": "YYYYMMDDTHHMMSSZ",  # UTC timestamp
            "type": "event_type",       # Event type identifier
            "payload": {...}            # Event-specific data
        }
    """
    files = spec_files(spec_slug)
    files["events"].parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": now_stamp(),
        "type": event_type,
        "payload": payload,
    }
    with open(files["events"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def sync_review_state(spec_slug: str, reason: str = "planning_artifacts_changed") -> dict[str, Any]:
    """
    Synchronize review state with current spec hash.

    Checks if the spec has changed since approval. If the previously approved
    spec hash differs from the current hash, invalidates the approval and
    records the change as an event.

    Args:
        spec_slug: Slug identifier for the spec
        reason: Reason code for invalidation (default: "planning_artifacts_changed")

    Returns:
        Current review state dictionary, potentially updated with invalidation
    """
    state = load_review_state(spec_slug)
    if state.get("approved") and state.get("spec_hash") != compute_spec_hash(spec_slug):
        state["approved"] = False
        state["invalidated_at"] = now_stamp()
        state["invalidated_reason"] = reason
        save_review_state(spec_slug, state)
        record_event(spec_slug, "review.invalidated", {"reason": reason})
    return state


def review_status_summary(spec_slug: str) -> dict[str, Any]:
    """
    Generate a summary of review status for a spec.

    Synchronizes the review state to check for spec changes and computes
    a comprehensive summary including approval status, validity, timestamps,
    and feedback counts.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Dictionary containing review status summary with keys:
            - approved: Whether the spec is currently approved
            - valid: Whether approval is still valid (approved and hash matches)
            - approved_by: Username of approver
            - approved_at: Timestamp of approval
            - review_count: Number of reviews completed
            - feedback_count: Number of feedback items
            - spec_changed: Whether spec has changed since approval
            - invalidated_at: Timestamp when approval was invalidated
            - invalidated_reason: Reason for invalidation
    """
    state = sync_review_state(spec_slug)
    current_hash = compute_spec_hash(spec_slug)
    return {
        "approved": state.get("approved", False),
        "valid": bool(state.get("approved")) and state.get("spec_hash") == current_hash,
        "approved_by": state.get("approved_by", ""),
        "approved_at": state.get("approved_at", ""),
        "review_count": state.get("review_count", 0),
        "feedback_count": len(state.get("feedback", [])),
        "spec_changed": bool(state.get("spec_hash")) and state.get("spec_hash") != current_hash,
        "invalidated_at": state.get("invalidated_at", ""),
        "invalidated_reason": state.get("invalidated_reason", ""),
    }


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


# System configuration and utility functions

_system_config_cache: dict[str, Any] | None = None


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    Deep merges overlay into base, with overlay values taking precedence.
    When both base and overlay have a dict value for the same key,
    they are merged recursively instead of being replaced.

    Args:
        base: Base dictionary to merge into
        overlay: Dictionary with values to overlay on top of base

    Returns:
        A new dictionary with merged contents
    """
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_root_path(raw: str | Path) -> Path:
    """
    Resolve a path relative to the project root.

    Converts the input to a Path object. If the path is relative,
    it resolves it relative to the project ROOT directory.

    Args:
        raw: Path as string or Path object

    Returns:
        Absolute Path object
    """
    path = Path(raw)
    if not path.is_absolute():
        return ROOT / path
    if ".autoflow" in path.parts and not path.is_relative_to(ROOT):
        marker = path.parts.index(".autoflow")
        return STATE_DIR.joinpath(*path.parts[marker + 1 :])
    return path


def read_json_or_default(path: Path, default: Any) -> Any:
    """
    Read a JSON file, returning a default value if the file doesn't exist or is invalid.

    This is a safe version of read_json that handles missing files and JSON parse
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
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return default


def system_config_default() -> dict[str, Any]:
    """
    Get the default system configuration.

    Returns the default configuration from the system config template if it exists,
    otherwise returns a hardcoded default configuration.

    Returns:
        Default system configuration dictionary with the following top-level keys:
        - memory: Memory settings including enabled flag, auto_capture_run_results,
          global_file path, and spec_dir path (dict)
        - models: Model profile configurations with profiles for spec, implementation,
          and review tasks (dict)
        - tools: Tool profile configurations with profiles for different agent types (dict)
        - registry: Registry settings including acp_agents list (dict)
    """
    if SYSTEM_CONFIG_TEMPLATE.exists():
        return read_json_or_default(SYSTEM_CONFIG_TEMPLATE, {})
    return {
        "memory": {
            "enabled": True,
            "auto_capture_run_results": True,
            "global_file": str(MEMORY_DIR / "global.md"),
            "spec_dir": str(MEMORY_DIR / "specs"),
        },
        "models": {
            "profiles": {
                "spec": "gpt-5",
                "implementation": "gpt-5-codex",
                "review": "claude-sonnet-4-6",
            }
        },
        "tools": {
            "profiles": {
                "codex-default": [],
                "claude-review": ["Read", "Bash(git:*)"],
            }
        },
        "registry": {
            "acp_agents": []
        },
    }


def load_system_config() -> dict[str, Any]:
    """
    Load the system configuration from file or defaults.

    This function performs a multi-stage merge to combine:
    1. Base defaults with required structure
    2. Default system configuration (from template or hardcoded)
    3. Local system configuration from system.json (if it exists)

    The merge is done using deep_merge, so local values override defaults.

    Caching Behavior:
        This function uses an in-memory cache to avoid repeated disk I/O.
        On first call, it loads the config from disk and caches it.
        Subsequent calls return the cached value directly (O(1) lookup).
        Use invalidate_system_config_cache() to clear the cache after
        modifying system.json.

    Performance:
        - First call: O(n) filesystem read and JSON parsing
        - Subsequent calls: O(1) memory lookup
        - Typical speedup: 10-20x for repeated calls

    Returns:
        Merged system configuration dictionary with the following structure:
        - memory: Memory settings including default_scopes, enabled flag,
          auto_capture_run_results, global_file path, and spec_dir path (dict)
        - models: Model profile configurations with profiles for different tasks (dict)
        - tools: Tool profile configurations with profiles for different agent types (dict)
        - registry: Registry settings including acp_agents list (dict)
    """
    global _system_config_cache

    # Return cached value if available (cache hit)
    if _system_config_cache is not None:
        return _system_config_cache

    # Load from disk and cache the result
    config = system_config_default()
    if SYSTEM_CONFIG_FILE.exists():
        local = read_json_or_default(SYSTEM_CONFIG_FILE, {})
        config = deep_merge(config, local)
    _system_config_cache = deep_merge(
        {
            "memory": {"default_scopes": ["spec"]},
            "models": {"profiles": {}},
            "tools": {"profiles": {}},
            "registry": {"acp_agents": []},
        },
        config,
    )
    return _system_config_cache


def invalidate_system_config_cache() -> None:
    """
    Invalidate the system configuration cache.

    Call this after modifying system.json to ensure the next load
    reads from disk instead of returning stale cached data.
    """
    global _system_config_cache
    _system_config_cache = None


# Memory helper functions

def memory_file(scope: str, spec_slug: str | None = None) -> Path:
    """
    Resolve the path to a memory file based on scope and optional spec slug.

    Memory files store persistent information for Autoflow operations.
    The scope determines which memory file to return:
    - "global": Returns the global memory file path
    - "spec": Returns the spec-specific memory file path (requires spec_slug)

    File paths are resolved from system configuration, with defaults:
    - Global: .autoflow/memory/global.md
    - Spec: .autoflow/memory/specs/{spec_slug}.md

    Args:
        scope: Memory scope, either "global" or "spec"
        spec_slug: Optional spec identifier for spec-scoped memory

    Returns:
        Resolved Path object to the memory file

    Raises:
        SystemExit: If scope is "spec" but no spec_slug is provided

    Example:
        >>> global_mem = memory_file("global")
        >>> print(global_mem)
        PosixPath('.autoflow/memory/global.md')

        >>> spec_mem = memory_file("spec", "my-feature")
        >>> print(spec_mem)
        PosixPath('.autoflow/memory/specs/my-feature.md')
    """
    memory_cfg = load_system_config().get("memory", {})
    if scope == "global":
        return resolve_root_path(memory_cfg.get("global_file", MEMORY_DIR / "global.md"))
    if spec_slug:
        spec_dir = resolve_root_path(memory_cfg.get("spec_dir", MEMORY_DIR / "specs"))
        return spec_dir / f"{spec_slug}.md"
    raise SystemExit("spec scope requires a spec slug")


def append_memory(scope: str, content: str, spec_slug: str | None = None, title: str = "") -> Path:
    """
    Append content to a memory file with a timestamped heading.

    Creates parent directories if they don't exist. Content is appended
    as a markdown section with a level-2 heading. If no title is provided,
    uses a timestamp in the format "Memory @ YYYYMMDDTHHMMSSZ".

    Args:
        scope: Memory scope, either "global" or "spec"
        content: Content to append to the memory file
        spec_slug: Optional spec identifier for spec-scoped memory
        title: Optional title for the memory entry (defaults to timestamp)

    Returns:
        Path object for the memory file that was appended to

    Example:
        >>> append_memory("global", "Important note about the project")
        PosixPath('.autoflow/memory/global.md')

        >>> append_memory("spec", "Feature decision", "my-feature", title="Architecture Decision")
        PosixPath('.autoflow/memory/specs/my-feature.md')
    """
    path = memory_file(scope, spec_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    heading = title or f"Memory @ {now_stamp()}"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"## {heading}\n\n{content.strip()}\n\n")
    return path


def load_memory_context(spec_slug: str, scopes: list[str] | None = None) -> str:
    """
    Load memory context from global and spec-specific memory files.

    Reads and combines memory content from specified scopes. Each scope's
    content is prefixed with a markdown heading. Only loads content from
    memory files that exist. Respects the memory.enabled configuration
    setting.

    The scopes parameter filters which memory sources to include:
    - "global": Include global memory if available
    - "spec": Include spec-specific memory if available

    If no scopes are specified, uses the default_scopes from system config
    (defaults to ["spec"]).

    Args:
        spec_slug: Spec identifier for loading spec-scoped memory
        scopes: Optional list of scopes to load (defaults to config default_scopes)

    Returns:
        Formatted string containing memory context with section headings,
        or "Memory is disabled." if memory is disabled in config,
        or "No stored memory yet." if no memory files exist

    Example:
        >>> context = load_memory_context("my-feature")
        >>> print(context)
        ### Spec memory
        ## Memory @ 20240309T120000Z
        Important architectural decision...

        >>> context = load_memory_context("my-feature", scopes=["global", "spec"])
        >>> print(context)
        ### Global memory
        ## Memory @ 20240309T110000Z
        Project-wide note...

        ### Spec memory
        ## Memory @ 20240309T120000Z
        Feature-specific note...
    """
    config = load_system_config()
    memory_cfg = config.get("memory", {})
    if not memory_cfg.get("enabled", True):
        return "Memory is disabled."
    allowed_scopes = scopes or list(memory_cfg.get("default_scopes", ["spec"]))
    parts = []
    global_path = memory_file("global")
    spec_path = memory_file("spec", spec_slug)
    if "global" in allowed_scopes and global_path.exists():
        parts.append("### Global memory\n")
        parts.append(global_path.read_text(encoding="utf-8").strip())
    if "spec" in allowed_scopes and spec_path.exists():
        parts.append("### Spec memory\n")
        parts.append(spec_path.read_text(encoding="utf-8").strip())
    return "\n\n".join(part for part in parts if part).strip() or "No stored memory yet."


def strategy_memory_file(scope: str, spec_slug: str | None = None) -> Path:
    """
    Get the file path for a strategy memory store.

    Strategy memory can be stored at global or spec scope. Global memory applies
    across all specs, while spec memory is specific to a particular specification.

    Args:
        scope: Either "global" for system-wide strategy memory, or "spec" for
               spec-specific memory
        spec_slug: Slug identifier for the spec (required when scope="spec")

    Returns:
        Path to the strategy memory JSON file

    Raises:
        SystemExit: If scope="spec" but no spec_slug is provided

    Examples:
        >>> strategy_memory_file("global")
        PosixPath('.autoflow/memory/strategy/global.json')

        >>> strategy_memory_file("spec", "my-feature")
        PosixPath('.autoflow/memory/strategy/specs/my-feature.json')
    """
    if scope == "global":
        return STRATEGY_MEMORY_DIR / "global.json"
    if spec_slug:
        return STRATEGY_MEMORY_DIR / "specs" / f"{spec_slug}.json"
    raise SystemExit("spec scope requires a spec slug")


def strategy_memory_default() -> dict[str, Any]:
    """
    Get the default structure for a strategy memory store.

    Returns a dictionary with the standard schema used for strategy memory
    persistence. This structure tracks reflections, planner notes, statistics,
    and playbook entries across workflow runs.

    Returns:
        Dictionary with the following structure:
        - updated_at: ISO 8601 timestamp of last update (empty string for new)
        - reflections: List of reflection entries from workflow reviews
        - planner_notes: List of notes added by the planner agent
        - stats: Dictionary containing:
          - by_role: Counters grouped by agent role
          - by_result: Counters grouped by task result type
          - finding_categories: Counters for review finding categories
          - severity: Counters for finding severity levels
          - files: Counters for files mentioned in findings
        - playbook: List of actionable recommendations derived from patterns

    Examples:
        >>> strategy_memory_default()
        {'updated_at': '', 'reflections': [], 'planner_notes': [],
         'stats': {'by_role': {}, 'by_result': {}, 'finding_categories': {},
                   'severity': {}, 'files': {}}, 'playbook': []}
    """
    return {
        "updated_at": "",
        "reflections": [],
        "planner_notes": [],
        "stats": {
            "by_role": {},
            "by_result": {},
            "finding_categories": {},
            "severity": {},
            "files": {},
        },
        "playbook": [],
    }


def load_strategy_memory(scope: str, spec_slug: str | None = None) -> dict[str, Any]:
    """
    Load strategy memory from disk.

    Reads the strategy memory file for the specified scope (global or spec).
    If the file doesn't exist or contains invalid JSON, returns the default
    strategy memory structure.

    Args:
        scope: Either "global" for system-wide strategy memory, or "spec" for
               spec-specific memory
        spec_slug: Slug identifier for the spec (required when scope="spec")

    Returns:
        Dictionary containing strategy memory data with the structure:
        - updated_at: ISO 8601 timestamp of last update
        - reflections: List of reflection entries
        - planner_notes: List of planner notes
        - stats: Dictionary of statistical counters
        - playbook: List of actionable recommendations

    Examples:
        >>> memory = load_strategy_memory("global")
        >>> memory["playbook"]
        ['Address high-severity findings first']

        >>> spec_memory = load_strategy_memory("spec", "my-feature")
        >>> len(spec_memory["reflections"])
        3
    """
    return read_json_or_default(strategy_memory_file(scope, spec_slug), strategy_memory_default())


def save_strategy_memory(scope: str, payload: dict[str, Any], spec_slug: str | None = None) -> Path:
    """
    Save strategy memory to disk.

    Writes the strategy memory payload to the appropriate file based on scope.
    Automatically updates the `updated_at` timestamp to the current UTC time
    before saving. Creates parent directories if they don't exist.

    Args:
        scope: Either "global" for system-wide strategy memory, or "spec" for
               spec-specific memory
        payload: Dictionary containing strategy memory data. Must include the
                 standard structure (reflections, planner_notes, stats, playbook).
                 The `updated_at` field will be overwritten with the current time.
        spec_slug: Slug identifier for the spec (required when scope="spec")

    Returns:
        Path to the file that was written

    Examples:
        >>> memory = load_strategy_memory("global")
        >>> memory["playbook"].append("New recommendation")
        >>> save_strategy_memory("global", memory)
        PosixPath('.autoflow/memory/strategy/global.json')

        >>> spec_memory = load_strategy_memory("spec", "my-feature")
        >>> spec_memory["reflections"].append(new_reflection)
        >>> save_strategy_memory("spec", spec_memory, "my-feature")
        PosixPath('.autoflow/memory/strategy/specs/my-feature.json')
    """
    payload["updated_at"] = now_stamp()
    path = strategy_memory_file(scope, spec_slug)
    write_json(path, payload)
    return path


def increment_counter(counters: dict[str, int], key: str) -> None:
    """
    Increment a counter in a dictionary.

    Creates the counter with initial value 1 if it doesn't exist.
    Does nothing if the key is empty.

    Args:
        counters: Dictionary of counters to update
        key: Counter key to increment
    """
    if not key:
        return
    counters[key] = counters.get(key, 0) + 1


# ============================================================================
# Agent Configuration Functions
# ============================================================================


@dataclass
class AgentSpec:
    """
    Specification for an AI agent configuration.

    Contains all parameters needed to instantiate and execute an AI agent,
    including command invocation, protocol settings, model configuration,
    tool access, and memory scopes.

    Attributes:
        name: Unique identifier for this agent
        command: Executable command to run (e.g., "claude", "codex")
        args: Command-line arguments to pass to the agent
        resume: Resume configuration (flags, session handling)
        protocol: Communication protocol ("cli", "api", etc.)
        model: Model identifier string
        model_profile: Named profile from system config models
        tools: List of tools/functions available to the agent
        tool_profile: Named profile from system config tools
        memory_scopes: Memory scopes this agent can access
        transport: Additional transport configuration options
    """

    name: str
    command: str
    args: list[str]
    resume: dict[str, Any] | None = None
    protocol: str = "cli"
    model: str = ""
    model_profile: str = ""
    tools: list[str] | None = None
    tool_profile: str = ""
    memory_scopes: list[str] | None = None
    transport: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert agent specification to dictionary.

        Serializes the AgentSpec dataclass instance to a plain dictionary
        suitable for JSON serialization or configuration storage.

        Returns:
            Dictionary representation of the agent specification with all
            configuration fields including name, command, args, resume settings,
            protocol, model, tools, and transport configuration.
        """
        data = {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "protocol": self.protocol,
        }
        if self.resume:
            data["resume"] = self.resume
        if self.model:
            data["model"] = self.model
        if self.model_profile:
            data["model_profile"] = self.model_profile
        if self.tools:
            data["tools"] = self.tools
        if self.tool_profile:
            data["tool_profile"] = self.tool_profile
        if self.memory_scopes:
            data["memory_scopes"] = self.memory_scopes
        if self.transport:
            data["transport"] = self.transport
        return data


# Cache for agent configuration
_agents_config_cache: dict[str, AgentSpec] | None = None


def _populate_agents_cache() -> None:
    """Load agents configuration into the cache.

    This implements lazy-loading: agents config is only loaded from disk when needed.
    Subsequent calls will use the cached data (O(1) lookup).

    Cache Behavior:
        If _agents_config_cache is not None, we've already loaded the agents,
        so we return immediately (cache hit). Otherwise, we load the agents from
        disk using load_agents() and store it in the cache.

    Note: Unlike run metadata cache, there's only one agents config, so this
    is a simple load-once pattern without opportunistic caching.

    The cached data is a dictionary mapping agent names to AgentSpec objects.
    """
    global _agents_config_cache

    # Skip if already loaded (cache hit)
    if _agents_config_cache is not None:
        return

    # Load agents config from disk
    _agents_config_cache = load_agents()


def invalidate_agents_cache() -> None:
    """Invalidate the agents configuration cache.

    Call this function whenever the agents configuration is modified to ensure
    the cache remains consistent with the filesystem state.

    Cache Invalidation Strategy:
        - Simple: set the cached data to None
        - Safe: ensures cache consistency after config modification
        - Lazy: data is reloaded on next access (not immediately)

    Note: Agents config modifications are rare (e.g., sync-agents command),
    so aggressive invalidation is acceptable. The cache will be repopulated
    on the next access.
    """
    global _agents_config_cache
    _agents_config_cache = None


def resolve_agent_profiles(spec: dict[str, Any], system_config: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve model and tool profiles in an agent specification.

    Expands named profiles (model_profile, tool_profile) to their actual
    values from system configuration. Also sets default memory_scopes
    if not specified.

    Args:
        spec: Agent specification dictionary with potential profile references
        system_config: System configuration containing model and tool profiles

    Returns:
        Resolved agent specification with expanded profiles
    """
    resolved = dict(spec)
    model_profiles = system_config.get("models", {}).get("profiles", {})
    tool_profiles = system_config.get("tools", {}).get("profiles", {})
    if not resolved.get("model") and resolved.get("model_profile"):
        resolved["model"] = model_profiles.get(resolved["model_profile"], "")
    if not resolved.get("tools") and resolved.get("tool_profile"):
        resolved["tools"] = tool_profiles.get(resolved["tool_profile"], [])
    if not resolved.get("memory_scopes"):
        resolved["memory_scopes"] = list(
            system_config.get("memory", {}).get("default_scopes", ["spec"])
        )
    return resolved


def load_agents() -> dict[str, AgentSpec]:
    """
    Load and parse all configured agents from the agents file.

    Reads the agents.json file, resolves model and tool profiles from
    system configuration, and instantiates AgentSpec objects for each agent.

    Caching Behavior:
        This function uses an in-memory cache to avoid repeated disk I/O.
        On first call, it loads the agents from disk and caches them.
        Subsequent calls return the cached value directly (O(1) lookup).
        Use invalidate_agents_cache() to clear the cache after
        modifying agents.json.

    Performance:
        - First call: O(n) filesystem read and JSON parsing
        - Subsequent calls: O(1) memory lookup
        - Typical speedup: 10-20x for repeated calls

    Returns:
        Dictionary mapping agent names to AgentSpec objects

    Raises:
        SystemExit: If agents.json file does not exist
    """
    global _agents_config_cache

    # Return cached value if available (cache hit)
    if _agents_config_cache is not None:
        return _agents_config_cache

    # Load from disk and cache the result
    if not AGENTS_FILE.exists():
        raise SystemExit(
            f"missing {AGENTS_FILE}. copy config/agents.example.json to .autoflow/agents.json first"
        )
    data = read_json(AGENTS_FILE)
    system_config = load_system_config()
    agents = {}
    for name, spec in data.get("agents", {}).items():
        resolved = resolve_agent_profiles(spec, system_config)
        agents[name] = AgentSpec(
            name=name,
            command=resolved["command"],
            args=list(resolved.get("args", [])),
            resume=resolved.get("resume"),
            protocol=resolved.get("protocol", "cli"),
            model=resolved.get("model", ""),
            model_profile=resolved.get("model_profile", ""),
            tools=list(resolved.get("tools", [])) if resolved.get("tools") else None,
            tool_profile=resolved.get("tool_profile", ""),
            memory_scopes=list(resolved.get("memory_scopes", [])) if resolved.get("memory_scopes") else None,
            transport=resolved.get("transport"),
        )
    _agents_config_cache = agents
    return _agents_config_cache


def normalize_findings(summary: str, findings: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Normalize review findings to a standard structure.

    Converts findings from various sources into a consistent format with all required
    fields. Handles missing or inconsistent data by providing sensible defaults.
    Each finding gets a unique ID if not present, and line numbers are normalized.

    Args:
        summary: Default summary text to use when finding body is missing
        findings: List of finding dictionaries from review sources, or None to create
                  a single default finding

    Returns:
        List of normalized finding dictionaries with keys:
        - id: Unique finding identifier (e.g., "F1", "F2")
        - title: Finding title or "Follow-up required"
        - body: Detailed description or summary
        - file: File path (empty string if not applicable)
        - line: Starting line number (None if not applicable)
        - end_line: Ending line number (None if not applicable)
        - severity: Severity level ("critical", "high", "medium", "low")
        - category: Finding category (e.g., "tests", "workflow", "general")
        - suggested_fix: Suggested fix text (empty string if none)
        - source_run: Source run identifier (empty string if none)

    Examples:
        >>> findings = [
        ...     {"title": "Add tests", "severity": "high", "category": "tests"}
        ... ]
        >>> normalized = normalize_findings("Please add tests", findings)
        >>> normalized[0]["id"]
        'F1'
        >>> normalized[0]["body"]
        'Please add tests'

        >>> normalized = normalize_findings("Fix bug", None)
        >>> len(normalized)
        1
        >>> normalized[0]["id"]
        'F1'
    """
    if findings:
        normalized = []
        for index, finding in enumerate(findings, start=1):
            start_line = finding.get("line", finding.get("start_line"))
            end_line = finding.get("end_line")
            normalized.append(
                {
                    "id": finding.get("id") or f"F{index}",
                    "title": finding.get("title") or "Follow-up required",
                    "body": finding.get("body") or summary,
                    "file": finding.get("file", ""),
                    "line": int(start_line) if start_line not in (None, "") else None,
                    "end_line": int(end_line) if end_line not in (None, "") else None,
                    "severity": finding.get("severity", "medium"),
                    "category": finding.get("category", "general"),
                    "suggested_fix": finding.get("suggested_fix", ""),
                    "source_run": finding.get("source_run", ""),
                }
            )
        return normalized
    return [
        {
            "id": "F1",
            "title": "Follow-up required",
            "body": summary,
            "file": "",
            "line": None,
            "end_line": None,
            "severity": "medium",
            "category": "general",
            "suggested_fix": "",
            "source_run": "",
        }
    ]


def load_agent_result_payload(result_file: Path) -> tuple[str, str, list[dict[str, Any]], str]:
    """
    Load and validate an agent result payload from a JSON file.

    Reads an agent result JSON file and validates its structure. Ensures that
    required fields are present and have the correct types. Normalizes findings
    if present.

    Args:
        result_file: Path to the agent result JSON file

    Returns:
        A tuple containing:
        - result: Result status string ("success", "needs_changes", "blocked", "failed")
        - summary: Summary text from the result
        - findings: List of normalized finding dictionaries
        - details: String representation of the result file path

    Raises:
        FileNotFoundError: If the result file does not exist
        ValueError: If the result payload is not a valid JSON object or contains
                    invalid data types
    """
    if not result_file.exists():
        raise FileNotFoundError(result_file)
    raw = read_json(result_file)
    if not isinstance(raw, dict):
        raise ValueError("agent result payload must be a JSON object")
    result = str(raw.get("result", "")).strip()
    if result not in RUN_RESULTS:
        raise ValueError("agent result payload must contain a valid result")
    summary = str(raw.get("summary", "")).strip() or f"Agent reported result {result}."
    findings = raw.get("findings", [])
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        raise ValueError("agent result findings must be a list")
    normalized = normalize_findings(summary, findings) if findings else []
    return result, summary, normalized, str(result_file)
