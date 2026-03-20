"""
Autoflow CLI Module

Provides core CLI functionality for the Autoflow workflow system.
This module extracts business logic from scripts/autoflow.py into a
testable class using dependency injection for configuration.

Usage:
    from autoflow.autoflow_cli import AutoflowCLI
    from autoflow.core.config import load_config

    config = load_config()
    cli = AutoflowCLI(config)
    cli.ensure_state()
    tasks = cli.load_tasks("my-spec")
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from autoflow.core.config import Config, get_state_dir


class TaskStatus(StrEnum):
    """Valid task statuses in the workflow."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    NEEDS_CHANGES = "needs_changes"
    BLOCKED = "blocked"
    DONE = "done"


class RunResult(StrEnum):
    """Possible results of an agent run."""

    SUCCESS = "success"
    NEEDS_CHANGES = "needs_changes"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class AgentSpec:
    """Specification for an agent configuration."""

    name: str
    command: str
    args: list[str]
    resume: dict[str, Any] | None = None
    model: str | None = None
    model_profile: str | None = None
    tool_profile: str | None = None
    tools: list[str] | None = None
    memory_scopes: list[str] | None = None
    protocol: str | None = None
    transport: dict[str, Any] | None = None


class AutoflowCLI:
    """
    Core Autoflow CLI functionality.

    This class encapsulates the business logic from the original
    scripts/autoflow.py, making it testable through dependency
    injection of configuration.

    Attributes:
        config: Autoflow configuration object
        root: Root directory of the project
        state_dir: State directory for storing workflow data

    Example:
        >>> from autoflow.core.config import load_config
        >>> from autoflow.autoflow_cli import AutoflowCLI
        >>>
        >>> config = load_config()
        >>> cli = AutoflowCLI(config, root=Path("."))
        >>> cli.ensure_state()
        >>> cli.create_spec("my-spec", "Title", "Description")
    """

    # Subdirectories within state directory
    SPECS_DIR = "specs"
    TASKS_DIR = "tasks"
    RUNS_DIR = "runs"
    LOGS_DIR = "logs"
    WORKTREES_DIR = "worktrees/tasks"
    MEMORY_DIR = "memory"
    STRATEGY_MEMORY_DIR = "memory/strategy"

    # File names
    REVIEW_STATE_FILE = "review_state.json"
    EVENTS_FILE = "events.jsonl"
    QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
    QA_FIX_REQUEST_JSON_FILE = "QA_FIX_REQUEST.json"

    def __init__(
        self,
        config: Config,
        root: str | Path | None = None,
        state_dir: str | Path | None = None,
    ):
        """
        Initialize the AutoflowCLI.

        Args:
            config: Autoflow configuration object
            root: Project root directory (defaults to current working directory)
            state_dir: State directory (defaults to config.state_dir or .autoflow)
        """
        self.config = config

        # Resolve root directory
        if root is None:
            root = Path.cwd()
        self.root = Path(root).resolve()

        # Resolve state directory
        if state_dir is None:
            state_dir = get_state_dir(config)
        self.state_dir = Path(state_dir).resolve()

        # Make shutil available for testing
        self.shutil = shutil

    @property
    def specs_dir(self) -> Path:
        """Path to specs directory."""
        return self.state_dir / self.SPECS_DIR

    @property
    def tasks_dir(self) -> Path:
        """Path to tasks directory."""
        return self.state_dir / self.TASKS_DIR

    @property
    def runs_dir(self) -> Path:
        """Path to runs directory."""
        return self.state_dir / self.RUNS_DIR

    @property
    def logs_dir(self) -> Path:
        """Path to logs directory."""
        return self.state_dir / self.LOGS_DIR

    @property
    def worktrees_dir(self) -> Path:
        """Path to worktrees directory."""
        return self.state_dir / self.WORKTREES_DIR

    @property
    def memory_dir(self) -> Path:
        """Path to memory directory."""
        return self.state_dir / self.MEMORY_DIR

    @property
    def strategy_memory_dir(self) -> Path:
        """Path to strategy memory directory."""
        return self.state_dir / self.STRATEGY_MEMORY_DIR

    @property
    def agents_file(self) -> Path:
        """Path to agents configuration file."""
        return self.state_dir / "agents.json"

    @property
    def discovery_file(self) -> Path:
        """Path to discovered agents registry file."""
        return self.state_dir / "discovered_agents.json"

    @property
    def system_config_file(self) -> Path:
        """Path to system configuration file."""
        return self.state_dir / "system.json"

    @property
    def bmad_dir(self) -> Path:
        """Path to BMAD templates directory."""
        return self.root / "templates" / "bmad"

    @property
    def system_config_template(self) -> Path:
        """Path to system configuration template."""
        return self.root / "config" / "system.example.json"

    # === Utility Methods ===

    @staticmethod
    def now_utc() -> datetime:
        """
        Get current datetime in UTC.

        Returns:
            Current datetime in UTC
        """
        return datetime.now(UTC)

    def now_stamp(self) -> str:
        """
        Get current UTC timestamp as a string.

        Returns:
            Timestamp in format YYYYMMDDTHHMMSSZ
        """
        return self.now_utc().strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def slugify(value: str) -> str:
        """
        Convert a string to a URL-friendly slug.

        Args:
            value: String to slugify

        Returns:
            Slugified string
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

    @staticmethod
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

    def write_json(self, path: Path, data: Any, indent: int = 2) -> None:
        """
        Write JSON data to a file.

        Args:
            path: Destination file path
            data: JSON-serializable data
            indent: Indentation level (default: 2)
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=indent, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def read_json(self, path: Path) -> Any:
        """
        Read JSON data from a file.

        Args:
            path: Source file path

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON
        """
        return json.loads(path.read_text(encoding="utf-8"))

    def read_json_or_default(self, path: Path, default: Any) -> Any:
        """
        Read JSON data from a file, returning default if not found.

        Args:
            path: Source file path
            default: Default value if file doesn't exist

        Returns:
            Parsed JSON data or default value
        """
        if not path.exists():
            return default
        try:
            return self.read_json(path)
        except (json.JSONDecodeError, OSError):
            return default

    def ensure_state(self) -> None:
        """
        Ensure all state directories exist.

        Creates the state directory structure if it doesn't exist.
        """
        for path in [
            self.state_dir,
            self.specs_dir,
            self.tasks_dir,
            self.runs_dir,
            self.logs_dir,
            self.worktrees_dir,
            self.memory_dir,
            self.strategy_memory_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def run_cmd(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a command as a subprocess.

        Args:
            args: Command arguments
            cwd: Working directory (defaults to root)
            check: Whether to raise exception on non-zero exit

        Returns:
            Completed process result
        """
        return subprocess.run(
            args,
            cwd=cwd or self.root,
            check=check,
            capture_output=True,
            text=True,
        )

    # === Path Resolution Methods ===

    def spec_dir(self, slug: str) -> Path:
        """
        Get the directory path for a spec.

        Args:
            slug: Spec slug identifier

        Returns:
            Path to spec directory

        Raises:
            SystemExit: If slug contains path traversal patterns
        """
        if not self.validate_slug_safe(slug):
            raise SystemExit(f"invalid spec slug: {slug}")
        return self.specs_dir / slug

    def task_file(self, spec_slug: str) -> Path:
        """
        Get the task file path for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Path to tasks file

        Raises:
            SystemExit: If spec_slug contains path traversal patterns
        """
        if not self.validate_slug_safe(spec_slug):
            raise SystemExit(f"invalid spec slug: {spec_slug}")
        return self.spec_dir(spec_slug) / "tasks.json"

    def worktree_path(self, spec_slug: str) -> Path:
        """
        Get the worktree path for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Path to worktree
        """
        if not self.validate_slug_safe(spec_slug):
            raise SystemExit(f"invalid spec slug: {spec_slug}")
        return self.worktrees_dir / spec_slug

    def worktree_branch(self, spec_slug: str) -> str:
        """
        Get the git branch name for a spec worktree.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Branch name
        """
        return f"spec/{spec_slug}"

    def spec_files(self, slug: str) -> dict[str, Path]:
        """
        Get all file paths for a spec.

        Args:
            slug: Spec slug identifier

        Returns:
            Dictionary mapping file types to their paths
        """
        base = self.spec_dir(slug)
        worktree = self.worktree_path(slug)
        runs_dir = base / "runs"
        return {
            "base": base,
            "spec_md": base / "spec.md",
            "plan_md": base / "plan.md",
            "tasks_json": base / "tasks.json",
            "review_state": base / self.REVIEW_STATE_FILE,
            "events": base / self.EVENTS_FILE,
            "qa_fix_request": base / self.QA_FIX_REQUEST_FILE,
            "qa_fix_request_json": base / self.QA_FIX_REQUEST_JSON_FILE,
            "handoffs_dir": base / "handoffs",
            "runs": runs_dir,
            "memory_dir": self.memory_dir / "specs" / slug,
            "worktree": worktree,
        }

    def memory_file(self, scope: str, spec_slug: str | None = None) -> Path:
        """
        Get the path to a memory file.

        Args:
            scope: Memory scope (e.g., "spec", "global")
            spec_slug: Optional spec slug for spec-scoped memory

        Returns:
            Path to memory file
        """
        if spec_slug:
            return self.memory_dir / "specs" / spec_slug / f"{scope}.md"
        return self.memory_dir / f"{scope}.md"

    def strategy_memory_file(self, scope: str, spec_slug: str | None = None) -> Path:
        """
        Get the path to a strategy memory file.

        Args:
            scope: Memory scope
            spec_slug: Optional spec slug

        Returns:
            Path to strategy memory file
        """
        if spec_slug:
            return self.strategy_memory_dir / "specs" / spec_slug / f"{scope}.json"
        return self.strategy_memory_dir / f"{scope}.json"

    # === Spec Operations ===

    def create_spec(
        self,
        slug: str,
        title: str,
        summary: str,
        content: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new spec.

        Args:
            slug: Spec slug identifier
            title: Spec title
            summary: Spec summary
            content: Optional full spec content

        Returns:
            Created spec data
        """
        files = self.spec_files(slug)
        files["base"].mkdir(parents=True, exist_ok=True)

        spec_content = content or f"# {title}\n\n{summary}"
        files["spec_md"].write_text(spec_content, encoding="utf-8")

        spec_data = {
            "id": slug,
            "slug": slug,
            "title": title,
            "summary": summary,
            "created_at": self.now_stamp(),
            "updated_at": self.now_stamp(),
        }

        self.write_json(files["base"] / "spec.json", spec_data)

        # Create initial tasks if not exists
        if not files["tasks_json"].exists():
            tasks_data = {
                "spec_slug": slug,
                "updated_at": self.now_stamp(),
                "tasks": [
                    {
                        "id": "T1",
                        "title": f"Define workflow for {title}",
                        "status": "todo",
                        "depends_on": [],
                        "owner_role": "spec-writer",
                        "acceptance_criteria": ["Initial task created"],
                        "notes": [],
                    }
                ],
            }
            self.write_json(files["tasks_json"], tasks_data)

        return spec_data

    # === Task Operations ===

    def load_tasks(self, spec_slug: str) -> dict[str, Any]:
        """
        Load tasks for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Tasks data dictionary
        """
        path = self.task_file(spec_slug)
        return self.read_json_or_default(
            path, {"tasks": [], "updated_at": self.now_stamp()}
        )

    def save_tasks(
        self,
        spec_slug: str,
        data: dict[str, Any],
        *,
        reason: str = "task_state_updated",
    ) -> None:
        """
        Save tasks for a spec.

        Args:
            spec_slug: Spec slug identifier
            data: Tasks data
            reason: Reason for the update (for review state sync)
        """
        data["updated_at"] = self.now_stamp()
        self.write_json(self.task_file(spec_slug), data)
        self.sync_review_state(spec_slug, reason=reason)

    def task_lookup(self, data: dict[str, Any], task_id: str) -> dict[str, Any]:
        """
        Look up a task by ID in task data.

        Args:
            data: Task data dictionary
            task_id: Task ID to look up

        Returns:
            Task dictionary or empty dict if not found
        """
        for task in data.get("tasks", []):
            if task.get("id") == task_id:
                return task
        return {}

    # === Review State Operations ===

    def load_review_state(self, spec_slug: str) -> dict[str, Any]:
        """
        Load review state for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Review state dictionary
        """
        files = self.spec_files(spec_slug)
        return self.read_json_or_default(
            files["review_state"], self.review_state_default()
        )

    def save_review_state(self, spec_slug: str, state: dict[str, Any]) -> None:
        """
        Save review state for a spec.

        Args:
            spec_slug: Spec slug identifier
            state: Review state dictionary
        """
        files = self.spec_files(spec_slug)
        self.write_json(files["review_state"], state)

    def review_state_default(self) -> dict[str, Any]:
        """
        Get default review state structure.

        Returns:
            Default review state dictionary
        """
        return {
            "valid": True,
            "invalidated_at": "",
            "invalidated_reason": "",
            "spec_hash": "",
            "feedback": [],
            "feedback_count": 0,
        }

    def sync_review_state(
        self, spec_slug: str, reason: str = "planning_artifacts_changed"
    ) -> dict[str, Any]:
        """
        Sync review state, marking as invalidated if spec changed.

        Args:
            spec_slug: Spec slug identifier
            reason: Reason for sync

        Returns:
            Updated review state
        """
        state = self.load_review_state(spec_slug)
        current_hash = self.compute_spec_hash(spec_slug)

        is_valid = state.get("valid", True)
        spec_changed = (
            bool(state.get("spec_hash")) and state.get("spec_hash") != current_hash
        )

        if spec_changed and is_valid:
            state["valid"] = False
            state["invalidated_at"] = self.now_stamp()
            state["invalidated_reason"] = reason

        state["spec_hash"] = current_hash
        state["feedback_count"] = len(state.get("feedback", []))
        state["spec_changed"] = spec_changed

        self.save_review_state(spec_slug, state)
        return state

    # === System Configuration ===

    def system_config_default(self) -> dict[str, Any]:
        """
        Get default system configuration.

        Returns:
            Default system configuration dictionary
        """
        return {
            "memory": {
                "enabled": True,
                "auto_capture_run_results": True,
                "default_scopes": ["spec"],
                "global_file": str(self.memory_dir / "global.md"),
                "spec_dir": str(self.memory_dir / "specs"),
            },
            "models": {
                "profiles": {
                    "implementation": "gpt-5-codex",
                    "review": "claude-sonnet-4-6",
                }
            },
            "tools": {
                "profiles": {
                    "claude-review": ["Read", "Bash(git:*)"],
                }
            },
            "registry": {"acp_agents": []},
        }

    def load_system_config(self) -> dict[str, Any]:
        """
        Load system configuration from file.

        Returns:
            System configuration dictionary
        """
        if self.system_config_file.exists():
            return self.read_json(self.system_config_file)

        # Load from template and save
        default = self.system_config_default()
        if self.system_config_template.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                default = self.read_json(self.system_config_template)

        self.write_json(self.system_config_file, default)
        return default

    # === Agent Operations ===

    def load_agents(self) -> dict[str, AgentSpec]:
        """
        Load agent configurations.

        Returns:
            Dictionary mapping agent names to AgentSpec objects
        """
        if not self.agents_file.exists():
            return {}

        data = self.read_json(self.agents_file)
        system_config = self.load_system_config()
        model_profiles = system_config.get("models", {}).get("profiles", {})
        tool_profiles = system_config.get("tools", {}).get("profiles", {})
        memory_config = system_config.get("memory", {})

        agents = {}

        for name, config in data.get("agents", {}).items():
            # Apply model profile if specified
            model = None
            model_profile = config.get("model_profile")
            if model_profile and model_profile in model_profiles:
                model = model_profiles[model_profile]

            # Apply tool profile if specified
            tools = None
            tool_profile = config.get("tool_profile")
            if tool_profile and tool_profile in tool_profiles:
                tools = tool_profiles[tool_profile]

            # Use default memory scopes if not specified
            memory_scopes = config.get("memory_scopes")
            if memory_scopes is None:
                memory_scopes = memory_config.get("default_scopes", ["spec"])

            agents[name] = AgentSpec(
                name=name,
                command=config.get("command", name),
                args=config.get("args", []),
                resume=config.get("resume"),
                model=model,
                model_profile=model_profile,
                tool_profile=tool_profile,
                tools=tools,
                memory_scopes=memory_scopes,
            )

        return agents

    # === Memory Operations ===

    def append_memory(
        self,
        scope: str,
        content: str,
        spec_slug: str | None = None,
        title: str = "",
    ) -> Path:
        """
        Append content to a memory file.

        Args:
            scope: Memory scope
            content: Content to append
            spec_slug: Optional spec slug for spec-scoped memory
            title: Optional title for the memory entry

        Returns:
            Path to memory file
        """
        path = self.memory_file(scope, spec_slug)
        path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = self.now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")
        separator = "\n\n---\n\n"
        header = f"## {title}\n\n" if title else ""

        entry = f"{header}{timestamp}\n\n{content}{separator}"

        if path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing + entry, encoding="utf-8")
        else:
            path.write_text(entry, encoding="utf-8")

        return path

    def load_memory_context(
        self, spec_slug: str, scopes: list[str] | None = None
    ) -> str:
        """
        Load memory context for a spec.

        Args:
            spec_slug: Spec slug identifier
            scopes: Optional list of scopes to load

        Returns:
            Memory context string
        """
        if scopes is None:
            scopes = ["spec"]

        parts = []
        for scope in scopes:
            path = self.memory_file(scope, spec_slug)
            if path.exists():
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)

        return "\n\n".join(parts)

    # === Strategy Memory Operations ===

    def load_strategy_memory(
        self, scope: str, spec_slug: str | None = None
    ) -> dict[str, Any]:
        """
        Load strategy memory.

        Args:
            scope: Memory scope
            spec_slug: Optional spec slug

        Returns:
            Strategy memory dictionary
        """
        path = self.strategy_memory_file(scope, spec_slug)
        return self.read_json_or_default(path, self.strategy_memory_default())

    def save_strategy_memory(
        self, scope: str, payload: dict[str, Any], spec_slug: str | None = None
    ) -> Path:
        """
        Save strategy memory.

        Args:
            scope: Memory scope
            payload: Memory data to save
            spec_slug: Optional spec slug

        Returns:
            Path to saved memory file
        """
        path = self.strategy_memory_file(scope, spec_slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.write_json(path, payload)
        return path

    def strategy_memory_default(self) -> dict[str, Any]:
        """
        Get default strategy memory structure.

        Returns:
            Default strategy memory dictionary
        """
        return {
            "reflections": [],
            "playbook": [],
            "counters": {
                "needs_changes": 0,
                "blocked": 0,
                "failed": 0,
            },
            "updated_at": "",
        }

    # === Fix Request Operations ===

    def load_fix_request(self, spec_slug: str) -> str:
        """
        Load fix request markdown content.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Fix request markdown content
        """
        files = self.spec_files(spec_slug)
        if files["qa_fix_request"].exists():
            return files["qa_fix_request"].read_text(encoding="utf-8")
        return ""

    def load_fix_request_data(self, spec_slug: str) -> dict[str, Any]:
        """
        Load fix request JSON data.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Fix request data dictionary
        """
        files = self.spec_files(spec_slug)
        return self.read_json_or_default(files["qa_fix_request_json"], {})

    # === Event Operations ===

    def record_event(
        self, spec_slug: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        """
        Record an event for a spec.

        Args:
            spec_slug: Spec slug identifier
            event_type: Type of event
            payload: Event payload data
        """
        files = self.spec_files(spec_slug)
        event = {
            "timestamp": self.now_stamp(),
            "type": event_type,
            **payload,
        }

        files["events"].parent.mkdir(parents=True, exist_ok=True)
        with open(files["events"], "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def load_events(self, spec_slug: str, limit: int = 20) -> list[dict[str, Any]]:
        """
        Load recent events for a spec.

        Args:
            spec_slug: Spec slug identifier
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        files = self.spec_files(spec_slug)
        if not files["events"].exists():
            return []

        events = []
        with open(files["events"], encoding="utf-8") as f:
            for line in f:
                try:
                    events.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue

        return events[-limit:]

    # === Hash Computation ===

    def compute_file_hash(self, path: Path) -> str:
        """
        Compute SHA256 hash of a file.

        Args:
            path: File path

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def compute_spec_hash(self, spec_slug: str) -> str:
        """
        Compute hash of spec artifacts for change detection.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Combined hash string
        """
        files = self.spec_files(spec_slug)

        hashes = []
        for path in [files["spec_md"], files["plan_md"], files["tasks_json"]]:
            if path.exists():
                hashes.append(self.compute_file_hash(path))

        if not hashes:
            return ""

        combined = "".join(hashes)
        return hashlib.sha256(combined.encode()).hexdigest()

    # === Strategy Summary ===

    def strategy_summary(self, spec_slug: str) -> dict[str, Any]:
        """
        Generate strategy summary for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Strategy summary dictionary
        """
        memory = self.load_strategy_memory("spec", spec_slug)
        return {
            "reflections_count": len(memory.get("reflections", [])),
            "playbook_count": len(memory.get("playbook", [])),
            "counters": memory.get("counters", {}),
            "updated_at": memory.get("updated_at", ""),
            "recent_reflections": memory.get("reflections", []),
            "playbook": memory.get("playbook", []),
        }

    # === Template Operations ===

    def load_bmad_template(self, role: str) -> str:
        """
        Load a BMAD template by role.

        Args:
            role: Role name (e.g., "spec-writer", "reviewer")

        Returns:
            Template content
        """
        path = self.bmad_dir / f"{role}.md"
        if not path.exists():
            return f"No BMAD template configured for role: {role}"
        return path.read_text(encoding="utf-8")

    # === Fix Request Operations ===

    def normalize_findings(
        self, summary: str, findings: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """
        Normalize findings data.

        Args:
            summary: Summary text
            findings: Optional list of finding dicts

        Returns:
            Normalized list of findings
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
                        "line": (
                            int(start_line) if start_line not in (None, "") else None
                        ),
                        "end_line": (
                            int(end_line) if end_line not in (None, "") else None
                        ),
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

    def format_fix_request_markdown(
        self, task_id: str, summary: str, result: str, findings: list[dict[str, Any]]
    ) -> str:
        """
        Format fix request as markdown.

        Args:
            task_id: Task identifier
            summary: Summary text
            result: Result string
            findings: List of finding dicts

        Returns:
            Formatted markdown string
        """
        lines = [
            f"# QA Fix Request: {task_id}",
            "",
            f"- created_at: {self.now_stamp()}",
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
                if (
                    finding.get("end_line") is not None
                    and finding["end_line"] != finding["line"]
                ):
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
        self,
        spec_slug: str,
        task_id: str,
        reviewer_summary: str,
        result: str,
        findings: list[dict[str, Any]] | None = None,
    ) -> Path:
        """
        Write a QA fix request.

        Args:
            spec_slug: Spec slug identifier
            task_id: Task identifier
            reviewer_summary: Summary from reviewer
            result: Result string
            findings: Optional list of findings

        Returns:
            Path to fix request file
        """
        path = self.spec_files(spec_slug)["qa_fix_request"]
        json_path = self.spec_files(spec_slug)["qa_fix_request_json"]
        normalized = self.normalize_findings(reviewer_summary, findings)
        payload = {
            "task": task_id,
            "result": result,
            "summary": reviewer_summary,
            "created_at": self.now_stamp(),
            "finding_count": len(normalized),
            "findings": normalized,
        }
        content = self.format_fix_request_markdown(
            task_id, reviewer_summary, result, normalized
        )
        content = "\n".join([content])
        path.write_text(content, encoding="utf-8")
        self.write_json(json_path, payload)
        self.record_event(
            spec_slug,
            "qa.fix_request_created",
            {"task": task_id, "result": result, "finding_count": len(normalized)},
        )
        return path

    # === Run Operations ===

    def create_run(
        self,
        args: Any,  # argparse.Namespace
    ) -> None:
        """
        Create a new run.

        Args:
            args: Arguments with spec, role, agent, task, branch, resume_from
        """
        files = self.spec_files(args.spec)
        tasks = self.load_tasks(args.spec)
        task = self.task_lookup(tasks, args.task)

        run_id = self.now_stamp()
        run_path = self.runs_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)

        metadata = {
            "id": run_id,
            "spec": args.spec,
            "role": args.role,
            "agent": args.agent,
            "task": args.task,
            "task_title": task["title"] if task else None,
            "branch": args.branch or "",
            "resume_from": args.resume_from or "",
            "attempt_count": 1,
            "status": "started",
            "created_at": self.now_stamp(),
        }

        self.write_json(run_path / "run.json", metadata)

        # Create output symlink
        link_path = files["runs"] / f"{args.role}_{args.task}"
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.unlink(missing_ok=True)
        link_path.symlink_to(run_path)

        print(run_path)

    def complete_run(self, args: Any) -> dict[str, Any]:
        """
        Complete a run.

        Args:
            args: Arguments with run, result, summary, findings_json, findings_file

        Returns:
            Result dictionary
        """
        run_path = self.runs_dir / args.run
        metadata = self.read_json(run_path / "run.json")

        # Load findings
        findings = None
        findings_json = getattr(args, "findings_json", None)
        findings_file = getattr(args, "findings_file", None)

        if findings_json:
            findings = json.loads(findings_json)
        elif findings_file:
            findings = self.read_json_or_default(Path(findings_file), [])

        # Update metadata
        metadata["status"] = "completed"
        metadata["result"] = args.result
        metadata["summary"] = args.summary
        metadata["completed_at"] = self.now_stamp()

        # Calculate duration
        created = datetime.fromisoformat(metadata["created_at"])
        completed = datetime.fromisoformat(metadata["completed_at"])
        metadata["duration_seconds"] = int((completed - created).total_seconds())

        self.write_json(run_path / "run.json", metadata)

        # Update review state
        spec_slug = metadata["spec"]
        task_id = metadata["task"]

        if metadata["role"] == "reviewer" and args.result in (
            "needs_changes",
            "blocked",
        ):
            self.write_fix_request(
                spec_slug,
                task_id,
                args.summary,
                args.result,
                findings=findings,
            )

        # Update task status
        tasks = self.load_tasks(spec_slug)
        task = self.task_lookup(tasks, task_id)
        if task:
            if args.result == "success":
                task["status"] = "done"
            elif args.result == "needs_changes":
                task["status"] = "needs_changes"
            elif args.result == "blocked":
                task["status"] = "blocked"
            self.save_tasks(spec_slug, tasks, reason="run_completed")

        # Record strategy memory
        strategy_memory_paths: list[Path] = []
        if findings:
            strategy_memory_paths = self.record_reflection(
                spec_slug,
                metadata["role"],
                args.result,
                args.summary,
                findings=findings,
            )

        result = {
            "run": args.run,
            "result": args.result,
            "fix_request": (
                str(self.spec_files(spec_slug)["qa_fix_request"])
                if metadata["role"] == "reviewer"
                and args.result in ("needs_changes", "blocked")
                else None
            ),
            "strategy_memory": [str(p) for p in strategy_memory_paths],
        }

        print(json.dumps(result, indent=2))
        return result

    def resume_run(self, args: Any) -> None:
        """
        Resume a run.

        Args:
            args: Arguments with run
        """
        original_path = self.runs_dir / args.run
        original_metadata = self.read_json(original_path / "run.json")

        # Create new run
        new_run_id = self.now_stamp()
        new_path = self.runs_dir / new_run_id
        new_path.mkdir(parents=True, exist_ok=True)

        metadata = {
            "id": new_run_id,
            "spec": original_metadata["spec"],
            "role": original_metadata["role"],
            "agent": original_metadata["agent"],
            "task": original_metadata["task"],
            "task_title": original_metadata.get("task_title"),
            "branch": original_metadata.get("branch", ""),
            "resume_from": args.run,
            "attempt_count": original_metadata.get("attempt_count", 1) + 1,
            "status": "started",
            "created_at": self.now_stamp(),
        }

        self.write_json(new_path / "run.json", metadata)

        # Update symlink
        files = self.spec_files(metadata["spec"])
        link_path = files["runs"] / f"{metadata['role']}_{metadata['task']}"
        link_path.unlink(missing_ok=True)
        link_path.symlink_to(new_path)

        print(new_path)

    # === Agent Discovery ===

    def discover_cli_agent(self, name: str, command: str) -> dict[str, Any] | None:
        """
        Discover a CLI agent.

        Args:
            name: Agent name
            command: Command path

        Returns:
            Agent config or None
        """
        if not self.shutil.which(command):
            return None

        result = self.run_cmd([command, "--help"], check=False)
        if result.returncode != 0:
            return None

        resume = None
        if "resume" in result.stdout.lower():
            resume = {"subcommand": "resume"}
        elif "continue" in result.stdout.lower():
            resume = {"subcommand": "continue"}

        return {
            "name": name,
            "command": command,
            "args": [],
            "resume": resume,
        }

    def discover_agents_registry(self) -> dict[str, Any]:
        """
        Discover agents from registry and PATH.

        Returns:
            Discovery payload
        """
        system_config = self.load_system_config()
        agents = []

        # Discover from PATH
        for name, command in [("codex", "codex"), ("claude", "claude")]:
            agent = self.discover_cli_agent(name, command)
            if agent:
                agents.append(agent)

        # Load ACP agents from config
        for acp_agent in system_config.get("registry", {}).get("acp_agents", []):
            agents.append(acp_agent)

        return {
            "agents": agents,
            "total_agents": len(agents),
            "discovered_at": self.now_stamp(),
        }

    def sync_discovered_agents(self, overwrite: bool = False) -> dict[str, Any]:
        """
        Sync discovered agents to agents file.

        Args:
            overwrite: Whether to overwrite existing agents

        Returns:
            Sync result
        """
        discovery = self.discover_agents_registry()
        existing = self.read_json_or_default(self.agents_file, {"agents": {}})

        for agent in discovery["agents"]:
            name = agent["name"]
            if overwrite or name not in existing["agents"]:
                config = self.discovered_agent_to_config(agent)
                existing["agents"][name] = config

        self.write_json(self.agents_file, existing)

        # Return result with total agent count including existing ones
        return {
            "agents": discovery["agents"],
            "total_agents": len(existing["agents"]),
            "discovered_at": self.now_stamp(),
        }

    def discovered_agent_to_config(self, agent: dict[str, Any]) -> dict[str, Any]:
        """
        Convert discovered agent to config format.

        Args:
            agent: Discovered agent dict

        Returns:
            Agent config
        """
        # Handle ACP agents that might not have "command" field
        if "command" not in agent:
            return {
                "command": agent.get("name", ""),
                "args": [],
                "resume": None,
            }

        return {
            "command": agent["command"],
            "args": agent.get("args", []),
            "resume": agent.get("resume"),
        }

    # === Strategy Memory Helpers ===

    def increment_counter(self, counters: dict[str, int], key: str) -> None:
        """
        Increment a counter in a dictionary.

        Args:
            counters: Dictionary of counters
            key: Key to increment
        """
        counters[key] = counters.get(key, 0) + 1

    def derive_strategy_actions(
        self,
        role: str,  # noqa: ARG002
        result: str,
        findings: list[dict[str, Any]],
        stats: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Derive strategy actions from run result.

        Args:
            role: Agent role
            result: Run result
            findings: List of findings
            stats: Statistics dictionary

        Returns:
            List of recommended actions
        """
        actions = []

        if result == "needs_changes" and findings:
            top_category = max(
                stats.get("finding_categories", {}).items(),
                key=lambda x: x[1],
                default=("general", 0),
            )[0]
            actions.append(
                {
                    "type": "focus_area",
                    "category": top_category,
                    "reason": f"Most findings in {top_category}",
                }
            )

        if result == "blocked":
            actions.append(
                {
                    "type": "require_planner",
                    "reason": "Task blocked, needs clarification",
                }
            )

        return actions

    def rebuild_playbook(self, memory: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Rebuild playbook from reflections.

        Args:
            memory: Strategy memory dictionary

        Returns:
            Playbook list
        """
        playbook = []
        stats = memory.get("stats", {})

        for category, count in stats.get("finding_categories", {}).items():
            if count >= 1:
                playbook.append(
                    {
                        "type": "pattern",
                        "category": category,
                        "count": count,
                        "action": f"Pay extra attention to {category} aspects",
                    }
                )

        return playbook

    def record_reflection(
        self,
        spec_slug: str,
        role: str,
        result: str,
        summary: str,
        findings: list[dict[str, Any]] | None = None,
    ) -> list[Path]:
        """
        Record a strategy reflection.

        Args:
            spec_slug: Spec slug
            role: Agent role
            result: Run result
            summary: Summary text
            findings: Optional list of findings

        Returns:
            List of updated paths
        """
        normalized = (
            self.normalize_findings(summary, findings)
            if findings or result in {"needs_changes", "blocked", "failed"}
            else []
        )
        updated_paths: list[Path] = []

        for scope in ["global", "spec"]:
            memory = self.load_strategy_memory(
                scope, spec_slug if scope == "spec" else None
            )
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
            self.increment_counter(stats.setdefault("by_role", {}), role)
            self.increment_counter(stats.setdefault("by_result", {}), result)

            for finding in normalized:
                self.increment_counter(
                    stats.setdefault("finding_categories", {}),
                    finding.get("category", "general"),
                )
                self.increment_counter(
                    stats.setdefault("severity", {}), finding.get("severity", "medium")
                )
                self.increment_counter(
                    stats.setdefault("files", {}), finding.get("file", "")
                )

            reflection = {
                "at": self.now_stamp(),
                "role": role,
                "result": result,
                "summary": summary,
                "findings": normalized,
                "recommended_actions": self.derive_strategy_actions(
                    role, result, normalized, stats
                ),
            }

            reflections = memory.setdefault("reflections", [])
            reflections.append(reflection)
            memory["reflections"] = reflections[-25:]
            memory["playbook"] = self.rebuild_playbook(memory)
            memory["updated_at"] = self.now_stamp()

            updated_paths.append(
                self.save_strategy_memory(
                    scope, memory, spec_slug if scope == "spec" else None
                )
            )

        return updated_paths

    # === Prompt Building ===

    def build_prompt(
        self,
        spec_slug: str,
        role: str,
        task_id: str | None,
        agent: AgentSpec,
        resume_from: str | None = None,
    ) -> str:
        """
        Build prompt for an agent.

        Args:
            spec_slug: Spec slug
            role: Agent role
            task_id: Task ID
            agent: Agent specification
            resume_from: Optional run ID to resume from

        Returns:
            Prompt string
        """
        files = self.spec_files(spec_slug)
        if not files["spec_md"].exists():
            raise SystemExit(f"unknown spec: {spec_slug}")

        tasks = self.load_tasks(spec_slug)
        selected_task = self.task_lookup(tasks, task_id) if task_id else None

        review_summary = (
            self.review_status_summary(spec_slug)
            if hasattr(self, "review_status_summary")
            else {}
        )
        fix_request = self.load_fix_request(spec_slug)
        fix_request_data = self.load_fix_request_data(spec_slug)
        memory_context = (
            self.load_memory_context(spec_slug, agent.memory_scopes)
            if agent.memory_scopes
            else ""
        )
        strategy_context = ""  # Simplified
        worktree_context_val = (
            f"Worktree: {files['worktree']}"
            if files["worktree"].exists()
            else "No worktree"
        )
        recovery_context_val = (
            f"Task: {selected_task['id']}" if selected_task else "No task selected"
        )
        resume_context_val = (
            f"Resuming from: {resume_from}" if resume_from else "No resume context"
        )

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
                    {
                        "agent": agent.name,
                        "command": agent.command,
                        "model": agent.model,
                        "model_profile": agent.model_profile,
                        "tools": agent.tools or [],
                        "tool_profile": agent.tool_profile,
                        "memory_scopes": agent.memory_scopes or [],
                        "native_resume_supported": bool(agent.resume),
                        "transport": agent.transport or {},
                    },
                    indent=2,
                    ensure_ascii=True,
                ),
                "",
                "## BMAD operating frame",
                self.load_bmad_template(role),
                "",
                worktree_context_val,
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
                recovery_context_val,
                "",
                "## Resume context",
                resume_context_val,
                "",
                "## QA fix request (structured)",
                json.dumps(fix_request_data, indent=2, ensure_ascii=True),
                "",
                "## QA fix request (markdown)",
                fix_request or "No QA fix request present.",
                "",
                "## Spec",
                files["spec_md"].read_text(encoding="utf-8"),
                "",
                "## Selected task",
                (
                    json.dumps(selected_task, indent=2, ensure_ascii=True)
                    if selected_task
                    else "{}"
                ),
                "",
                "## Full task graph",
                json.dumps(tasks, indent=2, ensure_ascii=True),
                "",
                "## Recent handoffs",
                "No handoffs yet.",
            ]
        )

    # === Taskmaster Operations ===

    def export_taskmaster_cmd(self, args: Any) -> None:
        """
        Export tasks to taskmaster format.

        Args:
            args: Arguments with spec and output
        """
        tasks = self.load_tasks(args.spec)
        payload = {
            "project": args.spec,
            "exported_at": self.now_stamp(),
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

        if args.output:
            output = Path(args.output)
            self.write_json(output, payload)
            print(str(output))
            return

        print(json.dumps(payload, indent=2, ensure_ascii=True))

    def import_taskmaster_cmd(self, args: Any) -> None:
        """
        Import tasks from taskmaster format.

        Args:
            args: Arguments with spec and input
        """
        payload = self.read_json(Path(args.input))
        tasks_input = payload if isinstance(payload, list) else payload.get("tasks", [])

        normalized = []
        for index, item in enumerate(tasks_input, start=1):
            depends = item.get("depends_on", item.get("dependencies", [])) or []
            criteria = (
                item.get("acceptance_criteria", item.get("acceptanceCriteria", []))
                or []
            )
            status = item.get("status", "todo")
            if status not in {
                "todo",
                "in_progress",
                "in_review",
                "needs_changes",
                "blocked",
                "done",
            }:
                status = "todo"

            normalized.append(
                {
                    "id": item.get("id") or f"T{index}",
                    "title": item.get("title", item.get("name", f"Task {index}")),
                    "status": status,
                    "depends_on": depends,
                    "owner_role": item.get(
                        "owner_role", item.get("role", "implementation-runner")
                    ),
                    "acceptance_criteria": criteria,
                    "notes": item.get("notes", []),
                }
            )

        data = {
            "spec_slug": args.spec,
            "updated_at": self.now_stamp(),
            "tasks": normalized,
        }

        self.write_json(self.task_file(args.spec), data)
        self.sync_review_state(args.spec, reason="taskmaster_import")
        self.record_event(
            args.spec,
            "taskmaster.imported",
            {"task_count": len(normalized), "source": args.input},
        )

        print(
            json.dumps(
                {"spec": args.spec, "task_count": len(normalized)},
                indent=2,
                ensure_ascii=True,
            )
        )

    # === Review State ===

    def review_status_summary(self, spec_slug: str) -> dict[str, Any]:
        """
        Get review status summary for a spec.

        Args:
            spec_slug: Spec slug

        Returns:
            Review status summary
        """
        review_state = self.load_review_state(spec_slug)
        tasks = self.load_tasks(spec_slug)

        # Count review statuses
        approved_count = 0
        total_reviewable = 0
        pending_review = False

        for task in tasks.get("tasks", []):
            if task["status"] == "done":
                # Check if this task has been approved
                task_reviews = review_state.get("task_approvals", {})
                if task_reviews.get(task["id"]) == "approved":
                    approved_count += 1
                total_reviewable += 1
            elif task["status"] == "in_review":
                pending_review = True

        # Review is valid if all done tasks are approved
        is_valid = total_reviewable == 0 or approved_count == total_reviewable

        return {
            "valid": is_valid,
            "approved_count": approved_count,
            "total_reviewable": total_reviewable,
            "pending_review": pending_review,
        }

    # === Workflow State ===

    def workflow_state(self, args: Any) -> None:
        """
        Get workflow state for a spec.

        Args:
            args: Arguments with spec
        """
        data = self.load_tasks(args.spec)
        review_summary = self.review_status_summary(args.spec)
        active_runs = []  # Simplified

        ready = []
        blocked = []

        for task in data.get("tasks", []):
            deps_done = all(
                self.task_lookup(data, dep)["status"] == "done"
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

        # Check if implementation is blocked due to missing review approval
        has_done_tasks = any(task["status"] == "done" for task in data.get("tasks", []))
        if has_done_tasks and not review_summary["valid"]:
            blocking_reason = "review_approval_required"
            next_entry = None

        payload = {
            "spec": args.spec,
            "review_status": review_summary,
            "worktree": {},
            "fix_request_present": bool(self.load_fix_request(args.spec)),
            "fix_request": self.load_fix_request_data(args.spec),
            "strategy_summary": self.strategy_summary(args.spec),
            "active_runs": active_runs,
            "ready_tasks": ready,
            "blocked_or_active_tasks": blocked,
            "blocking_reason": blocking_reason,
            "recommended_next_action": None if active_runs else next_entry,
        }

        print(json.dumps(payload, indent=2, ensure_ascii=True))
