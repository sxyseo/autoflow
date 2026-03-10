#!/usr/bin/env python3
"""
Autoflow CLI - Control Plane Interface

Provides the command-line interface for managing Autoflow specs, tasks, agents,
and git worktrees. This is the main entry point for interacting with the Autoflow
workflow system.

Features:
    - Spec and task lifecycle management
    - Git worktree isolation for parallel development
    - Agent discovery and configuration
    - Memory and strategy tracking
    - Review and approval workflows
    - Run execution and history tracking

Usage:
    # Initialize Autoflow state
    python scripts/autoflow.py init

    # Create a new spec
    python scripts/autoflow.py new-spec --title "Add Feature" --summary "Description"

    # Show available tasks
    python scripts/autoflow.py list-tasks --spec my-spec

    # Create a worktree for isolated development
    python scripts/autoflow.py create-worktree --spec my-spec

    # Show overall status
    python scripts/autoflow.py status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoflow.core.sanitization import sanitize_dict, sanitize_value


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
SPECS_DIR = STATE_DIR / "specs"
TASKS_DIR = STATE_DIR / "tasks"
RUNS_DIR = STATE_DIR / "runs"
LOGS_DIR = STATE_DIR / "logs"
WORKTREES_DIR = STATE_DIR / "worktrees" / "tasks"
MEMORY_DIR = STATE_DIR / "memory"
STRATEGY_MEMORY_DIR = MEMORY_DIR / "strategy"
DISCOVERY_FILE = STATE_DIR / "discovered_agents.json"
SYSTEM_CONFIG_FILE = STATE_DIR / "system.json"
SYSTEM_CONFIG_TEMPLATE = ROOT / "config" / "system.example.json"
AGENTS_FILE = STATE_DIR / "agents.json"
BMAD_DIR = ROOT / "templates" / "bmad"
REVIEW_STATE_FILE = "review_state.json"
EVENTS_FILE = "events.jsonl"
QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
QA_FIX_REQUEST_JSON_FILE = "QA_FIX_REQUEST.json"
VALID_TASK_STATUSES = {
    "todo",
    "in_progress",
    "in_review",
    "needs_changes",
    "blocked",
    "done",
}
RUN_RESULTS = {"success", "needs_changes", "blocked", "failed"}


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
    """Validate that a slug does not contain path traversal patterns.

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
    }
    sanitized_data = data if preserve_runtime_config else (
        sanitize_dict(data) if isinstance(data, dict) else sanitize_value(data) if isinstance(data, list) else data
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitized_data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def print_json(data: Any) -> None:
    """
    Print JSON data to stdout with sanitization.

    Sanitizes sensitive data before printing to prevent information disclosure.

    Args:
        data: JSON-serializable data to print
    """
    # Sanitize data to remove sensitive information
    # Use sanitize_value to handle both dicts and lists containing sensitive data
    sanitized_data = sanitize_dict(data) if isinstance(data, dict) else sanitize_value(data) if isinstance(data, list) else data
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
    for path in [STATE_DIR, SPECS_DIR, TASKS_DIR, RUNS_DIR, LOGS_DIR, WORKTREES_DIR, MEMORY_DIR, STRATEGY_MEMORY_DIR]:
        path.mkdir(parents=True, exist_ok=True)


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
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "resume": self.resume or {},
            "protocol": self.protocol,
            "model": self.model,
            "model_profile": self.model_profile,
            "tools": self.tools or [],
            "tool_profile": self.tool_profile,
            "memory_scopes": self.memory_scopes or [],
            "transport": self.transport or {},
        }


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
    return path if path.is_absolute() else ROOT / path


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

    Returns:
        Dictionary mapping agent names to AgentSpec objects

    Raises:
        SystemExit: If agents.json file does not exist
    """
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
    return agents


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


def worktree_path(spec_slug: str) -> Path:
    """
    Get the worktree path for a spec.

    Args:
        spec_slug: Spec slug identifier

    Returns:
        Path to the worktree directory
    """
    if not validate_slug_safe(spec_slug):
        raise SystemExit(f"invalid spec slug: {spec_slug}")
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

    Returns:
        Merged system configuration dictionary with the following structure:
        - memory: Memory settings including default_scopes, enabled flag,
          auto_capture_run_results, global_file path, and spec_dir path (dict)
        - models: Model profile configurations with profiles for different tasks (dict)
        - tools: Tool profile configurations with profiles for different agent types (dict)
        - registry: Registry settings including acp_agents list (dict)
    """
    config = system_config_default()
    if SYSTEM_CONFIG_FILE.exists():
        local = read_json_or_default(SYSTEM_CONFIG_FILE, {})
        config = deep_merge(config, local)
    return deep_merge(
        {
            "memory": {"default_scopes": ["spec"]},
            "models": {"profiles": {}},
            "tools": {"profiles": {}},
            "registry": {"acp_agents": []},
        },
        config,
    )


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


def derive_strategy_actions(
    role: str,
    result: str,
    findings: list[dict[str, Any]],
    stats: dict[str, Any],
) -> list[str]:
    """
    Derive strategic actions from review findings and statistics.

    Analyzes review findings, result status, and historical statistics to generate
    actionable recommendations for improving future work. Considers severity levels,
    categories, file paths, and recurring patterns.

    Args:
        role: Agent role (e.g., "implementation-runner", "maintainer")
        result: Review result status (e.g., "success", "needs_changes", "blocked", "failed")
        findings: List of review findings with category, severity, and file metadata
        stats: Historical statistics including finding_categories and file counts

    Returns:
        List of strategic action recommendations based on the analysis
    """
    actions: list[str] = []
    categories = {finding.get("category", "") for finding in findings if finding.get("category")}
    severities = {finding.get("severity", "") for finding in findings if finding.get("severity")}
    files = [finding.get("file", "") for finding in findings if finding.get("file")]

    if any(level in severities for level in {"critical", "high"}):
        actions.append("Address the highest-severity findings before broad refactors or new features.")
    if "tests" in categories or any("test" in path.lower() for path in files):
        actions.append("Add or update a regression test before sending the task back to review.")
    if "workflow" in categories or "infra" in categories:
        actions.append("Re-run the relevant control-plane command locally before retrying the task.")
    if result in {"needs_changes", "blocked", "failed"}:
        actions.append("Start the retry from the structured fix request instead of reusing the prior edit plan.")
    if role in {"implementation-runner", "maintainer"} and result == "success":
        actions.append("Keep the validated edit path small and capture the exact verification steps in the handoff.")

    recurring_categories = [
        category
        for category, count in stats.get("finding_categories", {}).items()
        if count >= 2
    ]
    if recurring_categories:
        actions.append(
            "Review recurring blocker categories first: " + ", ".join(sorted(recurring_categories))
        )
    return actions


def rebuild_playbook(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Rebuild a playbook from memory statistics.

    Generates actionable rules based on historical finding categories and file hotspots.
    Prioritizes rules by evidence count and includes special handling for tests
    and workflow categories. Returns the top 8 rules.

    Args:
        memory: Strategy memory dictionary containing stats with finding_categories
                and files counts

    Returns:
        List of playbook entries sorted by evidence count (highest first).
        Each entry contains category/file, evidence_count, and a rule string.
        Maximum 8 entries.
    """
    playbook: list[dict[str, Any]] = []
    for category, count in sorted(
        memory.get("stats", {}).get("finding_categories", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        rule = f"Before retrying work that touches {category}, review prior findings and front-load verification."
        if category == "tests":
            rule = "If tests-related findings recur, write the regression test before or alongside the fix."
        elif category == "workflow":
            rule = "If workflow findings recur, validate control-plane commands and state transitions before code edits."
        playbook.append(
            {
                "category": category,
                "evidence_count": count,
                "rule": rule,
            }
        )
    for file_path, count in sorted(
        memory.get("stats", {}).get("files", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        if count < 2:
            continue
        playbook.append(
            {
                "file": file_path,
                "evidence_count": count,
                "rule": f"Treat {file_path} as a hotspot and review existing findings before editing it again.",
            }
        )
    return playbook[:8]


def record_reflection(
    spec_slug: str,
    run_metadata: dict[str, Any],
    result: str,
    summary: str,
    findings: list[dict[str, Any]] | None = None,
) -> list[Path]:
    """
    Record a task run reflection into strategy memory.

    Captures reflection data including run metadata, results, summary, and findings.
    Updates both global and spec-scoped strategy memory with statistics and
    maintains a rolling history of the last 25 reflections. Automatically rebuilds
    the strategy playbook based on accumulated reflections.

    Args:
        spec_slug: Spec identifier for scoping the reflection
        run_metadata: Dictionary containing run metadata (id, task, role, etc.)
        result: Run result status (e.g., "success", "needs_changes", "blocked", "failed")
        summary: Text summary of the reflection
        findings: Optional list of finding dictionaries with category, severity, file

    Returns:
        List of paths to updated strategy memory files (global and spec)

    Example:
        >>> metadata = {"id": "run-123", "task": "task-1", "role": "developer"}
        >>> findings = [{"category": "bug", "severity": "high", "file": "src/main.py"}]
        >>> paths = record_reflection("my-spec", metadata, "success", "All tests passed", findings)
        >>> print(f"Updated {len(paths)} memory files")
        Updated 2 memory files
    """
    normalized = (
        normalize_findings(summary, findings)
        if findings or result in {"needs_changes", "blocked", "failed"}
        else []
    )
    updated_paths: list[Path] = []
    for scope in ["global", "spec"]:
        memory = load_strategy_memory(scope, spec_slug if scope == "spec" else None)
        stats = memory.setdefault(
            "stats",
            {
                "by_role": {},
                "by_result": {},
                "finding_categories": {},
                "severity": {},
                "files": {},
            },
        )
        increment_counter(stats.setdefault("by_role", {}), run_metadata.get("role", "unknown"))
        increment_counter(stats.setdefault("by_result", {}), result)
        for finding in normalized:
            increment_counter(stats.setdefault("finding_categories", {}), finding.get("category", "general"))
            increment_counter(stats.setdefault("severity", {}), finding.get("severity", "medium"))
            increment_counter(stats.setdefault("files", {}), finding.get("file", ""))
        reflection = {
            "at": now_stamp(),
            "run": run_metadata.get("id", ""),
            "task": run_metadata.get("task", ""),
            "role": run_metadata.get("role", ""),
            "result": result,
            "summary": summary,
            "findings": normalized,
            "recommended_actions": derive_strategy_actions(
                run_metadata.get("role", ""),
                result,
                normalized,
                stats,
            ),
        }
        reflections = memory.setdefault("reflections", [])
        reflections.append(reflection)
        memory["reflections"] = reflections[-25:]
        memory["playbook"] = rebuild_playbook(memory)
        updated_paths.append(save_strategy_memory(scope, memory, spec_slug if scope == "spec" else None))
    return updated_paths


def add_planner_note(
    spec_slug: str,
    title: str,
    content: str,
    category: str = "strategy",
    scope: str = "spec",
) -> Path:
    """
    Add a planner note to strategy memory.

    Planner notes are free-form annotations for tracking strategic decisions,
    observations, or guidance. Notes are timestamped and categorized, with the
    last 25 notes retained in memory. Notes can be scoped globally or to a
    specific spec.

    Args:
        spec_slug: Spec identifier for scoping the note
        title: Short title describing the note
        content: Detailed content of the note
        category: Category for organizing notes (default: "strategy")
        scope: Memory scope - "global" or "spec" (default: "spec")

    Returns:
        Path to the updated strategy memory file

    Example:
        >>> path = add_planner_note(
        ...     "my-spec",
        ...     "Architecture Decision",
        ...     "Use PostgreSQL for the primary database",
        ...     category="architecture"
        ... )
        >>> print(f"Note saved to {path}")
    """
    memory = load_strategy_memory(scope, spec_slug if scope == "spec" else None)
    notes = memory.setdefault("planner_notes", [])
    notes.append(
        {
            "at": now_stamp(),
            "title": title,
            "category": category,
            "content": content.strip(),
        }
    )
    memory["planner_notes"] = notes[-25:]
    return save_strategy_memory(scope, memory, spec_slug if scope == "spec" else None)


def strategy_summary(spec_slug: str) -> dict[str, Any]:
    """
    Generate a summary of strategy memory for a spec.

    Loads the strategy memory for the given spec and extracts the most relevant
    information including playbook entries, planner notes, recent reflections,
    and statistics.

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Dictionary containing:
            - updated_at: Last update timestamp
            - playbook: List of playbook rules with evidence
            - planner_notes: Last 5 planner notes with metadata
            - recent_reflections: Last 5 reflection entries
            - stats: Strategy statistics and metrics
    """
    spec_memory = load_strategy_memory("spec", spec_slug)
    recent = spec_memory.get("reflections", [])[-5:]
    return {
        "updated_at": spec_memory.get("updated_at", ""),
        "playbook": spec_memory.get("playbook", []),
        "planner_notes": spec_memory.get("planner_notes", [])[-5:],
        "recent_reflections": recent,
        "stats": spec_memory.get("stats", {}),
    }


def render_strategy_context(spec_slug: str) -> str:
    """
    Render strategy memory as formatted markdown for context injection.

    Generates a markdown representation of strategy memory for use in prompts
    and context windows. Includes playbook entries, planner notes, and recent
    reflections with their recommended actions.

    The output includes:
    - Playbook: Top 5 rules with evidence counts
    - Planner notes: Last 3 notes with titles and categories
    - Recent reflections: Last 3 reflections with outcomes and actions

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Formatted markdown string containing strategy context, or a message
        indicating no strategy memory has been recorded yet
    """
    summary = strategy_summary(spec_slug)
    lines = ["## Strategy memory", ""]
    playbook = summary.get("playbook", [])
    if playbook:
        lines.append("### Playbook")
        lines.append("")
        for item in playbook[:5]:
            target = item.get("category") or item.get("file") or "general"
            lines.append(f"- {target}: {item['rule']} (evidence={item['evidence_count']})")
        lines.append("")
    notes = summary.get("planner_notes", [])
    if notes:
        lines.append("### Planner notes")
        lines.append("")
        for note in notes[-3:]:
            lines.append(f"- {note['title']} [{note['category']}]")
            lines.append(f"  {note['content']}")
        lines.append("")
    reflections = summary.get("recent_reflections", [])
    if reflections:
        lines.append("### Recent reflections")
        lines.append("")
        for item in reflections[-3:]:
            lines.append(
                f"- {item['task']} / {item['role']} -> {item['result']}: {item['summary']}"
            )
            for action in item.get("recommended_actions", [])[:2]:
                lines.append(f"  action: {action}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("No strategy memory recorded yet.")
    return "\n".join(lines).strip()


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


def load_tasks(spec_slug: str) -> dict[str, Any]:
    """
    Load the tasks file for a spec.

    Reads and parses the tasks JSON file containing all tasks, their status,
    and metadata. Exits with an error if the tasks file doesn't exist.

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
    path = task_file(spec_slug)
    if not path.exists():
        raise SystemExit(f"missing task file: {path}")
    return read_json(path)


def task_lookup(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    """
    Look up a task by ID within a tasks dictionary.

    Searches through the tasks list to find a task with the matching ID.
    This is useful for retrieving full task details given only a task ID.

    Args:
        data: Tasks dictionary containing a "tasks" key with a list of task objects
        task_id: Unique identifier of the task to find

    Returns:
        Task dictionary containing all task details:
        - id: Unique task identifier (str)
        - title: Task title (str)
        - status: Task status (str)
        - ...additional task metadata

    Raises:
        SystemExit: If no task with the given ID is found
    """
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            return task
    raise SystemExit(f"unknown task: {task_id}")


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


def load_events(spec_slug: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Load events from the spec's event log.

    Reads the events.jsonl file and returns the most recent events.
    Events are stored in reverse chronological order (newest last),
    so the last N lines are retrieved.

    Args:
        spec_slug: Slug identifier for the spec
        limit: Maximum number of events to return (default: 20)

    Returns:
        List of event dictionaries, each containing:
        - "at": UTC timestamp string
        - "type": Event type identifier
        - "payload": Event-specific data dictionary

        Returns empty list if the event log doesn't exist.
    """
    events_path = spec_files(spec_slug)["events"]
    if not events_path.exists():
        return []
    with open(events_path, encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def load_fix_request(spec_slug: str) -> str:
    """
    Load the QA fix request markdown file for a spec.

    Reads the fix request markdown file that contains structured feedback
    for implementation revisions. Returns an empty string if the file doesn't exist.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Contents of the fix request markdown file, or empty string if not found

    Examples:
        >>> content = load_fix_request("my-feature")
        >>> print(content[:50])
        # QA Fix Request: task-001
    """
    path = spec_files(spec_slug)["qa_fix_request"]
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_fix_request_data(spec_slug: str) -> dict[str, Any]:
    """
    Load the QA fix request JSON data for a spec.

    Reads the structured JSON data that contains the fix request payload including
    task ID, result status, summary, and normalized findings. Returns a default
    empty structure if the file doesn't exist.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Dictionary containing fix request data with keys:
        - task: Task ID string
        - result: Review result status
        - summary: Reviewer summary text
        - finding_count: Number of findings
        - findings: List of normalized finding dictionaries
        Returns default empty structure if file not found.

    Examples:
        >>> data = load_fix_request_data("my-feature")
        >>> data["finding_count"]
        3
        >>> len(data["findings"])
        3
    """
    return read_json_or_default(
        spec_files(spec_slug)["qa_fix_request_json"],
        {"task": "", "result": "", "summary": "", "finding_count": 0, "findings": []},
    )


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


def format_fix_request_markdown(task_id: str, summary: str, result: str, findings: list[dict[str, Any]]) -> str:
    """
    Format a QA fix request as structured markdown.

    Generates a comprehensive markdown document containing review findings in a
    structured format suitable for developer review and implementation revisions.
    Includes a summary table, detailed findings with metadata, and retry policy.

    Args:
        task_id: Identifier for the task requiring fixes
        summary: High-level summary of the review feedback
        result: Review result status (e.g., "needs_changes", "blocked")
        findings: List of normalized finding dictionaries

    Returns:
        Formatted markdown string with sections:
        - Header with task ID and metadata
        - Summary section with overall feedback
        - Findings table with ID, severity, category, file, line, and title
        - Details section with full information for each finding
        - Retry policy section with guidance for implementation

    Examples:
        >>> findings = [
        ...     {
        ...         "id": "F1",
        ...         "title": "Add tests",
        ...         "severity": "high",
        ...         "category": "tests",
        ...         "file": "src/test.py",
        ...         "line": 42,
        ...         "end_line": 50,
        ...         "body": "Add unit tests for edge cases",
        ...         "suggested_fix": "Add tests in test suite",
        ...         "source_run": "run-123"
        ...     }
        ... ]
        >>> markdown = format_fix_request_markdown("task-001", "Tests needed", "needs_changes", findings)
        >>> print(markdown[:100])
        # QA Fix Request: task-001
        <BLANKLINE>
        - created_at: 20260309T120000Z
        - result: needs_changes
    """
    lines = [
        f"# QA Fix Request: {task_id}",
        "",
        f"- created_at: {now_stamp()}",
        f"- result: {result}",
        f"- finding_count: {len(findings)}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Findings",
        "",
        "| ID | Severity | Category | File | Line | Title |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        line_display = ""
        if finding.get("line") is not None:
            line_display = str(finding["line"])
            if finding.get("end_line") is not None and finding["end_line"] != finding["line"]:
                line_display = f"{line_display}-{finding['end_line']}"
        lines.append(
            f"| {finding['id']} | {finding['severity']} | {finding['category']} | "
            f"{finding.get('file', '')} | {line_display} | {finding['title']} |"
        )
    lines.extend(["", "## Details", ""])
    for finding in findings:
        lines.extend(
            [
                f"### {finding['id']}: {finding['title']}",
                "",
                f"- severity: {finding['severity']}",
                f"- category: {finding['category']}",
                f"- file: {finding.get('file', '')}",
                f"- line: {finding.get('line', '')}",
                f"- end_line: {finding.get('end_line', '')}",
                f"- suggested_fix: {finding.get('suggested_fix', '')}",
                f"- source_run: {finding.get('source_run', '')}",
                "",
                finding["body"],
                "",
            ]
        )
    lines.extend(
        [
            "## Retry policy",
            "",
            "- Read this file before retrying the implementation task.",
            "- Address findings in severity order where possible.",
            "- Change approach instead of repeating the same edits.",
            "- Leave a handoff note explaining what changed in the retry.",
            "",
        ]
    )
    return "\n".join(lines)


def write_fix_request(
    spec_slug: str,
    task_id: str,
    reviewer_summary: str,
    result: str,
    findings: list[dict[str, Any]] | None = None,
) -> Path:
    """
    Write a QA fix request to both markdown and JSON files.

    Creates structured fix request documentation by normalizing findings, formatting
    them as markdown, and saving both human-readable (markdown) and machine-readable
    (JSON) versions. Records an event in the spec's event log.

    Args:
        spec_slug: Slug identifier for the spec
        task_id: Identifier for the task requiring fixes
        reviewer_summary: High-level summary of the review feedback
        result: Review result status (e.g., "needs_changes", "blocked")
        findings: List of finding dictionaries from review, or None for a default finding

    Returns:
        Path to the written markdown fix request file

    Side Effects:
        - Creates/overwrites QA_FIX_REQUEST.md file in spec directory
        - Creates/overwrites QA_FIX_REQUEST.json file in spec directory
        - Records "qa.fix_request_created" event in spec's event log

    Examples:
        >>> findings = [
        ...     {"title": "Fix typo", "severity": "low", "category": "style"}
        ... ]
        >>> path = write_fix_request("my-feature", "task-001", "Minor fixes needed", "needs_changes", findings)
        >>> path.name
        'QA_FIX_REQUEST.md'
        >>> path.exists()
        True
    """
    path = spec_files(spec_slug)["qa_fix_request"]
    json_path = spec_files(spec_slug)["qa_fix_request_json"]
    normalized = normalize_findings(reviewer_summary, findings)
    payload = {
        "task": task_id,
        "result": result,
        "summary": reviewer_summary,
        "created_at": now_stamp(),
        "finding_count": len(normalized),
        "findings": normalized,
    }
    content = format_fix_request_markdown(task_id, reviewer_summary, result, normalized)
    content = "\n".join(
        [content]
    )
    path.write_text(content, encoding="utf-8")
    write_json(json_path, payload)
    record_event(
        spec_slug,
        "qa.fix_request_created",
        {"task": task_id, "result": result, "finding_count": len(normalized)},
    )
    return path


def clear_fix_request(spec_slug: str) -> None:
    """
    Remove QA fix request files for a spec.

    Deletes both the markdown and JSON fix request files if they exist.
    Records an event in the spec's event log if any files were removed.

    Args:
        spec_slug: Slug identifier for the spec

    Side Effects:
        - Deletes QA_FIX_REQUEST.md file if it exists
        - Deletes QA_FIX_REQUEST.json file if it exists
        - Records "qa.fix_request_cleared" event in spec's event log if any files were removed

    Examples:
        >>> clear_fix_request("my-feature")
        >>> # Files are removed if they existed
    """
    paths = [
        spec_files(spec_slug)["qa_fix_request"],
        spec_files(spec_slug)["qa_fix_request_json"],
    ]
    removed = False
    for path in paths:
        if path.exists():
            path.unlink()
            removed = True
    if removed:
        record_event(spec_slug, "qa.fix_request_cleared", {})


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


def save_tasks(spec_slug: str, data: dict[str, Any], *, reason: str = "task_state_updated") -> None:
    """
    Save task data for a spec and synchronize review state.

    Updates the task data with a timestamp, writes it to the task file,
    and triggers review state synchronization. The reason parameter allows
    tracking why the task state was updated.

    Args:
        spec_slug: Slug identifier for the spec
        data: Task data dictionary to save
        reason: Optional reason for task state update (default: "task_state_updated")
    """
    data["updated_at"] = now_stamp()
    write_json(task_file(spec_slug), data)
    sync_review_state(spec_slug, reason=reason)


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


def load_bmad_template(role: str) -> str:
    """
    Load a BMAD (Behavioral Model for Agent Development) template for a specific role.

    BMAD templates provide role-specific guidance and instructions for agents.
    Templates are stored as markdown files in the templates/bmad directory,
    with filenames matching the role name.

    Args:
        role: The role name to load the template for (e.g., "developer", "reviewer")

    Returns:
        The template content as a string, or a message indicating no template
        is configured for the requested role
    """
    path = BMAD_DIR / f"{role}.md"
    if not path.exists():
        return "No BMAD template configured for this role."
    return path.read_text(encoding="utf-8")


def native_resume_preview(agent: AgentSpec) -> list[str]:
    """
    Build command preview for native resume mode.

    Constructs the command line arguments needed to resume a previous session
    using the agent's native resume capability. Supports different resume modes:
    - "subcommand": Uses a dedicated resume subcommand (e.g., "claude resume")
    - "args": Passes resume arguments directly to the main command
    - Other modes: Returns empty list (no native resume)

    Args:
        agent: Agent specification containing resume configuration

    Returns:
        List of command arguments for native resume, or empty list if resume
        is not configured or mode is not supported. Includes "<prompt>" as
        a placeholder for the actual prompt content.

    Example:
        >>> agent = AgentSpec(
        ...     name="claude",
        ...     command="claude",
        ...     resume={"mode": "subcommand", "subcommand": "continue", "args": []}
        ... )
        >>> native_resume_preview(agent)
        ['claude', '--print', 'continue', '<prompt>']
    """
    if not agent.resume:
        return []
    mode = agent.resume.get("mode", "none")
    resume_args = list(agent.resume.get("args", []))
    if mode == "subcommand":
        return [agent.command, *agent.args, agent.resume.get("subcommand", "resume"), *resume_args, "<prompt>"]
    if mode == "args":
        return [agent.command, *agent.args, *resume_args, "<prompt>"]
    return []


def discover_cli_agent(name: str, command: str) -> dict[str, Any] | None:
    """
    Discover a CLI agent by checking command availability and capabilities.

    Attempts to locate the specified command on the system PATH and analyzes
    its help output to determine supported capabilities. This enables automatic
    detection of agent features like resume support and model selection flags.

    Detection capabilities:
    - resume: Checks for "resume" or "--continue" in help text
    - model_flag: Checks for "--model" or " -m," in help text

    Args:
        name: Identifier name for the agent (e.g., "claude", "codex")
        command: Executable command to search for (e.g., "claude", "codex")

    Returns:
        Dictionary containing discovered agent information with keys:
        - name: Agent identifier
        - protocol: Always "cli" for this function
        - command: The command string
        - path: Full path to the executable
        - capabilities: Dict of boolean flags (resume, model_flag)

        Returns None if the command is not found on PATH.

    Example:
        >>> agent = discover_cli_agent("claude", "claude")
        >>> if agent:
        ...     print(agent["path"])
        ...     print(agent["capabilities"]["resume"])
    """
    executable = shutil.which(command)
    if not executable:
        return None
    help_result = run_cmd([command, "--help"], check=False)
    help_text = (help_result.stdout or "") + (help_result.stderr or "")
    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }
    protocol = "cli"
    return {
        "name": name,
        "protocol": protocol,
        "command": command,
        "path": executable,
        "capabilities": capabilities,
    }


def discover_agents_registry() -> dict[str, Any]:
    """
    Discover all available agents from CLI and system configuration registry.

    Performs comprehensive agent discovery by:
    1. Checking for CLI-based agents (codex, claude) on the system PATH
    2. Loading additional agents from the system config registry (ACP protocol)

    CLI agents are discovered by probing for executable commands and their
    capabilities. Registry agents are loaded from the system configuration's
    registry.acp_agents section, which typically contains ACP (Agent Control
    Protocol) agents with custom transport configurations.

    The discovery results are cached to DISCOVERY_FILE for persistence and
    returned with metadata about when the discovery was performed.

    Returns:
        Dictionary containing:
        - discovered_at: ISO 8601 timestamp of when discovery was performed
        - agents: List of discovered agent dictionaries, each containing:
            - name: Agent identifier
            - protocol: "cli" or "acp"
            - command/path (for CLI agents)
            - transport (for ACP agents)
            - capabilities: Dict of supported features
        - system_config: Relevant sections from system config including:
            - memory: Memory configuration
            - models: Model profiles
            - tools: Tool configurations

    Side Effects:
        Writes discovery results to DISCOVERY_FILE (discovered_agents.json)

    Example:
        >>> registry = discover_agents_registry()
        >>> print(f"Found {len(registry['agents'])} agents")
        >>> for agent in registry['agents']:
        ...     print(f"  - {agent['name']} ({agent['protocol']})")
    """
    config = load_system_config()
    discovered = []
    for name, command in [("codex", "codex"), ("claude", "claude")]:
        item = discover_cli_agent(name, command)
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
        "discovered_at": now_stamp(),
        "agents": discovered,
        "system_config": {
            "memory": config.get("memory", {}),
            "models": config.get("models", {}),
            "tools": config.get("tools", {}),
        },
    }
    write_json(DISCOVERY_FILE, payload)
    return payload


def discovered_agent_to_config(agent: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a discovered agent registry entry into an Autoflow agent configuration.

    Converts agent discovery data into the standard Autoflow agent configuration format,
    handling both ACP (Agent Communication Protocol) agents and CLI agents. For CLI
    agents, configures resume behavior based on agent capabilities.

    Args:
        agent: Discovered agent metadata from the agent registry. Contains protocol,
            command, name, capabilities, and optional transport configuration.

    Returns:
        A dictionary with agent configuration including:
        - protocol: "acp" or "cli"
        - command: Command to run the agent
        - args: List of command arguments (typically empty)
        - transport: Transport config for ACP agents
        - resume: Resume configuration for CLI agents with resume capability
        - memory_scopes: List of memory scopes (defaults to ["spec"])
    """
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


def sync_discovered_agents(overwrite: bool = False) -> dict[str, Any]:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into agents.json, preserving existing
    agent configurations by default. Can optionally overwrite existing entries.
    Creates the agents file with default structure if it doesn't exist.

    Args:
        overwrite: If True, replace existing agent configurations with discovered
            ones. If False, preserve existing configurations and only add new agents.

    Returns:
        A dictionary containing sync results:
        - agents_file: Path to the agents.json file
        - added: List of agent names that were added or updated
        - total_agents: Total number of agents after sync
    """
    ensure_state()
    discovered = discover_agents_registry()
    existing = {"defaults": {"workspace": ".", "shell": "bash"}, "agents": {}}
    if AGENTS_FILE.exists():
        existing = read_json_or_default(AGENTS_FILE, existing)
        existing.setdefault("defaults", {"workspace": ".", "shell": "bash"})
        existing.setdefault("agents", {})
    merged = dict(existing["agents"])
    added = []
    for agent in discovered.get("agents", []):
        name = agent["name"]
        if name in merged and not overwrite:
            continue
        merged[name] = discovered_agent_to_config(agent)
        added.append(name)
    payload = {"defaults": existing["defaults"], "agents": merged}
    write_json(AGENTS_FILE, payload)
    return {
        "agents_file": str(AGENTS_FILE),
        "added": added,
        "total_agents": len(merged),
    }

# ============================================================================
# RUN METADATA CACHING STRATEGY
# ============================================================================
#
# Problem: The original implementation scanned ALL run directories in O(n) time
# for every call to run_metadata_iter(), active_runs_for_spec(), and
# task_run_history(). With many runs, this caused significant performance
# degradation, especially when these functions were called repeatedly.
#
# Solution: Implemented a lazy-loading cache indexed by spec_slug:
#
#   1. Cache Structure:
#      - _run_metadata_cache: dict[spec_slug, list[run_metadata]]
#      - _cache_loaded_specs: set[spec_slug] tracks which specs are cached
#
#   2. Lazy Loading:
#      - Runs are only loaded from disk when first requested
#      - Subsequent calls return cached data from memory (O(1) lookup)
#      - When loading runs for one spec, we opportunistically cache all
#        specs encountered during the filesystem scan (amortized O(1))
#
#   3. Cache Invalidation:
#      - Cache is invalidated by calling invalidate_run_cache()
#      - Called after creating new runs (create_run_record)
#      - This ensures cache consistency when runs are modified
#      - Invalidation is simple: clear all cached data (safe and correct)
#
#   4. Performance Impact:
#      - First call: O(n) filesystem scan (same as before)
#      - Subsequent calls: O(1) memory lookup (vs O(n) scan)
#      - Typical speedup: 2x+ for repeated calls
#
# ============================================================================

# Cache data structures
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


def run_metadata_iter() -> list[dict[str, Any]]:
    """Return all run metadata using a lazy-loaded cache.

    Performance Characteristics:
        - First call: O(n) filesystem scan to load all run metadata
        - Subsequent calls: O(m) where m = number of cached specs (typically O(1))
        - Previous uncached implementation: O(n) filesystem scan on EVERY call

    Cache Behavior:
        This function uses an in-memory cache indexed by spec_slug to avoid
        repeated O(n) filesystem scans. On first call, it loads all runs via
        _populate_run_cache(). Subsequent calls return the cached data directly
        from memory, which is much faster than scanning the filesystem.

        The cache is automatically invalidated when runs are created or modified
        (see invalidate_run_cache() in create_run_record()).

    Returns:
        A list of run metadata dictionaries, sorted by run directory name.
    """
    # Ensure all specs are loaded into cache (lazy-load on first call)
    _populate_run_cache()

    # Flatten the cache into a single list
    items = []
    for spec_runs in _run_metadata_cache.values():
        items.extend(spec_runs)

    # Sort by run id (the run id corresponds to the directory name)
    return sorted(items, key=lambda item: item.get("id", ""))


def active_runs_for_spec(spec_slug: str) -> list[dict[str, Any]]:
    """Return active runs for a spec using cached lookup.

    This function uses the lazy-loaded cache to avoid O(n) filesystem scans.
    It only loads runs for the requested spec, and subsequent calls return
    the cached data from memory.

    Args:
        spec_slug: The spec identifier to get active runs for.

    Returns:
        A list of run metadata dictionaries for the spec that are not completed.
    """
    # Lazy-load runs for this specific spec
    _populate_run_cache_for_spec(spec_slug)

    # Return cached runs for this spec, filtered by status
    return [
        item
        for item in _run_metadata_cache.get(spec_slug, [])
        if item.get("status") != "completed"
    ]


def task_run_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return run history for a task using cached lookup.

    This function uses the lazy-loaded cache to avoid O(n) filesystem scans.
    It only loads runs for the requested spec, and subsequent calls return
    the cached data from memory.

    Args:
        spec_slug: The spec identifier to get task run history for.
        task_id: The task identifier to get run history for.
        limit: Maximum number of history items to return (default: 5).

    Returns:
        A list of run metadata dictionaries for the task, sorted by created_at
        and limited to the last `limit` items.
    """
    # Lazy-load runs for this specific spec
    _populate_run_cache_for_spec(spec_slug)

    # Filter by task_id from cached data
    history = [
        item
        for item in _run_metadata_cache.get(spec_slug, [])
        if item.get("task") == task_id
    ]

    # Sort by created_at and return last `limit` items
    return sorted(history, key=lambda item: item.get("created_at", ""))[-limit:]


def latest_handoffs(spec_slug: str, limit: int = 3) -> list[Path]:
    """
    Get the most recent handoff markdown files for a spec.

    Handoffs contain context passed between agents when working on tasks.
    This function retrieves the latest handoff files, sorted chronologically,
    to provide recent context for continuation or review.

    Args:
        spec_slug: URL-friendly slug identifying the spec
        limit: Maximum number of handoff files to return (default: 3)

    Returns:
        List of paths to the most recent handoff markdown files,
        sorted oldest to newest. Returns empty list if no handoffs exist
        or the handoffs directory doesn't exist.
    """
    handoffs_dir = spec_files(spec_slug)["handoffs_dir"]
    if not handoffs_dir.exists():
        return []
    return sorted(handoffs_dir.glob("*.md"))[-limit:]


def worktree_context(spec_slug: str) -> str:
    """
    Generate environment context documentation for a spec's workspace mode.

    Creates a formatted markdown section explaining whether the spec uses an
    isolated git worktree or shares the main repository root. Provides critical
    rules and path information to guide agent behavior based on the workspace mode.

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Formatted markdown string containing environment context, including:
        - Current working directory path
        - Workspace mode (isolated worktree or shared root)
        - Critical rules for path usage and file operations
        - Parent repository path (if using worktree)
    """
    path = worktree_path(spec_slug)
    if not path.exists():
        return f"""## Environment Context

**Working Directory:** `{ROOT}`
**Spec Workspace Mode:** Shared repository root

No isolated git worktree is configured for this spec yet.
Use relative paths only.
"""
    return f"""## Environment Context

**Working Directory:** `{path}`
**Spec Workspace Mode:** Isolated git worktree
**Parent Repository:** `{ROOT}`

### Critical rules

1. Stay inside the worktree path above.
2. Do not edit files through absolute paths pointing at the parent repository.
3. Use relative paths from the worktree for all changes and git operations.
"""


def recovery_context(spec_slug: str, task_id: str) -> str:
    """
    Generate context about previous failed or blocked attempts for a task.

    Aggregates information from recent unsuccessful task runs to help agents
    understand what went wrong before and avoid repeating mistakes. Includes
    run IDs, roles, results, and summary text from up to 3 recent failures.

    Args:
        spec_slug: URL-friendly slug identifying the spec
        task_id: Unique identifier for the task

    Returns:
        Formatted text string containing:
        - Count of previous unsuccessful attempts
        - List of recent failed/blocked runs with:
            - Run ID
            - Role that executed the run
            - Result status (needs_changes, blocked, or failed)
            - Summary text (if available)
        Returns "No previous failed or blocked attempts..." if no failures exist.
    """
    history = task_run_history(spec_slug, task_id, limit=5)
    unsuccessful = [item for item in history if item.get("result") in {"needs_changes", "blocked", "failed"}]
    if not unsuccessful:
        return "No previous failed or blocked attempts recorded for this task."
    lines = [
        f"Previous unsuccessful attempts: {len(unsuccessful)}",
        "",
        "Recent outcomes:",
    ]
    for item in unsuccessful[-3:]:
        run_dir = RUNS_DIR / item["id"]
        summary_path = run_dir / "summary.md"
        summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
        lines.append(
            f"- {item['id']} ({item.get('role', 'unknown')} -> {item.get('result', 'unknown')})"
        )
        if summary_text:
            lines.append(f"  {summary_text.replace(chr(10), ' ')}")
    return "\n".join(lines)


def resume_context(run_id: str | None) -> str:
    """
    Generate context when resuming execution from a previous run.

    Retrieves metadata and summary information from a prior run to enable
    continuation of work. Provides agents with information about what role
    previously worked on the task, what result was achieved, how many attempts
    have been made, and what summary was recorded.

    Args:
        run_id: Unique identifier of the run to resume from, or None if no resume context

    Returns:
        Formatted text string containing:
        - Run ID being resumed
        - Previous role that executed the run
        - Previous result status
        - Attempt count so far
        - Summary text from the previous run (if available)
        Returns "No resume context." if run_id is None
        Returns "Requested resume source `{run_id}` was not found." if run doesn't exist
    """
    if not run_id:
        return "No resume context."
    run_dir = RUNS_DIR / run_id
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        return f"Requested resume source `{run_id}` was not found."
    metadata = read_json(metadata_path)
    summary_path = run_dir / "summary.md"
    summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    return "\n".join(
        [
            f"Resuming from run: {run_id}",
            f"Previous role: {metadata.get('role', '')}",
            f"Previous result: {metadata.get('result', 'unfinished')}",
            f"Attempt count so far: {metadata.get('attempt_count', 1)}",
            "",
            summary_text or "No previous summary recorded.",
        ]
    )


def parse_findings(args: argparse.Namespace) -> list[dict[str, Any]] | None:
    """
    Parse findings from command-line arguments.

    Findings can be provided either as a JSON string via --findings-json
    or as a file path via --findings-file. The JSON can be either a list
    of finding objects or a dict with a 'findings' key.

    Args:
        args: Parsed command-line arguments with optional findings_json
            and findings_file attributes

    Returns:
        List of finding dictionaries, or None if no findings provided

    Raises:
        json.JSONDecodeError: If the provided JSON is invalid
    """
    findings_json = getattr(args, "findings_json", "")
    findings_file = getattr(args, "findings_file", "")
    if findings_json:
        loaded = json.loads(findings_json)
        return loaded if isinstance(loaded, list) else loaded.get("findings", [])
    if findings_file:
        loaded = read_json(Path(findings_file))
        return loaded if isinstance(loaded, list) else loaded.get("findings", [])
    return None


def default_tasks() -> list[dict[str, Any]]:
    """
    Get the default task template for new specs.

    Returns a predefined list of tasks that form the core workflow for
    building an autonomous development harness, including workflow contract
    definition, task graph management, execution harness implementation,
    review gates, and maintenance hooks.

    Returns:
        List of task dictionaries with default workflow tasks. Each task
        contains id, title, status, depends_on, owner_role,
        acceptance_criteria, and notes fields
    """
    return [
        {
            "id": "T1",
            "title": "Define workflow contract and repository structure",
            "status": "todo",
            "depends_on": [],
            "owner_role": "spec-writer",
            "acceptance_criteria": [
                "Spec and control-plane directories exist.",
                "Workflow roles and artifacts are defined.",
            ],
            "notes": [],
        },
        {
            "id": "T2",
            "title": "Build task graph and lifecycle management",
            "status": "todo",
            "depends_on": ["T1"],
            "owner_role": "task-graph-manager",
            "acceptance_criteria": [
                "Tasks have explicit lifecycle states.",
                "The system can identify the next ready task.",
            ],
            "notes": [],
        },
        {
            "id": "T3",
            "title": "Implement bounded coding execution harness",
            "status": "todo",
            "depends_on": ["T2"],
            "owner_role": "implementation-runner",
            "acceptance_criteria": [
                "A run can target one task and one backend agent.",
                "Runs store prompts, metadata, and summaries.",
            ],
            "notes": [],
        },
        {
            "id": "T4",
            "title": "Add review gate and handoff artifacts",
            "status": "todo",
            "depends_on": ["T3"],
            "owner_role": "reviewer",
            "acceptance_criteria": [
                "Review is distinct from implementation.",
                "Review outcome can move tasks to done or needs_changes.",
            ],
            "notes": [],
        },
        {
            "id": "T5",
            "title": "Add maintenance and git workflow hooks",
            "status": "todo",
            "depends_on": ["T4"],
            "owner_role": "maintainer",
            "acceptance_criteria": [
                "The system can prepare isolated worktrees.",
                "Low-risk maintenance can be scheduled and audited.",
            ],
            "notes": [],
        },
    ]


def create_spec(args: argparse.Namespace) -> None:
    """
    Create a new spec directory with markdown, metadata, and initial task files.

    Creates a spec directory structure containing:
    - spec.md: Main specification document with title, summary, problem, goals, etc.
    - metadata.json: Spec metadata including slug, title, dates, and worktree info
    - handoff.md: Handoff notes for role transitions
    - tasks.json: Initial task list with default tasks
    - review_state.json: Initial review state
    - handoffs/: Directory for role handoff notes

    Args:
        args: Namespace containing spec creation parameters:
            - title: Spec title
            - summary: Brief description of the spec
            - slug: Optional URL-friendly slug (auto-generated from title if not provided)

    Raises:
        SystemExit: If a spec with the same slug already exists

    Side Effects:
        Creates spec directory and all initial files
        Records a spec.created event
    """
    ensure_state()
    slug = slugify(args.slug or args.title)
    files = spec_files(slug)
    if files["spec"].exists():
        raise SystemExit(f"spec already exists: {slug}")
    files["dir"].mkdir(parents=True, exist_ok=True)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    spec_markdown = f"""# {args.title}

## Summary

{args.summary}

## Problem

Describe the problem this system is solving.

## Goals

- Build a reliable autonomous development harness.
- Keep orchestration separate from model-specific execution.
- Make every run resumable and auditable.

## Non-goals

- Fully unsupervised production deploys in v1.
- Vendor lock-in to a single coding model.

## Constraints

- Use explicit specs and task artifacts.
- Support `codex` and `claude` style CLIs.
- Support background execution with `tmux`.
- Require review before marking coding work complete.
- Prefer isolated git worktrees for implementation runs.

## Acceptance Criteria

- A spec-driven task graph exists.
- Runs can be created from roles and agent mappings.
- Review is a separate step from implementation.
- Git workflow hooks can prepare isolated task branches.
"""
    metadata = {
        "slug": slug,
        "title": args.title,
        "summary": args.summary,
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
        "status": "draft",
        "worktree": {
            "path": "",
            "branch": worktree_branch(slug),
            "base_branch": detect_base_branch(),
        },
    }
    handoff = "# Handoff\n\nInitial spec created. Next role should refine scope and derive tasks.\n"
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    files["handoff"].write_text(handoff, encoding="utf-8")
    write_json(files["metadata"], metadata)
    save_review_state(slug, review_state_default())
    if not task_file(slug).exists():
        write_json(
            task_file(slug),
            {
                "spec_slug": slug,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
    record_event(slug, "spec.created", {"title": args.title})
    print(str(files["dir"]))


def list_tasks(args: argparse.Namespace) -> None:
    """
    List all tasks for a spec in JSON format.

    Retrieves the task list for a given spec and prints it as formatted JSON.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier

    Side Effects:
        Prints JSON task list to stdout
    """
    tasks = load_tasks(args.spec)
    print_json(tasks)


def next_task_data(spec_slug: str, role: str | None = None) -> dict[str, Any] | None:
    """
    Find the next available task for a given role.

    Searches for a task that is:
    - For non-reviewer roles: status is "todo" or "needs_changes", matches the role if specified,
      and has all dependencies completed
    - For reviewer role: status is "in_review"

    Args:
        spec_slug: Spec slug identifier
        role: Optional role filter (e.g., "frontend", "backend"). If None, returns any
            available task. If "reviewer", returns tasks in review status.

    Returns:
        Task dictionary if an available task is found, None otherwise

    Side Effects:
        None
    """
    tasks = load_tasks(spec_slug)
    for task in tasks.get("tasks", []):
        if role == "reviewer":
            if task["status"] != "in_review":
                continue
        else:
            if task["status"] not in {"todo", "needs_changes"}:
                continue
            if role and task["owner_role"] != role:
                continue
        blocked = False
        for dep in task.get("depends_on", []):
            dep_task = task_lookup(tasks, dep)
            if dep_task["status"] != "done":
                blocked = True
                break
        if not blocked:
            return task
    return None


def next_task(args: argparse.Namespace) -> None:
    """
    Print the next available task for a spec in JSON format.

    Retrieves and displays the next available task for a given spec and role.
    If no task is available, prints an empty JSON object.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - role: Optional role filter (e.g., "frontend", "backend", "reviewer")

    Side Effects:
        Prints task data as JSON to stdout, or {} if no task is available
    """
    task = next_task_data(args.spec, args.role)
    if not task:
        print("{}")
        return
    print_json(task)


def set_task_status(args: argparse.Namespace) -> None:
    """
    Set the status of a task within a spec.

    Updates the task's status field, adds a note with timestamp, saves the
    updated tasks data, records an event, and prints the updated task as JSON.

    Valid statuses: todo, in_progress, in_review, needs_changes, blocked, done

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier to update
            - status: New status value (must be in VALID_TASK_STATUSES)
            - note: Optional note to add (defaults to status change message)

    Raises:
        SystemExit: If the provided status is not valid
    """
    if args.status not in VALID_TASK_STATUSES:
        raise SystemExit(f"invalid status: {args.status}")
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = args.status
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or f"status set to {args.status}"}
    )
    save_tasks(args.spec, data, reason="task_status_updated")
    record_event(args.spec, "task.status_updated", {"task": args.task, "status": args.status})
    print_json(task)


def write_handoff(
    spec_slug: str,
    task_id: str,
    role: str,
    summary: str,
    next_role: str,
    result: str,
) -> Path:
    """
    Write a handoff document for a task.

    Creates a timestamped handoff markdown file in the spec's handoffs directory
    and updates the current handoff file. The handoff includes metadata (role,
    next_role, result, timestamp) and a summary section.

    Args:
        spec_slug: Spec identifier (slug or ID)
        task_id: Task identifier for the handoff
        role: Current role (who is handing off)
        summary: Summary of work completed or context for next role
        next_role: Next role to take over the task
        result: Result status or outcome of the current role's work

    Returns:
        Path to the created handoff markdown file
    """
    files = spec_files(spec_slug)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    handoff_path = files["handoffs_dir"] / f"{now_stamp()}-{task_id}-{slugify(role)}.md"
    handoff_text = "\n".join(
        [
            f"# Handoff: {task_id}",
            "",
            f"- role: {role}",
            f"- next_role: {next_role}",
            f"- result: {result}",
            f"- created_at: {now_stamp()}",
            "",
            "## Summary",
            "",
            summary,
            "",
        ]
    )
    handoff_path.write_text(handoff_text, encoding="utf-8")
    files["handoff"].write_text(handoff_text, encoding="utf-8")
    record_event(spec_slug, "handoff.created", {"task": task_id, "role": role, "result": result})
    return handoff_path


def create_handoff(args: argparse.Namespace) -> None:
    """
    Create a handoff document from CLI arguments.

    Command-line interface wrapper for write_handoff(). Extracts handoff
    parameters from args namespace, creates the handoff document, and
    prints the resulting file path.

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier for the handoff
            - role: Current role handing off
            - summary: Summary of work completed
            - next_role: Next role to receive the handoff
            - result: Result status of current work
    """
    path = write_handoff(args.spec, args.task, args.role, args.summary, args.next_role, args.result)
    print(str(path))


def approve_spec(args: argparse.Namespace) -> None:
    """
    Approve a spec and record approval metadata.

    Marks the spec as approved, capturing the approver's identity, approval timestamp,
    and a hash of the spec content at the time of approval. Increments the review
    count and clears any previous invalidation status. Records the approval in the
    event log and displays the updated review status.

    The spec hash ensures that if the spec content changes after approval, the
    approval can be detected as invalid.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to approve
            - approved_by: Username or identifier of the approver

    Side Effects:
        - Updates review_state.json with approval information
        - Appends approval event to events.jsonl
        - Prints review status summary as JSON to stdout
    """
    state = load_review_state(args.spec)
    state["approved"] = True
    state["approved_by"] = args.approved_by
    state["approved_at"] = now_stamp()
    state["spec_hash"] = compute_spec_hash(args.spec)
    state["review_count"] = state.get("review_count", 0) + 1
    state["invalidated_at"] = ""
    state["invalidated_reason"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.approved", {"approved_by": args.approved_by})
    print_json(review_status_summary(args.spec))


def invalidate_review(args: argparse.Namespace) -> None:
    """
    Invalidate a spec's approval status.

    Marks a previously approved spec as no longer approved, recording the invalidation
    timestamp, reason for invalidation, and clearing the spec hash. This is typically
    used when the spec has changed in a way that requires re-review, or when an
    approval needs to be rescinded due to new information or requirements.

    The spec hash is cleared to ensure that the approval is no longer considered valid,
    even if the spec content happens to match the previous hash.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to invalidate
            - reason: Explanation for why the approval is being invalidated

    Side Effects:
        - Updates review_state.json with invalidation information
        - Appends invalidation event to events.jsonl
        - Prints review status summary as JSON to stdout
    """
    state = load_review_state(args.spec)
    state["approved"] = False
    state["invalidated_at"] = now_stamp()
    state["invalidated_reason"] = args.reason
    state["spec_hash"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.invalidated", {"reason": args.reason})
    print_json(review_status_summary(args.spec))


def show_review_status(args: argparse.Namespace) -> None:
    """
    Display the current review status for a spec.

    Outputs a comprehensive summary of the spec's review state, including approval
    status, validity, timestamps, reviewer information, and feedback counts. The
    status is synchronously computed to check for spec changes since approval.

    The output includes whether the spec is approved, whether the approval is still
    valid (i.e., the spec hasn't changed), the number of reviews completed, and
    the number of feedback items received.

    Args:
        args: Namespace containing the following attributes:
            - spec: Slug identifier for the spec to check

    Side Effects:
        - Prints review status summary as JSON to stdout

    Output Format:
        JSON object with the following keys:
            - approved: Whether the spec is currently approved
            - valid: Whether approval is still valid (approved and hash matches)
            - approved_by: Username of approver (if approved)
            - approved_at: Timestamp of approval (if approved)
            - review_count: Number of reviews completed
            - feedback_count: Number of feedback items
            - spec_changed: Whether spec has changed since approval
            - invalidated_at: Timestamp when approval was invalidated (if applicable)
            - invalidated_reason: Reason for invalidation (if applicable)
    """
    print_json(review_status_summary(args.spec))


def build_prompt(
    spec_slug: str,
    role: str,
    task_id: str | None,
    agent: AgentSpec,
    resume_from: str | None = None,
) -> str:
    """
    Build a comprehensive execution prompt for an AI agent.

    Assembles all context needed for an AI agent to execute a task, including
    the spec definition, task details, agent configuration, memory context,
    strategy context, review state, recovery information, resume context,
    QA fix requests, and recent handoffs.

    The prompt is structured to provide the agent with complete situational
    awareness and all necessary metadata to perform its role effectively.

    Args:
        spec_slug: Slug identifier for the spec to execute
        role: Role name the agent should assume (e.g., "developer", "reviewer")
        task_id: Specific task ID to execute, or None to auto-select next task
        agent: Agent specification with configuration, tools, and memory scopes
        resume_from: Optional run ID to resume from for recovery

    Returns:
        Complete prompt string with all context sections for agent execution

    Raises:
        SystemExit: If the specified spec does not exist
    """
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id) if task_id else next_task_data(spec_slug, role)
    review_summary = review_status_summary(spec_slug)
    fix_request = load_fix_request(spec_slug)
    fix_request_data = load_fix_request_data(spec_slug)
    memory_context = load_memory_context(spec_slug, agent.memory_scopes)
    strategy_context = render_strategy_context(spec_slug)
    handoff_sections = []
    for handoff_path in latest_handoffs(spec_slug):
        handoff_sections.append(f"### {handoff_path.name}\n")
        handoff_sections.append(handoff_path.read_text(encoding="utf-8"))
    recovery = recovery_context(spec_slug, selected_task["id"]) if selected_task else "No task selected."
    return "\n".join(
        [
            f"Role: {role}",
            f"Spec slug: {spec_slug}",
            f"Task id: {selected_task['id'] if selected_task else 'none'}",
            "",
            "Read the repository state and execute the role carefully.",
            "Follow the selected task acceptance criteria.",
            "Keep changes scoped and leave a concise handoff summary.",
            "",
            "## Backend configuration",
            json.dumps(
                sanitize_dict(
                    {
                        "agent": agent.name,
                        "protocol": agent.protocol,
                        "command": agent.command,
                        "model": agent.model,
                        "model_profile": agent.model_profile,
                        "tools": agent.tools or [],
                        "tool_profile": agent.tool_profile,
                        "memory_scopes": agent.memory_scopes or [],
                        "native_resume_supported": bool(agent.resume),
                        "transport": agent.transport or {},
                    }
                ),
                indent=2,
                ensure_ascii=True,
            ),
            "",
            "## BMAD operating frame",
            load_bmad_template(role),
            "",
            worktree_context(spec_slug),
            "",
            "## Memory context",
            memory_context,
            "",
            strategy_context,
            "",
            "## Review state",
            json.dumps(review_summary, indent=2, ensure_ascii=True),
            "",
            "## Recovery context",
            recovery,
            "",
            "## Resume context",
            resume_context(resume_from),
            "",
            "## QA fix request (structured)",
            json.dumps(fix_request_data, indent=2, ensure_ascii=True),
            "",
            "## QA fix request (markdown)",
            fix_request or "No QA fix request present.",
            "",
            "## Spec",
            files["spec"].read_text(encoding="utf-8"),
            "",
            "## Selected task",
            json.dumps(selected_task, indent=2, ensure_ascii=True) if selected_task else "{}",
            "",
            "## Full task graph",
            json.dumps(tasks, indent=2, ensure_ascii=True),
            "",
            "## Recent handoffs",
            "\n".join(handoff_sections) if handoff_sections else "No handoffs yet.",
        ]
    )


def create_run_record(
    spec_slug: str,
    role: str,
    agent_name: str,
    task_id: str,
    branch: str | None = None,
    resume_from: str | None = None,
) -> Path:
    """
    Create a new run record directory with all necessary files.

    Creates a unique run directory with timestamp-based ID, generates the agent prompt,
    creates the execution script, and writes run metadata. The run ID is formatted as:
    {timestamp}-{role}-{spec_slug}-{task_id}[-{suffix}] if duplicates exist.

    Args:
        spec_slug: Slug identifier for the spec
        role: Role executing the run (e.g., "implementation-runner", "reviewer")
        agent_name: Name of the agent to use for execution
        task_id: ID of the task to execute
        branch: Git branch name (defaults to "codex/{spec_slug}-{task_id}")
        resume_from: Optional run ID to resume from

    Returns:
        Path to the created run directory

    Raises:
        SystemExit: If run directory creation fails (already exists after suffix attempts)
        KeyError: If agent_name is not found in agents configuration
    """
    agents = load_agents()
    agent = agents[agent_name]
    run_id_base = f"{now_stamp()}-{slugify(role)}-{slugify(spec_slug)}-{slugify(task_id)}"
    run_id = run_id_base
    run_dir = RUNS_DIR / run_id
    suffix = 1
    while run_dir.exists():
        run_id = f"{run_id_base}-{suffix}"
        run_dir = RUNS_DIR / run_id
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(
        build_prompt(spec_slug, role, task_id, agent, resume_from=resume_from),
        encoding="utf-8",
    )
    branch = branch or f"codex/{slugify(spec_slug)}-{slugify(task_id)}"
    target_workdir = worktree_path(spec_slug) if worktree_path(spec_slug).exists() else ROOT
    command = [agent.command, *agent.args, str(prompt_path)]
    run_json_path = run_dir / "run.json"
    run_script = run_dir / "run.sh"
    run_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(target_workdir))}",
                f"exec {shlex.quote(str(ROOT / 'scripts' / 'run-agent.sh'))} {shlex.quote(agent_name)} {shlex.quote(str(prompt_path))} {shlex.quote(str(run_json_path))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    summary_path = run_dir / "summary.md"
    summary_path.write_text("# Run Summary\n\nFill after execution.\n", encoding="utf-8")
    os.chmod(run_script, 0o755)
    metadata = {
        "id": run_id,
        "spec": spec_slug,
        "task": task_id,
        "role": role,
        "agent": agent_name,
        "branch": branch,
        "workdir": str(target_workdir),
        "created_at": now_stamp(),
        "command_preview": command,
        "status": "created",
        "attempt_count": len(task_run_history(spec_slug, task_id)) + 1,
        "resume_from": resume_from or "",
        "resume_command": f"python3 scripts/autoflow.py resume-run --run {run_id}",
        "native_resume_supported": bool(agent.resume),
        "native_resume_command_preview": native_resume_preview(agent),
        "agent_config": agent.to_dict(),
        "retry_policy": {
            "max_automatic_attempts": 3,
            "requires_fix_request_after_review_failure": True,
        },
    }
    write_json(run_json_path, metadata)
    record_event(spec_slug, "run.created", {"run": run_id, "task": task_id, "role": role})
    invalidate_run_cache()
    return run_dir


def create_run(args: argparse.Namespace) -> None:
    """
    Create a new run for task execution.

    Validates the agent and spec review status, selects the appropriate task,
    updates task status to in_progress, and creates a run record. If no task
    is specified, automatically selects the next ready task for the role.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - role: Role executing the run
            - agent: Agent name to use
            - task: Optional task ID (auto-selects if not provided)
            - branch: Optional git branch name
            - resume_from: Optional run ID to resume from

    Raises:
        SystemExit: If agent is unknown, spec review is invalid, no ready task exists,
                    or task is not in a runnable state
    """
    ensure_state()
    agents = load_agents()
    if args.agent not in agents:
        raise SystemExit(f"unknown agent: {args.agent}")
    review_summary = review_status_summary(args.spec)
    if args.role in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        raise SystemExit(
            "spec review approval is not valid; approve the current planning contract before implementation"
        )
    chosen_task = args.task
    if not chosen_task:
        next_candidate = next_task_data(args.spec, args.role)
        if not next_candidate:
            raise SystemExit("no ready task for this role")
        chosen_task = next_candidate["id"]
    tasks = load_tasks(args.spec)
    task = task_lookup(tasks, chosen_task)
    expected_role = "reviewer" if task["status"] == "in_review" and args.role == "reviewer" else task["owner_role"]
    if expected_role != args.role:
        raise SystemExit(f"task {chosen_task} belongs to role {task['owner_role']}, not {args.role}")
    if task["status"] not in {"todo", "needs_changes", "in_progress", "in_review"}:
        raise SystemExit(f"task {chosen_task} is not runnable from status {task['status']}")
    task["status"] = "in_progress"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": f"run pending for role {args.role}"}
    )
    save_tasks(args.spec, tasks, reason="task_status_updated")
    run_dir = create_run_record(
        args.spec,
        args.role,
        args.agent,
        chosen_task,
        branch=args.branch,
        resume_from=getattr(args, "resume_from", None),
    )
    print(str(run_dir))


def resume_run(args: argparse.Namespace) -> None:
    """
    Resume a previous run by creating a new run record.

    Creates a new run that resumes from a previous run, preserving the original
    spec, role, agent, and task configuration. The new run is linked to the
    original run via the resume_from parameter.

    Args:
        args: Namespace with attributes:
            - run: Run ID to resume from

    Raises:
        SystemExit: If run ID is unknown or spec review is invalid
    """
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    review_summary = review_status_summary(metadata["spec"])
    if metadata["role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        raise SystemExit(
            "spec review approval is not valid; approve the current planning contract before resuming implementation"
        )
    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"])
    task["status"] = "in_progress"
    task.setdefault("notes", []).append({"at": now_stamp(), "note": f"retry created from {args.run}"})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated")
    new_run = create_run_record(
        metadata["spec"],
        metadata["role"],
        metadata["agent"],
        metadata["task"],
        branch=metadata.get("branch"),
        resume_from=args.run,
    )
    record_event(metadata["spec"], "run.resumed", {"from": args.run, "task": metadata["task"]})
    print(str(new_run))


def complete_run(args: argparse.Namespace) -> None:
    """
    Mark a run as completed and update task status.

    Processes the completion of a run by:
    - Updating run metadata with result and completion time
    - Updating task status based on run result
    - Recording findings and generating fix requests if needed
    - Capturing reflections in strategy memory
    - Writing handoff notes for the next role
    - Recording completion events

    Args:
        args: Namespace with attributes:
            - run: Run ID to complete
            - result: Run result ("success", "needs_changes", "blocked", "failed")
            - summary: Optional completion summary
            - findings: Optional findings data

    Raises:
        SystemExit: If result is invalid or run ID is unknown
    """
    if args.result not in RUN_RESULTS:
        raise SystemExit(f"invalid result: {args.result}")
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    findings = parse_findings(args)
    metadata["status"] = "completed"
    metadata["result"] = args.result
    metadata["completed_at"] = now_stamp()
    metadata["findings_count"] = len(findings or [])
    write_json(metadata_path, metadata)
    summary = args.summary or f"Run {args.run} completed with result {args.result}."
    (run_dir / "summary.md").write_text(f"# Run Summary\n\n{summary}\n", encoding="utf-8")

    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"])
    if metadata["role"] == "reviewer":
        next_status = "done" if args.result == "success" else args.result
    elif args.result == "success":
        next_status = "in_review"
    else:
        next_status = args.result
    status_map = {
        "success": next_status,
        "needs_changes": "needs_changes",
        "blocked": "blocked",
        "failed": "blocked",
    }
    task["status"] = status_map[args.result]
    task.setdefault("notes", []).append({"at": now_stamp(), "note": summary})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated")
    next_role = "reviewer" if metadata["role"] != "reviewer" else task["owner_role"]
    fix_request_path = ""
    if metadata["role"] == "reviewer" and args.result in {"needs_changes", "blocked", "failed"}:
        fix_request_path = str(write_fix_request(metadata["spec"], metadata["task"], summary, args.result, findings=findings))
    if metadata["role"] == "implementation-runner" and args.result == "success":
        clear_fix_request(metadata["spec"])
    strategy_paths = record_reflection(metadata["spec"], metadata, args.result, summary, findings=findings)
    memory_cfg = load_system_config().get("memory", {})
    if memory_cfg.get("enabled", True) and memory_cfg.get("auto_capture_run_results", True):
        for scope in metadata.get("agent_config", {}).get("memory_scopes") or ["spec"]:
            append_memory(
                scope,
                f"role={metadata['role']}\nresult={args.result}\nsummary={summary}",
                spec_slug=metadata["spec"],
                title=f"{metadata['task']} {metadata['role']} {args.result}",
            )
    handoff_path = write_handoff(
        metadata["spec"], metadata["task"], metadata["role"], summary, next_role, args.result
    )
    record_event(
        metadata["spec"],
        "run.completed",
        {
            "run": metadata["id"],
            "task": metadata["task"],
            "role": metadata["role"],
            "result": args.result,
            "fix_request": fix_request_path,
        },
    )
    print(
        json.dumps(
            {
                "run": metadata["id"],
                "task_status": task["status"],
                "handoff": str(handoff_path),
                "fix_request": fix_request_path,
                "strategy_memory": [str(path) for path in strategy_paths],
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def cancel_run(args: argparse.Namespace) -> None:
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    if metadata["status"] == "completed":
        raise SystemExit(f"cannot cancel run with status {metadata['status']}")
    reason = args.reason or f"Run {args.run} cancelled."
    metadata["status"] = "cancelled"
    metadata["cancelled_at"] = now_stamp()
    write_json(metadata_path, metadata)
    (run_dir / "summary.md").write_text(f"# Run Summary\n\n{reason}\n", encoding="utf-8")

    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"])
    task["status"] = "todo"
    task.setdefault("notes", []).append({"at": now_stamp(), "note": reason})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated")
    record_event(
        metadata["spec"],
        "run.cancelled",
        {
            "run": metadata["id"],
            "task": metadata["task"],
            "role": metadata["role"],
            "reason": reason,
        },
    )
    print(
        json.dumps(
            {
                "run": metadata["id"],
                "task_status": task["status"],
                "cancelled_at": metadata["cancelled_at"],
                "reason": reason,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def show_task_history(args: argparse.Namespace) -> None:
    """
    Display execution history for a specific task.

    Retrieves and prints all runs associated with the given spec and task,
    sorted by creation timestamp. Output is formatted as indented JSON.

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec
            - task: ID of the task to get history for
    """
    print_json(task_run_history(args.spec, args.task))


def show_events(args: argparse.Namespace) -> None:
    """
    Display event log for a spec.

    Retrieves and prints the most recent events from the spec's event log,
    formatted as indented JSON. Events are stored in reverse chronological
    order (newest last).

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec
            - limit: Maximum number of events to return (default: 20)
    """
    print_json(load_events(args.spec, args.limit))


def show_fix_request(args: argparse.Namespace) -> None:
    """
    Display QA fix request data for a spec.

    Retrieves and prints the structured JSON data containing the fix request
    payload including task ID, result status, summary, and normalized findings.
    Output is formatted as indented JSON.

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec

    Notes:
        Returns a default empty structure if the fix request file doesn't exist.
    """
    print_json(load_fix_request_data(args.spec))


def create_fix_request_cmd(args: argparse.Namespace) -> None:
    """
    Create a QA fix request artifact for a spec and task.

    Parses QA findings from command-line arguments and writes a structured
    fix request file to the spec's review directory. The file captures
    issues that must be addressed before the spec can be approved.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - task: Task ID requiring fixes
            - summary: Brief summary of issues
            - result: QA result status (e.g., "needs_changes")
            - findings_json: JSON string with findings (optional)
            - findings_file: Path to JSON file with findings (optional)

    Side Effects:
        - Creates .autoflow/specs/{spec}/QA_FIX_REQUEST.md
        - Records event in spec's event log
    """
    findings = parse_findings(args)
    path = write_fix_request(args.spec, args.task, args.summary, args.result, findings=findings)
    print(str(path))


def show_system_config(_: argparse.Namespace) -> None:
    """
    Display the current system configuration.

    Prints the system configuration as formatted JSON. The configuration is
    loaded from system.json (if it exists) and merged with defaults from
    the system config template.

    The output includes:
    - memory: Memory settings and file paths
    - models: Model profile configurations
    - tools: Tool profile configurations
    - registry: Registry settings
    """
    print_json(load_system_config())


def init_system_config(_: argparse.Namespace) -> None:
    """
    Initialize the system configuration file.

    Creates the system configuration file at .autoflow/system.json with default
    values. If the file already exists, this command does nothing (it will not
    overwrite existing configuration).

    The configuration is loaded from config/system.example.json if it exists,
    otherwise uses hardcoded defaults. The configuration includes:
    - memory: Memory settings and file paths
    - models: Model profile configurations
    - tools: Tool profile configurations
    - registry: Registry settings

    Prints the path to the configuration file after initialization.
    """
    ensure_state()
    if not SYSTEM_CONFIG_FILE.exists():
        write_json(SYSTEM_CONFIG_FILE, system_config_default())
    print(str(SYSTEM_CONFIG_FILE))


def discover_agents_cmd(_: argparse.Namespace) -> None:
    """
    Discover and display all available agents.

    Performs comprehensive agent discovery by checking for CLI-based agents
    (codex, claude) on the system PATH and loading additional agents from the
    system configuration registry (ACP protocol).

    The discovery results are printed as JSON containing:
    - discovered_at: ISO 8601 timestamp of when discovery was performed
    - agents: List of discovered agent dictionaries with name, protocol,
      command/path, transport, and capabilities
    - system_config: Relevant sections from system config including memory,
      models, and tools configurations

    The discovery results are also cached to .autoflow/discovered_agents.json
    for persistence and use by other commands.
    """
    print_json(discover_agents_registry())


def sync_agents_cmd(args: argparse.Namespace) -> None:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into .autoflow/agents.json,
    preserving existing agent configurations by default. Can optionally
    overwrite existing entries when the --overwrite flag is provided.

    Creates the agents file with default structure if it doesn't exist.

    The sync results are printed as JSON containing:
    - agents_file: Path to the agents.json file
    - added: List of agent names that were added or updated
    - total_agents: Total number of agents after sync

    Args:
        args: Namespace with optional overwrite attribute (bool). If True,
            replaces existing agent configurations with discovered ones.
            If False, preserves existing configurations and only adds new agents.
    """
    print_json(sync_discovered_agents(overwrite=args.overwrite))


def write_memory_cmd(args: argparse.Namespace) -> None:
    """
    Append content to a memory file.

    Creates a timestamped memory entry in either global or spec-scoped memory.
    The entry is written as a markdown section with an optional title. If no
    title is provided, a timestamp is used.

    Args:
        args: Namespace containing:
            - scope: Memory scope ("global" or "spec")
            - spec: Optional spec slug for spec-scoped memory
            - title: Optional title for the memory entry
            - content: Content to append to memory

    Output:
        Prints the path to the updated memory file
    """
    path = append_memory(args.scope, args.content, spec_slug=args.spec, title=args.title)
    print(str(path))


def show_memory_cmd(args: argparse.Namespace) -> None:
    """
    Display stored memory content.

    Retrieves and displays the content of a memory file. The memory file
    is determined by the scope (global or spec) and optional spec slug.

    Args:
        args: Namespace containing:
            - scope: Memory scope ("global" or "spec")
            - spec: Optional spec slug for spec-scoped memory

    Output:
        Prints the memory file contents, or empty string if file doesn't exist
    """
    path = memory_file(args.scope, args.spec)
    if not path.exists():
        print("")
        return
    print(path.read_text(encoding="utf-8"))


def show_strategy_cmd(args: argparse.Namespace) -> None:
    """
    Display accumulated strategy memory for a spec.

    Shows the complete strategy summary including playbook entries,
    planner notes, recent reflections, and statistics. This provides
    a comprehensive view of all strategic decisions and learnings
    accumulated for a spec.

    Args:
        args: Namespace containing:
            - spec: Spec slug to show strategy for

    Output:
        Prints JSON-formatted strategy summary with keys:
            - updated_at: Last update timestamp
            - playbook: List of playbook rules with evidence
            - planner_notes: Last 5 planner notes with metadata
            - recent_reflections: Last 5 reflection entries
            - stats: Strategy statistics and metrics
    """
    print_json(strategy_summary(args.spec))


def add_planner_note_cmd(args: argparse.Namespace) -> None:
    """
    Add a planner note to strategy memory.

    Creates a timestamped, categorized planner note for tracking strategic
    decisions, observations, or guidance. Notes are retained in memory
    with the last 25 notes preserved. Can be scoped globally or to a
    specific spec.

    Args:
        args: Namespace containing:
            - spec: Spec slug for scoping the note
            - title: Short title describing the note
            - content: Detailed content of the note
            - category: Category for organizing notes (default: "strategy")
            - scope: Memory scope - "global" or "spec" (default: "spec")

    Output:
        Prints the path to the updated strategy memory file
    """
    path = add_planner_note(args.spec, args.title, args.content, category=args.category, scope=args.scope)
    print(str(path))


def taskmaster_payload(spec_slug: str) -> dict[str, Any]:
    """
    Build Taskmaster-compatible export payload from spec tasks.

    Transforms Autoflow task data into the Taskmaster JSON format, mapping
    Autoflow field names to Taskmaster conventions. The payload includes
    project metadata and a list of tasks with their dependencies.

    Args:
        spec_slug: Slug identifier of the spec to export

    Returns:
        Dictionary containing:
        - project: Spec slug identifier
        - exported_at: ISO 8601 timestamp of export
        - tasks: List of task dictionaries in Taskmaster format
    """
    tasks = load_tasks(spec_slug)
    return {
        "project": spec_slug,
        "exported_at": now_stamp(),
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


def export_taskmaster_cmd(args: argparse.Namespace) -> None:
    """
    Export spec tasks in Taskmaster JSON format.

    Creates a Taskmaster-compatible JSON export of all tasks in a spec.
    Can write to a file or print to stdout. Useful for migrating tasks
    to external project management tools or for backup purposes.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug to export
            - output: Optional file path to write JSON (prints to stdout if None)
    """
    payload = taskmaster_payload(args.spec)
    if args.output:
        output = Path(args.output)
        write_json(output, payload)
        print(str(output))
        return
    print_json(payload)


def normalize_imported_task(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """
    Normalize an imported task entry to Autoflow format.

    Handles multiple input formats (Taskmaster, legacy Autoflow, etc.) and
    converts them to the standard Autoflow task schema. Provides sensible
    defaults for missing fields and validates status values.

    Args:
        entry: Raw task dictionary from import source. May contain various
            field names (e.g., "dependencies" vs "depends_on",
            "acceptanceCriteria" vs "acceptance_criteria")
        index: Numeric index used for generating default task ID

    Returns:
        Normalized task dictionary with fields:
        - id: Task identifier (from entry or generated as T{index})
        - title: Task title (from "title", "name", or generated)
        - status: Validated task status (defaults to "todo")
        - depends_on: List of task dependency IDs
        - owner_role: Role responsible for the task
        - acceptance_criteria: List of acceptance criteria
        - notes: List of task notes
    """
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


def import_taskmaster_cmd(args: argparse.Namespace) -> None:
    """
    Import tasks from Taskmaster JSON format into a spec.

    Reads a JSON file containing task data in Taskmaster or compatible format,
    normalizes the entries to Autoflow schema, and updates the spec's task file.
    Accepts both a list of tasks or a dict with a "tasks" key.

    Synchronizes review state after import and records the import event for
    audit trail purposes.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug to import tasks into
            - input: Path to JSON file containing task data

    Side Effects:
        - Overwrites the spec's task file with imported data
        - Syncs review state (may clear existing review data)
        - Records "taskmaster.imported" event in spec history
    """
    payload = read_json(Path(args.input))
    tasks_input = payload if isinstance(payload, list) else payload.get("tasks", [])
    normalized = [
        normalize_imported_task(item, index)
        for index, item in enumerate(tasks_input, start=1)
    ]
    data = {
        "spec_slug": args.spec,
        "updated_at": now_stamp(),
        "tasks": normalized,
    }
    write_json(task_file(args.spec), data)
    sync_review_state(args.spec, reason="taskmaster_import")
    record_event(args.spec, "taskmaster.imported", {"task_count": len(normalized), "source": args.input})
    print_json({"spec": args.spec, "task_count": len(normalized)})


def create_worktree(args: argparse.Namespace) -> None:
    """
    Create a git worktree for isolated spec development.

    Creates a new git worktree linked to a spec-specific branch, allowing
    parallel development without affecting the main branch. The worktree
    is created at `.autoflow/worktrees/tasks/{spec_slug}`.

    If the worktree already exists, updates the spec metadata with the
    worktree information without recreating it.

    The branch name follows the pattern `codex/{slugified_spec}` and is
    created from the base branch if it doesn't already exist.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - base_branch: Base branch to create worktree from (optional,
              defaults to detected base branch)

    Side Effects:
        - Creates git worktree directory
        - Creates or checks out spec-specific branch
        - Updates spec metadata with worktree path and branch info
        - Records worktree.created event

    Example:
        >>> args = argparse.Namespace(spec="feature-auth", base_branch="main")
        >>> create_worktree(args)
        {"path": ".autoflow/worktrees/tasks/feature-auth",
         "branch": "codex/feature-auth",
         "base_branch": "main"}
    """
    ensure_state()
    path = worktree_path(args.spec)
    branch = worktree_branch(args.spec)
    base_branch = args.base_branch or detect_base_branch()
    metadata = read_json_or_default(spec_files(args.spec)["metadata"], {})

    if path.exists():
        metadata["worktree"] = {
            "path": str(path),
            "branch": branch,
            "base_branch": base_branch,
        }
        write_json(spec_files(args.spec)["metadata"], metadata)
        print_json(metadata["worktree"])
        return

    branch_exists = run_cmd(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    if branch_exists:
        run_cmd(["git", "worktree", "add", str(path), branch])
    else:
        run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch])

    metadata["worktree"] = {
        "path": str(path),
        "branch": branch,
        "base_branch": base_branch,
    }
    write_json(spec_files(args.spec)["metadata"], metadata)
    record_event(args.spec, "worktree.created", metadata["worktree"])
    print_json(metadata["worktree"])


def remove_worktree(args: argparse.Namespace) -> None:
    """
    Remove a git worktree for a spec.

    Removes the worktree directory and optionally deletes the associated branch.
    Updates the spec metadata to clear the worktree path.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - delete_branch: If True, delete the associated git branch
              (defaults to False from argparse)

    Side Effects:
        - Removes git worktree directory if it exists
        - Deletes the associated branch if delete_branch is True
        - Updates spec metadata to clear worktree path
        - Records worktree.removed event

    Example:
        >>> args = argparse.Namespace(spec="feature-auth", delete_branch=True)
        >>> remove_worktree(args)
        {"path": "", "branch": "codex/feature-auth", "base_branch": "main"}
    """
    path = worktree_path(args.spec)
    branch = worktree_branch(args.spec)
    if path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)])
    if args.delete_branch:
        run_cmd(["git", "branch", "-D", branch], check=False)
    metadata = read_json_or_default(spec_files(args.spec)["metadata"], {})
    metadata["worktree"] = {"path": "", "branch": branch, "base_branch": detect_base_branch()}
    write_json(spec_files(args.spec)["metadata"], metadata)
    record_event(args.spec, "worktree.removed", {"path": str(path), "branch_deleted": args.delete_branch})
    print_json(metadata["worktree"])


def list_specs(_: argparse.Namespace) -> None:
    items = []
    for metadata_path in SPECS_DIR.glob("*/metadata.json"):
        metadata = read_json(metadata_path)
        slug = metadata.get("slug", metadata_path.parent.name)
        review_state = load_review_state(slug)
        items.append(
            {
                "slug": slug,
                "title": metadata.get("title", ""),
                "summary": metadata.get("summary", ""),
                "status": metadata.get("status", ""),
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "worktree": metadata.get("worktree", {}),
                "review": {
                    "approved": review_state.get("approved", False),
                    "approved_by": review_state.get("approved_by", ""),
                    "review_count": review_state.get("review_count", 0),
                },
            }
        )
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    print(json.dumps(items, indent=2, ensure_ascii=True))


def list_worktrees(_: argparse.Namespace) -> None:
    """
    List all worktrees across all specs.

    Scans all spec metadata files to collect worktree information, including
    the spec slug, worktree path, associated branch, and base branch.

    Args:
        _: Unused namespace argument (required for CLI command interface)

    Output:
        Prints JSON array of worktree information, one entry per spec:
        - spec: Spec slug identifier
        - worktree: Dictionary containing:
            - path: Path to worktree directory (empty if not created)
            - branch: Branch name for the worktree
            - base_branch: Base branch the worktree was created from

    Example:
        >>> list_worktrees(None)
        [
          {
            "spec": "feature-auth",
            "worktree": {
              "path": ".autoflow/worktrees/tasks/feature-auth",
              "branch": "codex/feature-auth",
              "base_branch": "main"
            }
          },
          {
            "spec": "bugfix-login",
            "worktree": {"path": "", "branch": "codex/bugfix-login", "base_branch": "main"}
          }
        ]
    """
    items = []
    for metadata_path in sorted(SPECS_DIR.glob("*/metadata.json")):
        metadata = read_json(metadata_path)
        items.append(
            {
                "spec": metadata.get("slug", metadata_path.parent.name),
                "worktree": metadata.get("worktree", {}),
            }
        )
    print_json(items)


def workflow_state(args: argparse.Namespace) -> None:
    """
    Aggregate and display comprehensive workflow state for a spec.

    Computes the complete workflow state by analyzing task dependencies,
    review status, active runs, strategy memory, and QA fix requests.
    Identifies ready tasks (those whose dependencies are satisfied) and
    blocked tasks, then determines the recommended next action while
    respecting approval gates.

    The output payload includes:
        - spec: Spec slug identifier
        - review_status: Review approval and validity information
        - worktree: Git worktree metadata if present
        - fix_request_present: Whether a QA fix request exists
        - fix_request: Structured QA fix request data
        - strategy_summary: Strategy memory with playbook and reflections
        - active_runs: List of currently executing runs for this spec
        - ready_tasks: Tasks ready to be started (dependencies met)
        - blocked_or_active_tasks: Tasks that are blocked or in progress
        - blocking_reason: Reason if next action is blocked (e.g., "review_approval_required")
        - recommended_next_action: Next task to work on, or None if active runs exist

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier

    Returns:
        None (prints JSON payload to stdout)
    """
    data = load_tasks(args.spec)
    review_summary = review_status_summary(args.spec)
    active_runs = active_runs_for_spec(args.spec)
    ready = []
    blocked = []
    for task in data.get("tasks", []):
        deps_done = all(task_lookup(data, dep)["status"] == "done" for dep in task.get("depends_on", []))
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
    if next_entry and next_entry["owner_role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        blocking_reason = "review_approval_required"
        next_entry = None
    payload = {
        "spec": args.spec,
        "review_status": review_summary,
        "worktree": read_json_or_default(spec_files(args.spec)["metadata"], {}).get("worktree", {}),
        "fix_request_present": bool(load_fix_request(args.spec)),
        "fix_request": load_fix_request_data(args.spec),
        "strategy_summary": strategy_summary(args.spec),
        "active_runs": active_runs,
        "ready_tasks": ready,
        "blocked_or_active_tasks": blocked,
        "blocking_reason": blocking_reason,
        "recommended_next_action": None if active_runs else next_entry,
    }
    print_json(payload)


def show_status(_: argparse.Namespace) -> None:
    """
    Display overall Autoflow system status.

    Shows a high-level overview of the Autoflow system by listing all
    available specs and runs. This provides a quick way to see what
    specs exist and what runs have been executed across the entire system.

    The output payload includes:
        - specs: Alphabetically sorted list of spec slugs
        - runs: Alphabetically sorted list of run IDs

    Args:
        _: Namespace (unused, present for command interface consistency)

    Returns:
        None (prints JSON payload to stdout)
    """
    ensure_state()
    specs = sorted(p.name for p in SPECS_DIR.iterdir() if p.is_dir())
    runs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
    status = {"specs": specs, "runs": runs}
    print_json(status)


def list_runs(args: argparse.Namespace) -> None:
    ensure_state()
    runs = run_metadata_iter()

    # Apply filters if provided
    if hasattr(args, 'spec') and args.spec:
        runs = [r for r in runs if r.get("spec") == args.spec]
    if hasattr(args, 'status') and args.status:
        runs = [r for r in runs if r.get("status") == args.status]
    if hasattr(args, 'role') and args.role:
        runs = [r for r in runs if r.get("role") == args.role]
    if hasattr(args, 'agent') and args.agent:
        runs = [r for r in runs if r.get("agent") == args.agent]

    print(json.dumps(runs, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    """
    Build and configure the Autoflow CLI argument parser.

    Creates the main ArgumentParser and all subcommands for interacting with
    the Autoflow workflow system. Each subcommand is configured with its
    respective arguments and bound to a handler function.

    Returns:
        Configured ArgumentParser with all Autoflow subcommands registered.

    Subcommands:
        init: Create .autoflow state directories
        new-spec: Create a spec scaffold with slug, title, and summary
        list-tasks: Print the task graph for a spec
        next-task: Print the next ready task for a role
        set-task-status: Update a task lifecycle state
        create-handoff: Write a handoff artifact between roles
        create-fix-request: Write a structured QA fix request artifact
        show-fix-request: Show the structured QA fix request data
        review-status: Show hash-based review approval status
        approve-spec: Approve the current spec/task contract hash
        invalidate-review: Manually invalidate approval state
        create-worktree: Create or reuse an isolated git worktree for a spec
        remove-worktree: Remove a spec worktree
        list-worktrees: Show known spec worktrees
        init-system-config: Write the local system config scaffold
        show-system-config: Show system memory/model/tool config
        discover-agents: Probe local agents and merge ACP registry entries
        sync-agents: Merge discovered CLI/ACP agents into .autoflow/agents.json
        write-memory: Append to global or spec memory
        show-memory: Show stored memory context
        show-strategy: Show accumulated planner/reflection strategy memory
        add-planner-note: Append a planner strategy note to strategy memory
        export-taskmaster: Export Autoflow tasks in Taskmaster-friendly JSON
        import-taskmaster: Import task data from Taskmaster-style JSON
        new-run: Create a runnable agent job
        resume-run: Create a retry run from an earlier run record
        complete-run: Close a run and update task state
        task-history: Show run history for a task
        show-events: Show recent event records for a spec
        workflow-state: Show ready tasks and next suggested action
        status: Print current specs and runs

    Examples:
        >>> parser = build_parser()
        >>> args = parser.parse_args(["status"])
        >>> args.func(args)
    """
    parser = argparse.ArgumentParser(description="Autoflow control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="create .autoflow state directories")
    init_cmd.set_defaults(func=lambda _: ensure_state())

    spec_cmd = sub.add_parser("new-spec", help="create a spec scaffold")
    spec_cmd.add_argument("--slug", default="")
    spec_cmd.add_argument("--title", required=True)
    spec_cmd.add_argument("--summary", required=True)
    spec_cmd.set_defaults(func=create_spec)

    tasks_cmd = sub.add_parser("list-tasks", help="print the task graph for a spec")
    tasks_cmd.add_argument("--spec", required=True)
    tasks_cmd.set_defaults(func=list_tasks)

    next_cmd = sub.add_parser("next-task", help="print the next ready task")
    next_cmd.add_argument("--spec", required=True)
    next_cmd.add_argument("--role")
    next_cmd.set_defaults(func=next_task)

    set_task_cmd = sub.add_parser("set-task-status", help="update a task lifecycle state")
    set_task_cmd.add_argument("--spec", required=True)
    set_task_cmd.add_argument("--task", required=True)
    set_task_cmd.add_argument("--status", required=True)
    set_task_cmd.add_argument("--note", default="")
    set_task_cmd.set_defaults(func=set_task_status)

    handoff_cmd = sub.add_parser("create-handoff", help="write a handoff artifact")
    handoff_cmd.add_argument("--spec", required=True)
    handoff_cmd.add_argument("--task", required=True)
    handoff_cmd.add_argument("--role", required=True)
    handoff_cmd.add_argument("--summary", required=True)
    handoff_cmd.add_argument("--next-role", required=True)
    handoff_cmd.add_argument("--result", required=True)
    handoff_cmd.set_defaults(func=create_handoff)

    fix_request_cmd = sub.add_parser("create-fix-request", help="write a structured QA fix request artifact")
    fix_request_cmd.add_argument("--spec", required=True)
    fix_request_cmd.add_argument("--task", required=True)
    fix_request_cmd.add_argument("--summary", required=True)
    fix_request_cmd.add_argument("--result", required=True)
    fix_request_cmd.add_argument("--findings-json", default="")
    fix_request_cmd.add_argument("--findings-file", default="")
    fix_request_cmd.set_defaults(func=create_fix_request_cmd)

    show_fix_cmd = sub.add_parser("show-fix-request", help="show the structured QA fix request data")
    show_fix_cmd.add_argument("--spec", required=True)
    show_fix_cmd.set_defaults(func=show_fix_request)

    review_status_cmd = sub.add_parser("review-status", help="show hash-based review approval status")
    review_status_cmd.add_argument("--spec", required=True)
    review_status_cmd.set_defaults(func=show_review_status)

    approve_cmd = sub.add_parser("approve-spec", help="approve the current spec/task contract hash")
    approve_cmd.add_argument("--spec", required=True)
    approve_cmd.add_argument("--approved-by", default="user")
    approve_cmd.set_defaults(func=approve_spec)

    invalidate_cmd = sub.add_parser("invalidate-review", help="manually invalidate approval state")
    invalidate_cmd.add_argument("--spec", required=True)
    invalidate_cmd.add_argument("--reason", default="manual_invalidation")
    invalidate_cmd.set_defaults(func=invalidate_review)

    worktree_create_cmd = sub.add_parser("create-worktree", help="create or reuse an isolated git worktree for a spec")
    worktree_create_cmd.add_argument("--spec", required=True)
    worktree_create_cmd.add_argument("--base-branch", default="")
    worktree_create_cmd.set_defaults(func=create_worktree)

    worktree_remove_cmd = sub.add_parser("remove-worktree", help="remove a spec worktree")
    worktree_remove_cmd.add_argument("--spec", required=True)
    worktree_remove_cmd.add_argument("--delete-branch", action="store_true")
    worktree_remove_cmd.set_defaults(func=remove_worktree)

    list_specs_cmd = sub.add_parser("list-specs", help="list all specs with metadata including status, worktree, and review state")
    list_specs_cmd.set_defaults(func=list_specs)

    worktree_list_cmd = sub.add_parser("list-worktrees", help="show known spec worktrees")
    worktree_list_cmd.set_defaults(func=list_worktrees)

    init_system_cmd = sub.add_parser("init-system-config", help="write the local system config scaffold")
    init_system_cmd.set_defaults(func=init_system_config)

    system_cmd = sub.add_parser("show-system-config", help="show system memory/model/tool config")
    system_cmd.set_defaults(func=show_system_config)

    discover_cmd = sub.add_parser("discover-agents", help="probe local agents and merge ACP registry entries")
    discover_cmd.set_defaults(func=discover_agents_cmd)

    sync_cmd = sub.add_parser("sync-agents", help="merge discovered CLI/ACP agents into .autoflow/agents.json")
    sync_cmd.add_argument("--overwrite", action="store_true")
    sync_cmd.set_defaults(func=sync_agents_cmd)

    write_memory = sub.add_parser("write-memory", help="append to global or spec memory")
    write_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    write_memory.add_argument("--spec")
    write_memory.add_argument("--title", default="")
    write_memory.add_argument("--content", required=True)
    write_memory.set_defaults(func=write_memory_cmd)

    show_memory = sub.add_parser("show-memory", help="show stored memory context")
    show_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    show_memory.add_argument("--spec")
    show_memory.set_defaults(func=show_memory_cmd)

    strategy_cmd = sub.add_parser("show-strategy", help="show accumulated planner/reflection strategy memory")
    strategy_cmd.add_argument("--spec", required=True)
    strategy_cmd.set_defaults(func=show_strategy_cmd)

    planner_cmd = sub.add_parser("add-planner-note", help="append a planner strategy note to strategy memory")
    planner_cmd.add_argument("--spec", required=True)
    planner_cmd.add_argument("--title", required=True)
    planner_cmd.add_argument("--content", required=True)
    planner_cmd.add_argument("--category", default="strategy")
    planner_cmd.add_argument("--scope", choices=["global", "spec"], default="spec")
    planner_cmd.set_defaults(func=add_planner_note_cmd)

    export_taskmaster = sub.add_parser("export-taskmaster", help="export Autoflow tasks in a Taskmaster-friendly JSON shape")
    export_taskmaster.add_argument("--spec", required=True)
    export_taskmaster.add_argument("--output", default="")
    export_taskmaster.set_defaults(func=export_taskmaster_cmd)

    import_taskmaster = sub.add_parser("import-taskmaster", help="import task data from a Taskmaster-style JSON file")
    import_taskmaster.add_argument("--spec", required=True)
    import_taskmaster.add_argument("--input", required=True)
    import_taskmaster.set_defaults(func=import_taskmaster_cmd)

    run_cmd_parser = sub.add_parser("new-run", help="create a runnable agent job")
    run_cmd_parser.add_argument("--spec", required=True)
    run_cmd_parser.add_argument("--role", required=True)
    run_cmd_parser.add_argument("--agent", required=True)
    run_cmd_parser.add_argument("--task")
    run_cmd_parser.add_argument("--branch")
    run_cmd_parser.add_argument("--resume-from")
    run_cmd_parser.set_defaults(func=create_run)

    resume_cmd = sub.add_parser("resume-run", help="create a retry run from an earlier run record")
    resume_cmd.add_argument("--run", required=True)
    resume_cmd.set_defaults(func=resume_run)

    complete_cmd = sub.add_parser("complete-run", help="close a run and update task state")
    complete_cmd.add_argument("--run", required=True)
    complete_cmd.add_argument("--result", required=True)
    complete_cmd.add_argument("--summary", default="")
    complete_cmd.add_argument("--findings-json", default="")
    complete_cmd.add_argument("--findings-file", default="")
    complete_cmd.set_defaults(func=complete_run)

    cancel_cmd = sub.add_parser("cancel-run", help="cancel a run and revert task status")
    cancel_cmd.add_argument("--run", required=True)
    cancel_cmd.add_argument("--reason", default="")
    cancel_cmd.set_defaults(func=cancel_run)

    history_cmd = sub.add_parser("task-history", help="show run history for a task")
    history_cmd.add_argument("--spec", required=True)
    history_cmd.add_argument("--task", required=True)
    history_cmd.set_defaults(func=show_task_history)

    events_cmd = sub.add_parser("show-events", help="show recent event records for a spec")
    events_cmd.add_argument("--spec", required=True)
    events_cmd.add_argument("--limit", type=int, default=20)
    events_cmd.set_defaults(func=show_events)

    workflow_cmd = sub.add_parser("workflow-state", help="show ready tasks and the next suggested action")
    workflow_cmd.add_argument("--spec", required=True)
    workflow_cmd.set_defaults(func=workflow_state)

    status_cmd = sub.add_parser("status", help="print current specs and runs")
    status_cmd.set_defaults(func=show_status)

    list_runs_cmd = sub.add_parser("list-runs", help="list runs with optional filtering")
    list_runs_cmd.add_argument("--spec", default="", help="filter by spec slug")
    list_runs_cmd.add_argument("--status", default="", help="filter by run status")
    list_runs_cmd.add_argument("--role", default="", help="filter by role")
    list_runs_cmd.add_argument("--agent", default="", help="filter by agent name")
    list_runs_cmd.set_defaults(func=list_runs)

    return parser


def main() -> None:
    """
    Main entry point for the Autoflow CLI.

    Parses command-line arguments and dispatches to the appropriate command handler.
    Each command is implemented as a separate function that receives the parsed arguments.

    The CLI uses argparse for argument parsing, with subcommands for each major operation:
    - init: Initialize Autoflow state directories
    - new-spec: Create a new specification
    - list-tasks: Show tasks for a spec
    - create-worktree: Create a git worktree for isolated development
    - status: Show overall Autoflow status
    - And many more...

    Error Handling:
        - Argument parsing errors are handled by argparse and display usage information
        - Command-specific errors are handled by individual command functions
        - Unhandled exceptions will propagate and display a traceback

    Example:
        # Initialize Autoflow
        python scripts/autoflow.py init

        # Create a new spec
        python scripts/autoflow.py new-spec --title "Add Feature" --summary "Description"

        # Show status
        python scripts/autoflow.py status
    """
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
