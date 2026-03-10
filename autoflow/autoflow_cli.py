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

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel

from autoflow.core.config import Config, get_state_dir


class TaskStatus(str, Enum):
    """Valid task statuses in the workflow."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    NEEDS_CHANGES = "needs_changes"
    BLOCKED = "blocked"
    DONE = "done"


class RunResult(str, Enum):
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
        root: Optional[Union[str, Path]] = None,
        state_dir: Optional[Union[str, Path]] = None,
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
        cwd: Optional[Path] = None,
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
        """
        return self.specs_dir / slug

    def task_file(self, spec_slug: str) -> Path:
        """
        Get the task file path for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Path to tasks file
        """
        return self.spec_dir(spec_slug) / "tasks.json"

    def worktree_path(self, spec_slug: str) -> Path:
        """
        Get the worktree path for a spec.

        Args:
            spec_slug: Spec slug identifier

        Returns:
            Path to worktree
        """
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
            "memory_dir": self.memory_dir / "specs" / slug,
            "worktree": worktree,
        }

    def memory_file(self, scope: str, spec_slug: Optional[str] = None) -> Path:
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

    def strategy_memory_file(
        self, scope: str, spec_slug: Optional[str] = None
    ) -> Path:
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
        content: Optional[str] = None,
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
        return self.read_json_or_default(path, {"tasks": [], "updated_at": self.now_stamp()})

    def save_tasks(
        self, spec_slug: str, data: dict[str, Any], *, reason: str = "task_state_updated"
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
        return self.read_json_or_default(files["review_state"], self.review_state_default())

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
            try:
                default = self.read_json(self.system_config_template)
            except (json.JSONDecodeError, OSError):
                pass

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
        agents = {}

        for name, config in data.get("agents", {}).items():
            agents[name] = AgentSpec(
                name=name,
                command=config.get("command", name),
                args=config.get("args", []),
                resume=config.get("resume"),
            )

        return agents

    # === Memory Operations ===

    def append_memory(
        self,
        scope: str,
        content: str,
        spec_slug: Optional[str] = None,
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
        self, spec_slug: str, scopes: Optional[list[str]] = None
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
        self, scope: str, spec_slug: Optional[str] = None
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
        self, scope: str, payload: dict[str, Any], spec_slug: Optional[str] = None
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
        with open(files["events"], "r", encoding="utf-8") as f:
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
        memory = self.load_strategy_memory("workflow", spec_slug)
        return {
            "reflections_count": len(memory.get("reflections", [])),
            "playbook_count": len(memory.get("playbook", [])),
            "counters": memory.get("counters", {}),
            "updated_at": memory.get("updated_at", ""),
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
