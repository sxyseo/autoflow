"""
Autoflow Core Commands - Pure data-returning functions

This module provides pure functions that extract and return data from the Autoflow state.
These functions mirror CLI commands but return data structures instead of printing JSON,
making them suitable for direct import by orchestration scripts.

Functions:
- get_workflow_state: Get complete workflow state for a spec
- get_task_history: Get run history for a specific task
- get_strategy_summary: Get strategy memory summary
- sync_agents: Sync discovered agents to agents.json
- taskmaster_import: Import tasks from Taskmaster format
- taskmaster_export: Export tasks to Taskmaster format
- validate_slug_safe: Validate that a slug does not contain path traversal patterns
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# === Path Constants ===

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = ROOT / ".autoflow"
SPECS_DIR = STATE_DIR / "specs"
TASKS_DIR = STATE_DIR / "tasks"
RUNS_DIR = STATE_DIR / "runs"
STRATEGY_MEMORY_DIR = STATE_DIR / "memory" / "strategy"
LOGS_DIR = STATE_DIR / "logs"
MEMORY_DIR = STATE_DIR / "memory"
DISCOVERY_FILE = STATE_DIR / "discovered_agents.json"
SYSTEM_CONFIG_FILE = STATE_DIR / "system.json"
SYSTEM_CONFIG_TEMPLATE = ROOT / "config" / "system.example.json"
AGENTS_FILE = STATE_DIR / "agents.json"

REVIEW_STATE_FILE = "review_state.json"
QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
QA_FIX_REQUEST_JSON_FILE = "QA_FIX_REQUEST.json"
EVENTS_FILE = "events.jsonl"

VALID_TASK_STATUSES = {
    "todo",
    "in_progress",
    "in_review",
    "needs_changes",
    "blocked",
    "done",
}


# === Helper Functions ===


def _spec_files(slug: str) -> dict[str, Path]:
    """Get file paths for a spec."""
    if not validate_slug_safe(slug):
        raise SystemExit("invalid spec slug")
    directory = SPECS_DIR / slug
    return {
        "dir": directory,
        "spec": directory / "spec.md",
        "metadata": directory / "metadata.json",
        "review_state": directory / REVIEW_STATE_FILE,
        "qa_fix_request": directory / QA_FIX_REQUEST_FILE,
        "qa_fix_request_json": directory / QA_FIX_REQUEST_JSON_FILE,
        "events": directory / EVENTS_FILE,
    }


def _read_json_or_default(path: Path, default: Any) -> Any:
    """Read JSON file, returning default if missing or invalid."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _task_file(spec_slug: str) -> Path:
    """Get path to task file for a spec."""
    if not validate_slug_safe(spec_slug):
        raise SystemExit("invalid spec slug")
    return TASKS_DIR / f"{spec_slug}.json"


def _load_tasks(spec_slug: str) -> dict[str, Any]:
    """Load task data for a spec."""
    path = _task_file(spec_slug)
    if not path.exists():
        raise SystemExit(f"missing task file: {path}")
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _task_lookup(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Look up a task by ID in task data."""
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            result: dict[str, Any] = task
            return result
    raise SystemExit(f"unknown task: {task_id}")


def _compute_file_hash(path: Path) -> str:
    """Compute MD5 hash of a file's contents."""
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


def _planning_contract(spec_slug: str) -> dict[str, Any]:
    """Get the planning contract (tasks) for a spec."""
    task_data = _load_tasks(spec_slug)
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


def _compute_spec_hash(spec_slug: str) -> str:
    """Compute hash of spec and tasks for review validation."""
    files = _spec_files(spec_slug)
    spec_hash = _compute_file_hash(files["spec"])
    task_hash = hashlib.md5(
        json.dumps(_planning_contract(spec_slug), sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    combined = f"{spec_hash}:{task_hash}"
    return hashlib.md5(combined.encode("utf-8"), usedforsecurity=False).hexdigest()


def _review_state_default() -> dict[str, Any]:
    """Get default review state."""
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


def _load_review_state(spec_slug: str) -> dict[str, Any]:
    """Load review state for a spec."""
    result: dict[str, Any] = _read_json_or_default(
        _spec_files(spec_slug)["review_state"],
        _review_state_default()
    )
    return result


def _save_review_state(spec_slug: str, state: dict[str, Any]) -> None:
    """Save review state for a spec."""
    path = _spec_files(spec_slug)["review_state"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _sync_review_state(spec_slug: str, reason: str = "planning_artifacts_changed") -> dict[str, Any]:
    """Sync review state, invalidating if spec has changed."""
    state = _load_review_state(spec_slug)
    if state.get("approved") and state.get("spec_hash") != _compute_spec_hash(spec_slug):
        state["approved"] = False
        state["invalidated_at"] = ""  # Would use now_stamp() in CLI
        state["invalidated_reason"] = reason
        _save_review_state(spec_slug, state)
    return state


def _review_status_summary(spec_slug: str) -> dict[str, Any]:
    """Get review status summary for a spec."""
    state = _sync_review_state(spec_slug)
    current_hash = _compute_spec_hash(spec_slug)
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


def _run_metadata_iter() -> list[dict[str, Any]]:
    """Iterate over all run metadata."""
    items: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return items
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            items.append(json.loads(metadata_path.read_text(encoding="utf-8")))
    return items


def _active_runs_for_spec(spec_slug: str) -> list[dict[str, Any]]:
    """Get active (non-completed) runs for a spec."""
    return [
        item
        for item in _run_metadata_iter()
        if item.get("spec") == spec_slug and item.get("status") != "completed"
    ]


def _load_fix_request(spec_slug: str) -> str:
    """Load QA fix request text for a spec."""
    path = _spec_files(spec_slug)["qa_fix_request"]
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _load_fix_request_data(spec_slug: str) -> dict[str, Any]:
    """Load QA fix request JSON data for a spec."""
    result: dict[str, Any] = _read_json_or_default(
        _spec_files(spec_slug)["qa_fix_request_json"],
        {"task": "", "result": "", "summary": "", "finding_count": 0, "findings": []},
    )
    return result


def _strategy_memory_file(scope: str, spec_slug: str | None = None) -> Path:
    """Get path to strategy memory file."""
    if scope == "global":
        return STRATEGY_MEMORY_DIR / "global.json"
    if spec_slug:
        return STRATEGY_MEMORY_DIR / "specs" / f"{spec_slug}.json"
    raise SystemExit("spec scope requires a spec slug")


def _strategy_memory_default() -> dict[str, Any]:
    """Get default strategy memory structure."""
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


def _load_strategy_memory(scope: str, spec_slug: str | None = None) -> dict[str, Any]:
    """Load strategy memory."""
    result: dict[str, Any] = _read_json_or_default(
        _strategy_memory_file(scope, spec_slug),
        _strategy_memory_default()
    )
    return result


def _strategy_summary(spec_slug: str) -> dict[str, Any]:
    """Get strategy memory summary for a spec."""
    spec_memory = _load_strategy_memory("spec", spec_slug)
    recent = spec_memory.get("reflections", [])[-5:]
    return {
        "updated_at": spec_memory.get("updated_at", ""),
        "playbook": spec_memory.get("playbook", []),
        "planner_notes": spec_memory.get("planner_notes", [])[-5:],
        "recent_reflections": recent,
        "stats": spec_memory.get("stats", {}),
    }


# === Agent Sync Helper Functions ===


def _now_utc() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def _now_stamp() -> str:
    """Get current timestamp in ISO 8601 format."""
    return _now_utc().strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, data: Any) -> None:
    """Write data to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _ensure_state() -> None:
    """Ensure state directories exist."""
    for path in [STATE_DIR, SPECS_DIR, TASKS_DIR, RUNS_DIR, LOGS_DIR, MEMORY_DIR, STRATEGY_MEMORY_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _system_config_default() -> dict[str, Any]:
    """Get default system configuration."""
    if SYSTEM_CONFIG_TEMPLATE.exists():
        result: dict[str, Any] = _read_json_or_default(SYSTEM_CONFIG_TEMPLATE, {})
        return result
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


def _load_system_config() -> dict[str, Any]:
    """Load system configuration from file."""
    config = _system_config_default()
    if SYSTEM_CONFIG_FILE.exists():
        local = _read_json_or_default(SYSTEM_CONFIG_FILE, {})
        config = _deep_merge(config, local)
    return _deep_merge(
        {
            "memory": {"default_scopes": ["spec"]},
            "models": {"profiles": {}},
            "tools": {"profiles": {}},
            "registry": {"acp_agents": []},
        },
        config,
    )


def _run_cmd(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _discover_cli_agent(name: str, command: str) -> dict[str, Any] | None:
    """Discover a CLI agent by checking if it's available."""
    executable = shutil.which(command)
    if not executable:
        return None
    help_result = _run_cmd([command, "--help"], check=False)
    help_text = (help_result.stdout or "") + (help_result.stderr or "")
    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }
    return {
        "name": name,
        "protocol": "cli",
        "command": command,
        "path": executable,
        "capabilities": capabilities,
    }


def _discover_agents_registry() -> dict[str, Any]:
    """Discover all available agents (CLI and ACP)."""
    config = _load_system_config()
    discovered = []
    for name, command in [("codex", "codex"), ("claude", "claude")]:
        item = _discover_cli_agent(name, command)
        if item:
            discovered.append(item)
    for agent in config.get("registry", {}).get("acp_agents", []):
        discovered.append(
            {
                "name": agent.get("name", "acp-agent"),
                "protocol": "acp",
                "transport": agent.get("transport", {}),
                "capabilities": agent.get("capabilities", {}),
            }
        )
    payload = {
        "discovered_at": _now_stamp(),
        "agents": discovered,
        "system_config": {
            "memory": config.get("memory", {}),
            "models": config.get("models", {}),
            "tools": config.get("tools", {}),
        },
    }
    _write_json(DISCOVERY_FILE, payload)
    return payload


def _discovered_agent_to_config(agent: dict[str, Any]) -> dict[str, Any]:
    """Convert discovered agent to configuration format."""
    if agent.get("protocol") == "acp":
        return {
            "protocol": "acp",
            "command": agent.get("transport", {}).get("command", agent.get("name", "acp-agent")),
            "args": [],
            "transport": agent.get("transport", {}),
            "memory_scopes": ["spec"],
        }
    resume = None
    if agent.get("name") == "codex" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "subcommand", "subcommand": "resume", "args": ["--last"]}
    elif agent.get("name") == "claude" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "args", "args": ["--continue"]}
    return {
        "protocol": "cli",
        "command": agent.get("command", agent.get("name", "")),
        "args": [],
        "resume": resume,
        "memory_scopes": ["spec"],
    }


# === Taskmaster Helper Functions ===


def _read_json(path: Path) -> Any:
    """Read JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _record_event(spec_slug: str, event_type: str, payload: dict[str, Any]) -> None:
    """Record an event to the spec's events file."""
    events_path = _spec_files(spec_slug)["events"]
    events_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": _now_stamp(),
        "type": event_type,
        "payload": payload,
    }
    with open(events_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def _normalize_imported_task(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize a task entry from Taskmaster format."""
    depends = entry.get("depends_on", entry.get("dependencies", [])) or []
    criteria = entry.get("acceptance_criteria", entry.get("acceptanceCriteria", [])) or []
    status = entry.get("status", "todo")
    if status not in VALID_TASK_STATUSES:
        status = "todo"
    return {
        "id": entry.get("id") or f"T{index}",
        "title": entry.get("title", entry.get("name", f"Task {index}")),
        "status": status,
        "depends_on": depends,
        "owner_role": entry.get("owner_role", entry.get("role", "implementation-runner")),
        "acceptance_criteria": criteria,
        "notes": entry.get("notes", []),
    }


def _taskmaster_payload(spec_slug: str) -> dict[str, Any]:
    """Generate Taskmaster export payload for a spec."""
    tasks = _load_tasks(spec_slug)
    return {
        "project": spec_slug,
        "exported_at": _now_stamp(),
        "tasks": [
            {
                "id": task["id"],
                "title": task["title"],
                "status": task["status"],
                "dependencies": task.get("depends_on", []),
                "owner_role": task["owner_role"],
                "acceptanceCriteria": task.get("acceptance_criteria", []),
                "notes": task.get("notes", []),
            }
            for task in tasks.get("tasks", [])
        ],
    }


# === Public API Functions ===


def get_workflow_state(spec_slug: str) -> dict[str, Any]:
    """
    Get complete workflow state for a spec.

    Args:
        spec_slug: Spec identifier (e.g., "001-example")

    Returns:
        Dict containing:
        - spec: Spec identifier
        - review_status: Review approval status
        - worktree: Git worktree information
        - fix_request_present: Whether QA fix request exists
        - fix_request: QA fix request data
        - strategy_summary: Strategy memory summary
        - active_runs: List of active run metadata
        - ready_tasks: Tasks ready to be executed
        - blocked_or_active_tasks: Tasks that are blocked or active
        - blocking_reason: Reason if workflow is blocked
        - recommended_next_action: Next recommended task to execute

    Raises:
        SystemExit: If spec task file is missing
    """
    data = _load_tasks(spec_slug)
    review_summary = _review_status_summary(spec_slug)
    active_runs = _active_runs_for_spec(spec_slug)

    ready = []
    blocked = []
    for task in data.get("tasks", []):
        deps_done = all(
            _task_lookup(data, dep)["status"] == "done"
            for dep in task.get("depends_on", [])
        )
        entry = {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "owner_role": task["owner_role"],
        }
        is_ready = False
        if task["status"] in {"todo", "needs_changes"} and deps_done:
            is_ready = True
        if task["status"] == "in_review":
            entry["owner_role"] = "reviewer"
            is_ready = True
        if is_ready:
            ready.append(entry)
        elif task["status"] != "done":
            blocked.append(entry)

    next_entry = ready[0] if ready else None
    blocking_reason = ""
    if (
        next_entry
        and next_entry["owner_role"] in {"implementation-runner", "maintainer"}
        and not review_summary["valid"]
    ):
        blocking_reason = "review_approval_required"
        next_entry = None

    return {
        "spec": spec_slug,
        "review_status": review_summary,
        "worktree": _read_json_or_default(_spec_files(spec_slug)["metadata"], {}).get("worktree", {}),
        "fix_request_present": bool(_load_fix_request(spec_slug)),
        "fix_request": _load_fix_request_data(spec_slug),
        "strategy_summary": _strategy_summary(spec_slug),
        "active_runs": active_runs,
        "ready_tasks": ready,
        "blocked_or_active_tasks": blocked,
        "blocking_reason": blocking_reason,
        "recommended_next_action": None if active_runs else next_entry,
    }


def get_task_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Get run history for a specific task.

    Args:
        spec_slug: Spec identifier
        task_id: Task identifier (e.g., "task-1")
        limit: Maximum number of history entries to return

    Returns:
        List of run metadata dicts, sorted by creation time, most recent last.
        Each dict contains run information (id, role, result, created_at, etc.)
    """
    history = [
        item
        for item in _run_metadata_iter()
        if item.get("spec") == spec_slug and item.get("task") == task_id
    ]
    return sorted(history, key=lambda item: item.get("created_at", ""))[-limit:]


def sync_agents(overwrite: bool = False) -> dict[str, Any]:
    """
    Sync discovered agents to agents.json configuration file.

    Discovers available CLI agents (claude, codex) and ACP agents from system config,
    then merges them into the agents.json file. Existing agents are preserved unless
    overwrite=True.

    Args:
        overwrite: If True, overwrite existing agent configs. If False, skip existing.

    Returns:
        Dict containing:
        - agents_file: Path to agents.json
        - added: List of agent names that were added
        - total_agents: Total number of agents in file after sync
    """
    _ensure_state()
    discovered = _discover_agents_registry()
    existing = {"defaults": {"workspace": ".", "shell": "bash"}, "agents": {}}
    if AGENTS_FILE.exists():
        existing = _read_json_or_default(AGENTS_FILE, existing)
        existing.setdefault("defaults", {"workspace": ".", "shell": "bash"})
        existing.setdefault("agents", {})
    agents_dict = existing.get("agents", {})
    assert isinstance(agents_dict, dict)
    merged: dict[str, dict[str, Any]] = {}
    for key, value in agents_dict.items():
        if isinstance(key, str) and isinstance(value, dict):
            merged[key] = value
    added: list[str] = []
    for agent in discovered.get("agents", []):
        name = agent["name"]
        if name in merged and not overwrite:
            continue
        merged[name] = _discovered_agent_to_config(agent)
        added.append(name)
    payload = {"defaults": existing["defaults"], "agents": merged}
    _write_json(AGENTS_FILE, payload)
    return {
        "agents_file": str(AGENTS_FILE),
        "added": added,
        "total_agents": len(merged),
    }


def get_strategy_summary(spec_slug: str) -> dict[str, Any]:
    """
    Get strategy memory summary for a spec.

    Args:
        spec_slug: Spec identifier

    Returns:
        Dict containing:
        - updated_at: Last update timestamp
        - playbook: Learned rules and patterns
        - planner_notes: Recent planner notes
        - recent_reflections: Recent reflection entries
        - stats: Strategy statistics
    """
    return _strategy_summary(spec_slug)


def taskmaster_export(spec_slug: str, output: str | None = None) -> dict[str, Any] | Path:
    """
    Export tasks to Taskmaster format.

    Args:
        spec_slug: Spec identifier
        output: Optional output file path. If provided, writes to file and returns Path.
                If None, returns the export payload dict.

    Returns:
        If output is None: Export payload dict with project, exported_at, and tasks list.
        If output is provided: Path to the written file.
    """
    payload = _taskmaster_payload(spec_slug)
    if output:
        output_path = Path(output)
        _write_json(output_path, payload)
        return output_path
    return payload


def taskmaster_import(spec_slug: str, input: str) -> dict[str, Any]:
    """
    Import tasks from Taskmaster format.

    Reads a Taskmaster export file (JSON with tasks array), normalizes the task data,
    and imports it into the spec's task file. Records an event and syncs review state.

    Args:
        spec_slug: Spec identifier
        input: Path to input file (JSON)

    Returns:
        Dict containing:
        - spec: Spec identifier
        - task_count: Number of tasks imported
    """
    input_path = Path(input)
    payload = _read_json(input_path)
    tasks_input = payload if isinstance(payload, list) else payload.get("tasks", [])
    normalized = [
        _normalize_imported_task(item, index)
        for index, item in enumerate(tasks_input, start=1)
    ]
    data = {
        "spec_slug": spec_slug,
        "updated_at": _now_stamp(),
        "tasks": normalized,
    }
    _write_json(_task_file(spec_slug), data)
    _sync_review_state(spec_slug, reason="taskmaster_import")
    _record_event(spec_slug, "taskmaster.imported", {"task_count": len(normalized), "source": str(input_path)})
    return {"spec": spec_slug, "task_count": len(normalized)}


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
    - Drive letters (Windows absolute paths like C:)

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


__all__ = [
    "get_workflow_state",
    "get_task_history",
    "sync_agents",
    "get_strategy_summary",
    "taskmaster_import",
    "taskmaster_export",
    "validate_slug_safe",
]
