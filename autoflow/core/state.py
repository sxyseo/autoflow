"""
Autoflow State Management Module

Provides persistent state management with atomic writes for specs, tasks,
runs, and memory. Implements crash-safe file operations using write-to-temp
and rename pattern.

Usage:
    from autoflow.core.state import StateManager, read_json, write_json

    # Using the StateManager
    state = StateManager(".autoflow")
    state.save_task("task-001", {"status": "in_progress"})
    task = state.load_task("task-001")

    # Using convenience functions
    write_json("path/to/file.json", {"data": "value"})
    data = read_json("path/to/file.json")
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, TypeVar, Union

from pydantic import BaseModel, Field

from autoflow.core.sanitization import sanitize_dict

# Type alias for JSON-serializable data
JSONData = dict[str, Any] | list[Any] | str | int | float | bool | None
T = TypeVar("T")


class TaskStatus(str, Enum):
    """Status of a task in the system."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    """Status of an agent run."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class ParallelGroupStatus(str, Enum):
    """Status of a parallel task group."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """Represents a task in the system."""

    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5  # 1-10, higher is more urgent
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    assigned_agent: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class Run(BaseModel):
    """Represents an agent execution run."""

    id: str
    task_id: Optional[str] = None
    agent: str
    status: RunStatus = RunStatus.STARTED
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    workdir: str = "."
    command: Optional[str] = None
    exit_code: Optional[int] = None
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def complete(
        self,
        status: RunStatus = RunStatus.COMPLETED,
        exit_code: Optional[int] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Mark the run as completed."""
        self.status = status
        self.completed_at = datetime.utcnow()
        self.duration_seconds = (
            self.completed_at - self.started_at
        ).total_seconds()
        self.exit_code = exit_code
        self.output = output
        self.error = error


class Spec(BaseModel):
    """Represents a specification document."""

    id: str
    title: str
    content: str
    version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Memory(BaseModel):
    """Represents a memory entry for context persistence."""

    id: str
    key: str
    value: Any
    category: str = "general"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if this memory entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


class ParallelTaskGroup(BaseModel):
    """Represents a group of tasks to be executed in parallel."""

    id: str
    title: str
    description: str = ""
    status: ParallelGroupStatus = ParallelGroupStatus.PENDING
    task_ids: list[str] = Field(default_factory=list)
    max_parallel: int = 3  # Maximum number of parallel tasks
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()


class StateManager:
    """
    Manages persistent state for Autoflow.

    Provides atomic file operations with crash safety using the
    write-to-temporary-and-rename pattern. State is organized into:
    - specs/: Specification documents
    - specs_archive/: Archived specification documents
    - tasks/: Task definitions and state
    - runs/: Agent execution runs
    - memory/: Persistent memory/context
    - workspaces/: Shared collaboration workspaces
    - activities/: Activity feed and event tracking
    - notifications/: User notifications and alerts

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        state_dir: Root directory for state storage
        backup_dir: Directory for backup files

    Example:
        >>> state = StateManager(".autoflow")
        >>> state.initialize()
        >>> state.save_task("task-001", {"title": "Fix bug"})
        >>> task = state.load_task("task-001")
    """

    # Subdirectories within state directory
    SPECS_DIR = "specs"
    SPECS_ARCHIVE_DIR = "specs_archive"
    TASKS_DIR = "tasks"
    RUNS_DIR = "runs"
    MEMORY_DIR = "memory"
    REPOSITORIES_DIR = "repositories"
    DEPENDENCIES_DIR = "dependencies"
    PARALLEL_DIR = "parallel"
    WORKSPACES_DIR = "workspaces"
    ACTIVITIES_DIR = "activities"
    NOTIFICATIONS_DIR = "notifications"
    BACKUP_DIR = "backups"

    def __init__(self, state_dir: Union[str, Path]):
        """
        Initialize the StateManager.

        Args:
            state_dir: Root directory for state storage.
                       Will be created if it doesn't exist.
        """
        self.state_dir = Path(state_dir).resolve()
        self.backup_dir = self.state_dir / self.BACKUP_DIR

    @property
    def specs_dir(self) -> Path:
        """Path to specs directory."""
        return self.state_dir / self.SPECS_DIR

    @property
    def archive_dir(self) -> Path:
        """Path to specs archive directory."""
        return self.state_dir / self.SPECS_ARCHIVE_DIR

    @property
    def tasks_dir(self) -> Path:
        """Path to tasks directory."""
        return self.state_dir / self.TASKS_DIR

    @property
    def runs_dir(self) -> Path:
        """Path to runs directory."""
        return self.state_dir / self.RUNS_DIR

    @property
    def memory_dir(self) -> Path:
        """Path to memory directory."""
        return self.state_dir / self.MEMORY_DIR

    @property
    def repositories_dir(self) -> Path:
        """Path to repositories directory."""
        return self.state_dir / self.REPOSITORIES_DIR

    @property
    def dependencies_dir(self) -> Path:
        """Path to dependencies directory."""
        return self.state_dir / self.DEPENDENCIES_DIR

    @property
    def parallel_dir(self) -> Path:
        """Path to parallel groups directory."""
        return self.state_dir / self.PARALLEL_DIR

    @property
    def workspaces_dir(self) -> Path:
        """Path to workspaces directory."""
        return self.state_dir / self.WORKSPACES_DIR

    @property
    def activities_dir(self) -> Path:
        """Path to activities directory."""
        return self.state_dir / self.ACTIVITIES_DIR

    @property
    def notifications_dir(self) -> Path:
        """Path to notifications directory."""
        return self.state_dir / self.NOTIFICATIONS_DIR

    def initialize(self) -> None:
        """
        Initialize the state directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> state = StateManager(".autoflow")
            >>> state.initialize()
            >>> assert state.state_dir.exists()
        """
        # Create main directories
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.specs_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)
        self.tasks_dir.mkdir(exist_ok=True)
        self.runs_dir.mkdir(exist_ok=True)
        self.memory_dir.mkdir(exist_ok=True)
        self.repositories_dir.mkdir(exist_ok=True)
        self.dependencies_dir.mkdir(exist_ok=True)
        self.parallel_dir.mkdir(exist_ok=True)
        self.workspaces_dir.mkdir(exist_ok=True)
        self.activities_dir.mkdir(exist_ok=True)
        self.notifications_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        # Resolve both paths to handle symlinks
        resolved_file = file_path.resolve()
        resolved_state_dir = self.state_dir.resolve()
        relative = resolved_file.relative_to(resolved_state_dir)
        return self.backup_dir / f"{relative}.bak"

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of an existing file.

        Only creates backups for files within the state directory.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if file doesn't exist or is outside state_dir
        """
        if not file_path.exists():
            return None

        # Only create backups for files within state directory
        try:
            file_path.resolve().relative_to(self.state_dir.resolve())
        except ValueError:
            # File is outside state directory, skip backup
            return None

        backup_path = self._get_backup_path(file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path

    def _restore_backup(self, file_path: Path) -> bool:
        """
        Restore a file from its backup.

        Only restores backups for files within the state directory.

        Args:
            file_path: Path to the file to restore

        Returns:
            True if restored, False if no backup exists or is outside state_dir
        """
        # Only restore backups for files within state directory
        try:
            file_path.resolve().relative_to(self.state_dir.resolve())
        except ValueError:
            # File is outside state directory, skip restore
            return False

        backup_path = self._get_backup_path(file_path)
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
            return True
        return False

    # === Generic JSON Operations ===

    def read_json(
        self,
        file_path: Union[str, Path],
        default: Optional[T] = None,
    ) -> Union[JSONData, T]:
        """
        Read JSON data from a file.

        Args:
            file_path: Path to the JSON file
            default: Default value if file doesn't exist or is invalid

        Returns:
            Parsed JSON data or default value

        Raises:
            ValueError: If file contains invalid JSON and no default provided

        Example:
            >>> data = state.read_json("data.json", default={})
        """
        path = Path(file_path)
        if not path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(f"File not found: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Try to restore from backup
            if self._restore_backup(path):
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            if default is not None:
                return default
            raise ValueError(f"Invalid JSON in {path}: {e}") from e

    def write_json(
        self,
        file_path: Union[str, Path],
        data: JSONData,
        indent: int = 2,
    ) -> Path:
        """
        Write JSON data to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.
        Creates parent directories if needed. Sanitizes sensitive data
        before writing to prevent information disclosure.

        Args:
            file_path: Destination path
            data: JSON-serializable data
            indent: Indentation level for pretty printing

        Returns:
            Path to the written file

        Raises:
            OSError: If write operation fails

        Example:
            >>> state.write_json("data.json", {"key": "value"})
        """
        path = Path(file_path).resolve()

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(path)

        # Sanitize data to remove sensitive information
        sanitized_data = sanitize_dict(data) if isinstance(data, dict) else data

        # Write to temporary file in same directory (ensures same filesystem)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(sanitized_data, f, indent=indent, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, path)
            return path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    # === Task Operations ===

    def save_task(self, task_id: str, task_data: dict[str, Any]) -> Path:
        """
        Save a task to the state.

        Args:
            task_id: Unique task identifier
            task_data: Task data dictionary

        Returns:
            Path to the saved task file

        Example:
            >>> state.save_task("task-001", {
            ...     "title": "Fix bug",
            ...     "status": "in_progress"
            ... })
        """
        # Ensure timestamps
        if "created_at" not in task_data:
            task_data["created_at"] = datetime.utcnow().isoformat()
        task_data["updated_at"] = datetime.utcnow().isoformat()

        file_path = self.tasks_dir / f"{task_id}.json"
        return self.write_json(file_path, task_data)

    def load_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """
        Load a task from the state.

        Args:
            task_id: Task identifier

        Returns:
            Task data dictionary or None if not found

        Example:
            >>> task = state.load_task("task-001")
            >>> if task:
            ...     print(task["title"])
        """
        file_path = self.tasks_dir / f"{task_id}.json"
        try:
            return self.read_json(file_path)
        except FileNotFoundError:
            return None

    def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        agent: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        List tasks, optionally filtered.

        Args:
            status: Filter by task status
            agent: Filter by assigned agent

        Returns:
            List of task dictionaries

        Example:
            >>> pending_tasks = state.list_tasks(status=TaskStatus.PENDING)
        """
        tasks = []
        if not self.tasks_dir.exists():
            return tasks

        for task_file in self.tasks_dir.glob("*.json"):
            try:
                task = self.read_json(task_file)
                if status and task.get("status") != status.value:
                    continue
                if agent and task.get("assigned_agent") != agent:
                    continue
                tasks.append(task)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by created_at descending
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks

    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task from the state.

        Args:
            task_id: Task identifier

        Returns:
            True if deleted, False if not found
        """
        file_path = self.tasks_dir / f"{task_id}.json"
        if file_path.exists():
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    # === Parallel Group Operations ===

    def save_parallel_group(
        self, group_id: str, group_data: dict[str, Any]
    ) -> Path:
        """
        Save a parallel task group to the state.

        Args:
            group_id: Unique group identifier
            group_data: Group data dictionary

        Returns:
            Path to the saved group file

        Example:
            >>> state.save_parallel_group("group-001", {
            ...     "title": "Parallel bug fixes",
            ...     "task_ids": ["task-001", "task-002"],
            ...     "max_parallel": 3
            ... })
        """
        # Ensure timestamps
        if "created_at" not in group_data:
            group_data["created_at"] = datetime.utcnow().isoformat()
        group_data["updated_at"] = datetime.utcnow().isoformat()

        file_path = self.parallel_dir / f"{group_id}.json"
        return self.write_json(file_path, group_data)

    def load_parallel_group(
        self, group_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Load a parallel task group from the state.

        Args:
            group_id: Group identifier

        Returns:
            Group data dictionary or None if not found

        Example:
            >>> group = state.load_parallel_group("group-001")
            >>> if group:
            ...     print(group["title"])
        """
        file_path = self.parallel_dir / f"{group_id}.json"
        try:
            return self.read_json(file_path)
        except FileNotFoundError:
            return None

    def list_parallel_groups(
        self,
        status: Optional[ParallelGroupStatus] = None,
    ) -> list[dict[str, Any]]:
        """
        List parallel task groups, optionally filtered.

        Args:
            status: Filter by group status

        Returns:
            List of group dictionaries

        Example:
            >>> active_groups = state.list_parallel_groups(
            ...     status=ParallelGroupStatus.IN_PROGRESS
            ... )
        """
        groups = []
        if not self.parallel_dir.exists():
            return groups

        for group_file in self.parallel_dir.glob("*.json"):
            try:
                group = self.read_json(group_file)
                if status and group.get("status") != status.value:
                    continue
                groups.append(group)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by created_at descending
        groups.sort(key=lambda g: g.get("created_at", ""), reverse=True)
        return groups

    def delete_parallel_group(self, group_id: str) -> bool:
        """
        Delete a parallel task group from the state.

        Args:
            group_id: Group identifier

        Returns:
            True if deleted, False if not found
        """
        file_path = self.parallel_dir / f"{group_id}.json"
        if file_path.exists():
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    # === Run Operations ===

    def save_run(self, run_id: str, run_data: dict[str, Any]) -> Path:
        """
        Save a run to the state.

        Args:
            run_id: Unique run identifier
            run_data: Run data dictionary

        Returns:
            Path to the saved run file

        Example:
            >>> state.save_run("run-001", {
            ...     "agent": "claude-code",
            ...     "status": "running"
            ... })
        """
        file_path = self.runs_dir / f"{run_id}.json"
        return self.write_json(file_path, run_data)

    def load_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """
        Load a run from the state.

        Args:
            run_id: Run identifier

        Returns:
            Run data dictionary or None if not found
        """
        file_path = self.runs_dir / f"{run_id}.json"
        try:
            return self.read_json(file_path)
        except FileNotFoundError:
            return None

    def list_runs(
        self,
        status: Optional[RunStatus] = None,
        agent: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List runs, optionally filtered.

        Args:
            status: Filter by run status
            agent: Filter by agent name
            limit: Maximum number of runs to return

        Returns:
            List of run dictionaries
        """
        runs = []
        if not self.runs_dir.exists():
            return runs

        for run_file in self.runs_dir.glob("*.json"):
            try:
                run = self.read_json(run_file)
                if status and run.get("status") != status.value:
                    continue
                if agent and run.get("agent") != agent:
                    continue
                runs.append(run)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by started_at descending
        runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return runs[:limit]

    # === Spec Operations ===

    def save_spec(self, spec_id: str, spec_data: dict[str, Any]) -> Path:
        """
        Save a specification to the state.

        Args:
            spec_id: Unique spec identifier
            spec_data: Spec data dictionary

        Returns:
            Path to the saved spec file
        """
        # Ensure timestamps
        if "created_at" not in spec_data:
            spec_data["created_at"] = datetime.utcnow().isoformat()
        spec_data["updated_at"] = datetime.utcnow().isoformat()

        file_path = self.specs_dir / f"{spec_id}.json"
        return self.write_json(file_path, spec_data)

    def load_spec(self, spec_id: str) -> Optional[dict[str, Any]]:
        """
        Load a specification from the state.

        Args:
            spec_id: Spec identifier

        Returns:
            Spec data dictionary or None if not found
        """
        file_path = self.specs_dir / f"{spec_id}.json"
        try:
            return self.read_json(file_path)
        except FileNotFoundError:
            return None

    def list_specs(
        self,
        tags: Optional[list[str]] = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """
        List specifications, optionally filtered by tags.

        Args:
            tags: Filter by tags (specs must have all tags)
            include_archived: If True, include archived specs in results

        Returns:
            List of spec dictionaries
        """
        specs = []
        if not self.specs_dir.exists():
            return specs

        for spec_file in self.specs_dir.glob("*.json"):
            try:
                spec = self.read_json(spec_file)
                if tags:
                    spec_tags = set(spec.get("tags", []))
                    if not set(tags).issubset(spec_tags):
                        continue
                specs.append(spec)
            except (json.JSONDecodeError, KeyError):
                continue

        # Optionally include archived specs
        if include_archived and self.archive_dir.exists():
            for spec_file in self.archive_dir.glob("*.json"):
                try:
                    spec = self.read_json(spec_file)
                    if tags:
                        spec_tags = set(spec.get("tags", []))
                        if not set(tags).issubset(spec_tags):
                            continue
                    specs.append(spec)
                except (json.JSONDecodeError, KeyError):
                    continue

        # Sort by created_at descending
        specs.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return specs

    def archive_spec(self, spec_id: str) -> bool:
        """
        Archive a specification by moving it to the archive directory.

        Args:
            spec_id: Spec identifier

        Returns:
            True if archived, False if not found

        Example:
            >>> success = state.archive_spec("spec-001")
        """
        source_path = self.specs_dir / f"{spec_id}.json"

        if not source_path.exists():
            return False

        # Ensure archive directory exists
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # Create backup before moving
        self._create_backup(source_path)

        # Read spec to update metadata
        spec_data = self.read_json(source_path)

        # Add archived flag to metadata
        if "metadata" not in spec_data:
            spec_data["metadata"] = {}
        spec_data["metadata"]["archived"] = True

        # Write updated spec back to source before moving
        self.write_json(source_path, spec_data)

        # Move to archive directory
        target_path = self.archive_dir / f"{spec_id}.json"
        shutil.move(str(source_path), str(target_path))

        return True

    def list_archived_specs(self, tags: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """
        List archived specifications, optionally filtered by tags.

        Args:
            tags: Filter by tags (specs must have all tags)

        Returns:
            List of archived spec dictionaries

        Example:
            >>> archived = state.list_archived_specs()
        """
        specs = []
        if not self.archive_dir.exists():
            return specs

        for spec_file in self.archive_dir.glob("*.json"):
            try:
                spec = self.read_json(spec_file)
                if tags:
                    spec_tags = set(spec.get("tags", []))
                    if not set(tags).issubset(spec_tags):
                        continue
                specs.append(spec)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by created_at descending
        specs.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return specs

    # === Memory Operations ===

    def save_memory(
        self,
        key: str,
        value: Any,
        category: str = "general",
        expires_in_seconds: Optional[int] = None,
    ) -> Path:
        """
        Save a memory entry.

        Args:
            key: Unique key for the memory
            value: Value to store
            category: Category for grouping
            expires_in_seconds: Optional expiration time in seconds

        Returns:
            Path to the saved memory file

        Example:
            >>> state.save_memory("last_branch", "feature-x", category="git")
        """
        memory_id = key.replace("/", "_").replace("\\", "_")
        memory_data = {
            "id": memory_id,
            "key": key,
            "value": value,
            "category": category,
            "created_at": datetime.utcnow().isoformat(),
        }

        if expires_in_seconds is not None:
            expires_at = datetime.utcnow().timestamp() + expires_in_seconds
            memory_data["expires_at"] = datetime.fromtimestamp(
                expires_at
            ).isoformat()

        file_path = self.memory_dir / f"{memory_id}.json"
        return self.write_json(file_path, memory_data)

    def load_memory(self, key: str) -> Optional[Any]:
        """
        Load a memory entry by key.

        Args:
            key: Memory key

        Returns:
            Stored value or None if not found/expired
        """
        memory_id = key.replace("/", "_").replace("\\", "_")
        file_path = self.memory_dir / f"{memory_id}.json"

        try:
            data = self.read_json(file_path)
            # Check expiration
            if "expires_at" in data:
                expires_at = datetime.fromisoformat(data["expires_at"])
                if datetime.utcnow() > expires_at:
                    # Memory expired, delete it
                    file_path.unlink()
                    return None
            return data.get("value")
        except FileNotFoundError:
            return None

    def list_memory(
        self,
        category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        List memory entries, optionally filtered by category.

        Args:
            category: Filter by category

        Returns:
            List of memory entries
        """
        memories = []
        if not self.memory_dir.exists():
            return memories

        for memory_file in self.memory_dir.glob("*.json"):
            try:
                memory = self.read_json(memory_file)

                # Check expiration
                if "expires_at" in memory:
                    expires_at = datetime.fromisoformat(memory["expires_at"])
                    if datetime.utcnow() > expires_at:
                        memory_file.unlink()
                        continue

                if category and memory.get("category") != category:
                    continue
                memories.append(memory)
            except (json.JSONDecodeError, KeyError):
                continue

        return memories

    def delete_memory(self, key: str) -> bool:
        """
        Delete a memory entry.

        Args:
            key: Memory key

        Returns:
            True if deleted, False if not found
        """
        memory_id = key.replace("/", "_").replace("\\", "_")
        file_path = self.memory_dir / f"{memory_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    # === Utility Methods ===

    def get_status(self) -> dict[str, Any]:
        """
        Get status summary of the state.

        Returns:
            Dictionary with counts and status information

        Example:
            >>> status = state.get_status()
            >>> print(f"Tasks: {status['tasks']['total']}")
        """
        return {
            "state_dir": str(self.state_dir),
            "initialized": self.state_dir.exists(),
            "tasks": {
                "total": len(list(self.tasks_dir.glob("*.json")))
                if self.tasks_dir.exists()
                else 0,
                "by_status": self._count_by_status(self.tasks_dir, "status"),
            },
            "runs": {
                "total": len(list(self.runs_dir.glob("*.json")))
                if self.runs_dir.exists()
                else 0,
                "by_status": self._count_by_status(self.runs_dir, "status"),
            },
            "specs": {
                "total": len(list(self.specs_dir.glob("*.json")))
                if self.specs_dir.exists()
                else 0,
            },
            "memory": {
                "total": len(list(self.memory_dir.glob("*.json")))
                if self.memory_dir.exists()
                else 0,
            },
            "parallel": {
                "total": len(list(self.parallel_dir.glob("*.json")))
                if self.parallel_dir.exists()
                else 0,
                "by_status": self._count_by_status(
                    self.parallel_dir, "status"
                ),
            },
            "workspaces": {
                "total": len(list(self.workspaces_dir.glob("*.json")))
                if self.workspaces_dir.exists()
                else 0,
            },
            "activities": {
                "total": len(list(self.activities_dir.glob("*.json")))
                if self.activities_dir.exists()
                else 0,
            },
            "notifications": {
                "total": len(list(self.notifications_dir.glob("*.json")))
                if self.notifications_dir.exists()
                else 0,
            },
        }

    def _count_by_status(
        self, directory: Path, status_field: str
    ) -> dict[str, int]:
        """Count items by status field."""
        counts: dict[str, int] = {}
        if not directory.exists():
            return counts

        for file_path in directory.glob("*.json"):
            try:
                data = self.read_json(file_path)
                status = data.get(status_field, "unknown")
                counts[status] = counts.get(status, 0) + 1
            except (json.JSONDecodeError, KeyError):
                counts["error"] = counts.get("error", 0) + 1

        return counts

    def cleanup_expired(self) -> int:
        """
        Clean up expired memory entries.

        Returns:
            Number of entries removed
        """
        removed = 0
        if not self.memory_dir.exists():
            return removed

        for memory_file in self.memory_dir.glob("*.json"):
            try:
                memory = self.read_json(memory_file)
                if "expires_at" in memory:
                    expires_at = datetime.fromisoformat(memory["expires_at"])
                    if datetime.utcnow() > expires_at:
                        memory_file.unlink()
                        removed += 1
            except (json.JSONDecodeError, KeyError):
                continue

        return removed

    def compact_backups(self, max_age_days: int = 7) -> int:
        """
        Remove old backup files.

        Args:
            max_age_days: Maximum age of backups to keep

        Returns:
            Number of backups removed
        """
        removed = 0
        if not self.backup_dir.exists():
            return removed

        cutoff = datetime.utcnow().timestamp() - (max_age_days * 86400)

        for backup_file in self.backup_dir.glob("**/*.bak"):
            if backup_file.stat().st_mtime < cutoff:
                backup_file.unlink()
                removed += 1

        return removed


# === Module-level convenience functions ===

def read_json(
    file_path: Union[str, Path],
    default: Optional[T] = None,
) -> Union[JSONData, T]:
    """
    Read JSON data from a file.

    Convenience function that creates a temporary StateManager.

    Args:
        file_path: Path to the JSON file
        default: Default value if file doesn't exist or is invalid

    Returns:
        Parsed JSON data or default value

    Example:
        >>> data = read_json("config.json", default={})
    """
    manager = StateManager(Path(file_path).parent)
    return manager.read_json(file_path, default=default)


def write_json(
    file_path: Union[str, Path],
    data: JSONData,
    indent: int = 2,
) -> Path:
    """
    Write JSON data to a file atomically.

    Convenience function that creates a temporary StateManager.
    Uses write-to-temporary-and-rename pattern for crash safety.

    Args:
        file_path: Destination path
        data: JSON-serializable data
        indent: Indentation level for pretty printing

    Returns:
        Path to the written file

    Example:
        >>> write_json("output.json", {"result": "success"})
    """
    manager = StateManager(Path(file_path).parent)
    return manager.write_json(file_path, data, indent=indent)
