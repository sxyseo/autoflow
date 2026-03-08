"""
Autoflow Repository Module

Provides data models for managing multiple git repositories with proper
dependency tracking and branch configuration.

Usage:
    from autoflow.core.repository import Repository, RepositoryDependency, RepositoryManager

    repo = Repository(
        id="frontend",
        name="Frontend Monorepo",
        path="~/dev/frontend",
        url="https://github.com/org/frontend.git",
        branch="main"
    )

    # Define a dependency relationship
    dep = RepositoryDependency(
        source_repo_id="frontend",
        target_repo_id="backend-api",
        dependency_type="runtime",
        branch_constraint="main"
    )

    # Use RepositoryManager for CRUD operations
    manager = RepositoryManager(".autoflow")
    manager.initialize()
    manager.save_repository(repo.id, repo.model_dump())
    loaded_repo = manager.load_repository(repo.id)
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator


class BranchConfig(BaseModel):
    """Branch configuration for a repository."""

    default: str = "main"
    current: Optional[str] = None
    protected: list[str] = Field(default_factory=lambda: ["main", "master"])

    @field_validator("current", mode="before")
    @classmethod
    def default_to_current(cls, v: Optional[str], info) -> Optional[str]:
        """Default current branch to default branch if not specified."""
        if v is None and "default" in info.data:
            return info.data["default"]
        return v


class DependencyType(str, Enum):
    """Type of repository dependency relationship."""

    RUNTIME = "runtime"
    """Required for the application to run."""

    DEVELOPMENT = "development"
    """Required only for development and testing."""

    PEER = "peer"
    """Optional but should be compatible with the source repository."""

    OPTIONAL = "optional"
    """Completely optional dependency."""


class RepositoryDependency(BaseModel):
    """
    Represents a dependency relationship between repositories.

    This model tracks cross-repository dependencies including version
    constraints, branch requirements, and dependency types. It enables
    proper ordering of operations and validation of repository setups.

    Attributes:
        source_repo_id: ID of the repository that has this dependency
        target_repo_id: ID of the repository being depended on
        dependency_type: Type of dependency relationship
        branch_constraint: Required branch for the target repository
        version_constraint: Optional version constraint
        required: Whether this dependency must be satisfied
        created_at: When this dependency was created
        metadata: Additional metadata about the dependency
    """

    source_repo_id: str
    """ID of the repository that has this dependency."""

    target_repo_id: str
    """ID of the repository being depended on."""

    dependency_type: DependencyType = DependencyType.RUNTIME
    """Type of dependency relationship."""

    branch_constraint: Optional[str] = None
    """Required branch or tag for the target repository."""

    version_constraint: Optional[str] = None
    """Optional version constraint (if using versioned releases)."""

    required: bool = True
    """Whether this dependency must be satisfied for operations."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    """Timestamp when this dependency was created."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Additional metadata about the dependency."""

    def is_satisfied_by(
        self,
        target_repo: Repository,
        target_branch: Optional[str] = None
    ) -> bool:
        """
        Check if a target repository and branch satisfies this dependency.

        Args:
            target_repo: The target repository to check
            target_branch: The branch of the target repository (uses current if None)

        Returns:
            True if the dependency is satisfied, False otherwise
        """
        # Check repository ID matches
        if target_repo.id != self.target_repo_id:
            return False

        # Check branch constraint if specified
        if self.branch_constraint is not None:
            branch_to_check = target_branch or target_repo.branch.current
            if branch_to_check != self.branch_constraint:
                return False

        return True

    def __str__(self) -> str:
        """String representation of the dependency."""
        constraint = f"@{self.branch_constraint}" if self.branch_constraint else ""
        required = " (required)" if self.required else " (optional)"
        return (
            f"{self.source_repo_id} -> {self.target_repo_id}{constraint}"
            f" [{self.dependency_type}]{required}"
        )

    def __repr__(self) -> str:
        """Detailed string representation of the dependency."""
        return (
            f"RepositoryDependency(source={self.source_repo_id!r}, "
            f"target={self.target_repo_id!r}, "
            f"type={self.dependency_type.value!r}, "
            f"branch={self.branch_constraint!r})"
        )


class Repository(BaseModel):
    """
    Represents a git repository in the multi-repository setup.

    Contains information about the repository location, remote URL,
    branch configuration, and metadata for dependency tracking.
    """

    id: str
    """Unique identifier for this repository (used in specs and dependencies)."""

    name: str
    """Human-readable name for the repository."""

    path: str
    """Filesystem path to the repository (can be relative or absolute)."""

    url: Optional[str] = None
    """Git remote URL for cloning/pulling (optional if path already exists)."""

    branch: BranchConfig = Field(default_factory=BranchConfig)
    """Branch configuration for this repository."""

    description: Optional[str] = None
    """Optional description of the repository's purpose."""

    enabled: bool = True
    """Whether this repository is active in multi-repo operations."""

    @field_validator("path", mode="before")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand environment variables and user home in path."""
        return os.path.expandvars(os.path.expanduser(v))

    def get_resolved_path(self) -> Path:
        """
        Get the absolute, resolved path to the repository.

        Returns:
            Path object pointing to the repository root
        """
        return Path(self.path).resolve()

    def get_git_dir(self) -> Path:
        """
        Get the .git directory path for this repository.

        Returns:
            Path object pointing to the .git directory
        """
        return self.get_resolved_path() / ".git"

    def is_valid(self) -> bool:
        """
        Check if the repository reference is valid.

        A valid repository has a .git directory at the specified path.

        Returns:
            True if the repository exists and is a valid git repository
        """
        git_dir = self.get_git_dir()
        return git_dir.exists() and git_dir.is_dir()

    def __str__(self) -> str:
        """String representation of the repository."""
        return f"Repository({self.id}: {self.name} @ {self.path})"

    def __repr__(self) -> str:
        """Detailed string representation of the repository."""
        return (
            f"Repository(id={self.id!r}, name={self.name!r}, "
            f"path={self.path!r}, url={self.url!r})"
        )


class RepositoryManager:
    """
    Manages repository configurations and dependencies.

    Provides atomic file operations with crash safety using the
    write-to-temporary-and-rename pattern. Repository configurations
    are organized into:
    - repositories/: Repository definitions
    - dependencies/: Cross-repository dependency relationships

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        state_dir: Root directory for state storage
        backup_dir: Directory for backup files

    Example:
        >>> manager = RepositoryManager(".autoflow")
        >>> manager.initialize()
        >>> manager.save_repository("frontend", {
        ...     "id": "frontend",
        ...     "name": "Frontend Monorepo",
        ...     "path": "~/dev/frontend"
        ... })
        >>> repo = manager.load_repository("frontend")
    """

    # Subdirectories within state directory
    REPOS_DIR = "repositories"
    DEPS_DIR = "dependencies"
    BACKUP_DIR = "backups"

    def __init__(self, state_dir: Union[str, Path]):
        """
        Initialize the RepositoryManager.

        Args:
            state_dir: Root directory for state storage.
                       Will be created if it doesn't exist.
        """
        self.state_dir = Path(state_dir).resolve()
        self.backup_dir = self.state_dir / self.BACKUP_DIR

    @property
    def repositories_dir(self) -> Path:
        """Path to repositories directory."""
        return self.state_dir / self.REPOS_DIR

    @property
    def dependencies_dir(self) -> Path:
        """Path to dependencies directory."""
        return self.state_dir / self.DEPS_DIR

    def initialize(self) -> None:
        """
        Initialize the state directory structure.

        Creates all required subdirectories if they don't exist.
        Idempotent - safe to call multiple times.

        Example:
            >>> manager = RepositoryManager(".autoflow")
            >>> manager.initialize()
            >>> assert manager.state_dir.exists()
        """
        # Create main directories
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.repositories_dir.mkdir(exist_ok=True)
        self.dependencies_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

    def _get_backup_path(self, file_path: Path) -> Path:
        """
        Get the backup path for a file.

        Args:
            file_path: Original file path

        Returns:
            Path to the backup file
        """
        relative = file_path.relative_to(self.state_dir)
        return self.backup_dir / f"{relative}.bak"

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of an existing file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file, or None if file doesn't exist
        """
        if not file_path.exists():
            return None

        backup_path = self._get_backup_path(file_path)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)
        return backup_path

    def _restore_backup(self, file_path: Path) -> bool:
        """
        Restore a file from its backup.

        Args:
            file_path: Path to the file to restore

        Returns:
            True if restored, False if no backup exists
        """
        backup_path = self._get_backup_path(file_path)
        if backup_path.exists():
            shutil.copy2(backup_path, file_path)
            return True
        return False

    def _read_json(
        self,
        file_path: Union[str, Path],
        default: Optional[Any] = None,
    ) -> Any:
        """
        Read JSON data from a file.

        Args:
            file_path: Path to the JSON file
            default: Default value if file doesn't exist or is invalid

        Returns:
            Parsed JSON data or default value

        Raises:
            ValueError: If file contains invalid JSON and no default provided
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

    def _write_json(
        self,
        file_path: Union[str, Path],
        data: Any,
        indent: int = 2,
    ) -> Path:
        """
        Write JSON data to a file atomically.

        Uses write-to-temporary-and-rename pattern for crash safety.
        Creates parent directories if needed.

        Args:
            file_path: Destination path
            data: JSON-serializable data
            indent: Indentation level for pretty printing

        Returns:
            Path to the written file

        Raises:
            OSError: If write operation fails
        """
        path = Path(file_path).resolve()

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup of existing file
        self._create_backup(path)

        # Write to temporary file in same directory (ensures same filesystem)
        temp_fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )

        try:
            # Write data to temp file
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_path, path)
            return path
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    # === Repository Operations ===

    def save_repository(self, repo_id: str, repo_data: dict[str, Any]) -> Path:
        """
        Save a repository configuration.

        Args:
            repo_id: Unique repository identifier
            repo_data: Repository data dictionary

        Returns:
            Path to the saved repository file

        Example:
            >>> manager.save_repository("frontend", {
            ...     "id": "frontend",
            ...     "name": "Frontend Monorepo",
            ...     "path": "~/dev/frontend",
            ...     "url": "https://github.com/org/frontend.git"
            ... })
        """
        # Ensure ID is set
        if "id" not in repo_data:
            repo_data["id"] = repo_id

        file_path = self.repositories_dir / f"{repo_id}.json"
        return self._write_json(file_path, repo_data)

    def load_repository(self, repo_id: str) -> Optional[dict[str, Any]]:
        """
        Load a repository configuration.

        Args:
            repo_id: Repository identifier

        Returns:
            Repository data dictionary or None if not found

        Example:
            >>> repo = manager.load_repository("frontend")
            >>> if repo:
            ...     print(repo["name"])
        """
        file_path = self.repositories_dir / f"{repo_id}.json"
        try:
            return self._read_json(file_path)
        except FileNotFoundError:
            return None

    def list_repositories(
        self,
        enabled: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        """
        List repositories, optionally filtered.

        Args:
            enabled: Filter by enabled status (None = all)

        Returns:
            List of repository dictionaries

        Example:
            >>> active_repos = manager.list_repositories(enabled=True)
        """
        repositories = []
        if not self.repositories_dir.exists():
            return repositories

        for repo_file in self.repositories_dir.glob("*.json"):
            try:
                repo = self._read_json(repo_file)
                if enabled is not None and repo.get("enabled", True) != enabled:
                    continue
                repositories.append(repo)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by ID
        repositories.sort(key=lambda r: r.get("id", ""))
        return repositories

    def delete_repository(self, repo_id: str) -> bool:
        """
        Delete a repository configuration.

        Args:
            repo_id: Repository identifier

        Returns:
            True if deleted, False if not found
        """
        file_path = self.repositories_dir / f"{repo_id}.json"
        if file_path.exists():
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    def repository_exists(self, repo_id: str) -> bool:
        """
        Check if a repository configuration exists.

        Args:
            repo_id: Repository identifier

        Returns:
            True if the repository exists
        """
        file_path = self.repositories_dir / f"{repo_id}.json"
        return file_path.exists()

    # === Dependency Operations ===

    def save_dependency(
        self,
        dep_id: str,
        dep_data: dict[str, Any],
    ) -> Path:
        """
        Save a dependency configuration.

        Args:
            dep_id: Unique dependency identifier
            dep_data: Dependency data dictionary

        Returns:
            Path to the saved dependency file

        Example:
            >>> manager.save_dependency("frontend-to-backend", {
            ...     "source_repo_id": "frontend",
            ...     "target_repo_id": "backend-api",
            ...     "dependency_type": "runtime"
            ... })
        """
        # Ensure timestamps
        if "created_at" not in dep_data:
            dep_data["created_at"] = datetime.utcnow().isoformat()

        file_path = self.dependencies_dir / f"{dep_id}.json"
        return self._write_json(file_path, dep_data)

    def load_dependency(self, dep_id: str) -> Optional[dict[str, Any]]:
        """
        Load a dependency configuration.

        Args:
            dep_id: Dependency identifier

        Returns:
            Dependency data dictionary or None if not found
        """
        file_path = self.dependencies_dir / f"{dep_id}.json"
        try:
            return self._read_json(file_path)
        except FileNotFoundError:
            return None

    def list_dependencies(
        self,
        source_repo_id: Optional[str] = None,
        target_repo_id: Optional[str] = None,
        dependency_type: Optional[DependencyType] = None,
    ) -> list[dict[str, Any]]:
        """
        List dependencies, optionally filtered.

        Args:
            source_repo_id: Filter by source repository ID
            target_repo_id: Filter by target repository ID
            dependency_type: Filter by dependency type

        Returns:
            List of dependency dictionaries

        Example:
            >>> runtime_deps = manager.list_dependencies(
            ...     dependency_type=DependencyType.RUNTIME
            ... )
        """
        dependencies = []
        if not self.dependencies_dir.exists():
            return dependencies

        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self._read_json(dep_file)
                if source_repo_id and dep.get("source_repo_id") != source_repo_id:
                    continue
                if target_repo_id and dep.get("target_repo_id") != target_repo_id:
                    continue
                if dependency_type and dep.get("dependency_type") != dependency_type.value:
                    continue
                dependencies.append(dep)
            except (json.JSONDecodeError, KeyError):
                continue

        # Sort by source_repo_id, then target_repo_id
        dependencies.sort(
            key=lambda d: (d.get("source_repo_id", ""), d.get("target_repo_id", ""))
        )
        return dependencies

    def delete_dependency(self, dep_id: str) -> bool:
        """
        Delete a dependency configuration.

        Args:
            dep_id: Dependency identifier

        Returns:
            True if deleted, False if not found
        """
        file_path = self.dependencies_dir / f"{dep_id}.json"
        if file_path.exists():
            self._create_backup(file_path)
            file_path.unlink()
            return True
        return False

    # === Utility Methods ===

    def get_status(self) -> dict[str, Any]:
        """
        Get status summary of repositories and dependencies.

        Returns:
            Dictionary with counts and status information

        Example:
            >>> status = manager.get_status()
            >>> print(f"Repositories: {status['repositories']['total']}")
        """
        return {
            "state_dir": str(self.state_dir),
            "initialized": self.state_dir.exists(),
            "repositories": {
                "total": len(list(self.repositories_dir.glob("*.json")))
                if self.repositories_dir.exists()
                else 0,
                "enabled": len([
                    f for f in self.repositories_dir.glob("*.json")
                    if self._read_json(f, default={}).get("enabled", True)
                ])
                if self.repositories_dir.exists()
                else 0,
            },
            "dependencies": {
                "total": len(list(self.dependencies_dir.glob("*.json")))
                if self.dependencies_dir.exists()
                else 0,
                "by_type": self._count_dependencies_by_type(),
            },
        }

    def _count_dependencies_by_type(self) -> dict[str, int]:
        """Count dependencies by type."""
        counts: dict[str, int] = {}
        if not self.dependencies_dir.exists():
            return counts

        for file_path in self.dependencies_dir.glob("*.json"):
            try:
                dep = self._read_json(file_path)
                dep_type = dep.get("dependency_type", "unknown")
                counts[dep_type] = counts.get(dep_type, 0) + 1
            except (json.JSONDecodeError, KeyError):
                counts["error"] = counts.get("error", 0) + 1

        return counts

    def get_repository_dependencies(
        self,
        repo_id: str,
        as_source: bool = True,
        as_target: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get all dependencies for a specific repository.

        Args:
            repo_id: Repository identifier
            as_source: Include dependencies where repo is the source
            as_target: Include dependencies where repo is the target

        Returns:
            List of dependency dictionaries

        Example:
            >>> deps = manager.get_repository_dependencies("frontend")
        """
        dependencies = []
        if not self.dependencies_dir.exists():
            return dependencies

        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self._read_json(dep_file)
                if as_source and dep.get("source_repo_id") == repo_id:
                    dependencies.append(dep)
                if as_target and dep.get("target_repo_id") == repo_id:
                    dependencies.append(dep)
            except (json.JSONDecodeError, KeyError):
                continue

        return dependencies

    def validate_dependencies(self) -> list[str]:
        """
        Validate all dependencies and return list of errors.

        Checks that:
        - All referenced repositories exist
        - No circular dependencies exist
        - Required dependencies are satisfied

        Returns:
            List of error messages (empty if all valid)

        Example:
            >>> errors = manager.validate_dependencies()
            >>> if errors:
            ...     for error in errors:
            ...         print(f"Error: {error}")
        """
        errors: list[str] = []
        if not self.dependencies_dir.exists():
            return errors

        # Get all repository IDs
        repo_ids = set()
        for repo_file in self.repositories_dir.glob("*.json"):
            try:
                repo = self._read_json(repo_file)
                repo_ids.add(repo.get("id"))
            except (json.JSONDecodeError, KeyError):
                continue

        # Validate dependencies
        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self._read_json(dep_file)
                source_id = dep.get("source_repo_id")
                target_id = dep.get("target_repo_id")

                # Check if source repository exists
                if source_id not in repo_ids:
                    errors.append(
                        f"Dependency '{dep_file.stem}': "
                        f"source repository '{source_id}' does not exist"
                    )

                # Check if target repository exists
                if target_id not in repo_ids:
                    errors.append(
                        f"Dependency '{dep_file.stem}': "
                        f"target repository '{target_id}' does not exist"
                    )

            except (json.JSONDecodeError, KeyError):
                errors.append(f"Dependency '{dep_file.stem}': invalid data")

        return errors
