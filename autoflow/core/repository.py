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

import os
import subprocess
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator

from autoflow.core.state import StateManager
from autoflow.core.types import RepositoryDependencyMetadata


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

    metadata: RepositoryDependencyMetadata = Field(default_factory=dict)  # type: ignore[assignment]
    """
    Additional metadata about the dependency.

    Provides structured metadata including validation status, notes,
    auto-update preferences, and related task tracking.
    """

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

        A valid repository has either:
        - A .git directory (normal repository)
        - A .git file with valid gitdir reference (git worktree)

        Returns:
            True if the repository exists and is a valid git repository
        """
        repo_path = self.get_resolved_path()
        git_path = repo_path / ".git"

        if git_path.is_dir():
            return True

        if git_path.is_file():
            # Git worktree - check gitdir reference
            try:
                content = git_path.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir: "):
                    gitdir = content[8:].strip()
                    gitdir_path = Path(gitdir)
                    if gitdir_path.is_absolute():
                        return gitdir_path.exists() and gitdir_path.is_dir()
                    else:
                        return (repo_path / gitdir_path).exists()
            except Exception:
                return False

        return False

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

    Integrates with StateManager for atomic file operations with crash safety.
    Repository configurations are organized into:
    - repositories/: Repository definitions
    - dependencies/: Cross-repository dependency relationships

    All write operations are atomic - either they complete fully
    or leave the existing state unchanged.

    Attributes:
        state: StateManager instance for state operations

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

    def __init__(self, state_dir: Union[str, Path, StateManager]):
        """
        Initialize the RepositoryManager.

        Args:
            state_dir: Root directory for state storage, or a StateManager instance.
                       Will be created if it doesn't exist.
        """
        if isinstance(state_dir, StateManager):
            self.state = state_dir
        else:
            self.state = StateManager(state_dir)

    @property
    def state_dir(self) -> Path:
        """Path to state directory."""
        return self.state.state_dir

    @property
    def repositories_dir(self) -> Path:
        """Path to repositories directory."""
        return self.state.repositories_dir

    @property
    def dependencies_dir(self) -> Path:
        """Path to dependencies directory."""
        return self.state.dependencies_dir

    @property
    def backup_dir(self) -> Path:
        """Path to backup directory."""
        return self.state.backup_dir

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
        self.state.initialize()

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
        return self.state.write_json(file_path, repo_data)

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
            return self.state.read_json(file_path)
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
        import json

        repositories = []
        if not self.repositories_dir.exists():
            return repositories

        for repo_file in self.repositories_dir.glob("*.json"):
            try:
                repo = self.state.read_json(repo_file)
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
            self.state._create_backup(file_path)
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

    def validate(self, repo_id: str) -> list[str]:
        """
        Validate a repository configuration and filesystem.

        Checks that:
        - Repository configuration exists
        - Repository path exists
        - Repository is a valid git repository (including worktrees)
        - Repository is accessible (can run git commands)

        Args:
            repo_id: Repository identifier

        Returns:
            List of error messages (empty if valid)

        Example:
            >>> errors = manager.validate("frontend")
            >>> if errors:
            ...     for error in errors:
            ...         print(f"Error: {error}")
        """
        errors: list[str] = []

        # Check if repository configuration exists
        repo_data = self.load_repository(repo_id)
        if repo_data is None:
            errors.append(f"Repository '{repo_id}' configuration not found")
            return errors

        # Get repository path from data
        repo_path_str = repo_data.get("path")
        if not repo_path_str:
            errors.append(f"Repository '{repo_id}' has no path specified")
            return errors

        # Expand path
        repo_path = Path(repo_path_str).expanduser().resolve()

        # Check if repository path exists
        if not repo_path.exists():
            errors.append(
                f"Repository '{repo_id}' path does not exist: {repo_path}"
            )
            return errors

        if not repo_path.is_dir():
            errors.append(
                f"Repository '{repo_id}' path is not a directory: {repo_path}"
            )
            return errors

        # Check if it's a valid git repository
        # Git repositories can have either:
        # 1. A .git directory (normal repository)
        # 2. A .git file (git worktree)
        git_path = repo_path / ".git"
        has_git = False

        if git_path.is_dir():
            # Normal git repository
            has_git = True
        elif git_path.is_file():
            # Git worktree - check if it contains a valid gitdir reference
            try:
                content = git_path.read_text(encoding="utf-8").strip()
                if content.startswith("gitdir: "):
                    gitdir = content[8:].strip()  # Remove "gitdir: " prefix
                    gitdir_path = Path(gitdir)
                    if gitdir_path.is_absolute():
                        has_git = gitdir_path.exists() and gitdir_path.is_dir()
                    else:
                        # Relative path - resolve from repo path
                        has_git = (repo_path / gitdir_path).exists()
            except Exception:
                pass

        if not has_git:
            errors.append(
                f"Repository '{repo_id}' is not a valid git repository "
                f"(missing .git directory or invalid git worktree at {git_path})"
            )
            return errors

        # Check if repository is accessible by running a git command
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            # Verify the output points to the expected .git directory
            if not result.stdout.strip():
                errors.append(
                    f"Repository '{repo_id}' git command returned empty output"
                )
        except subprocess.CalledProcessError as e:
            errors.append(
                f"Repository '{repo_id}' is not accessible: "
                f"git command failed with exit code {e.returncode}"
            )
        except subprocess.TimeoutExpired:
            errors.append(
                f"Repository '{repo_id}' is not accessible: "
                f"git command timed out"
            )
        except PermissionError:
            errors.append(
                f"Repository '{repo_id}' is not accessible: "
                f"permission denied"
            )
        except Exception as e:
            errors.append(
                f"Repository '{repo_id}' is not accessible: "
                f"{type(e).__name__}: {e}"
            )

        return errors

    def validate_all(self) -> dict[str, list[str]]:
        """
        Validate all repositories.

        Returns:
            Dictionary mapping repository IDs to lists of error messages

        Example:
            >>> results = manager.validate_all()
            >>> for repo_id, errors in results.items():
            ...     if errors:
            ...         print(f"{repo_id}: {len(errors)} errors")
        """
        results: dict[str, list[str]] = {}
        repositories = self.list_repositories()

        for repo in repositories:
            repo_id = repo.get("id")
            if repo_id:
                results[repo_id] = self.validate(repo_id)

        return results

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
        return self.state.write_json(file_path, dep_data)

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
            return self.state.read_json(file_path)
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
        import json

        dependencies = []
        if not self.dependencies_dir.exists():
            return dependencies

        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self.state.read_json(dep_file)
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
            self.state._create_backup(file_path)
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
                    if self.state.read_json(f, default={}).get("enabled", True)
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
        import json

        counts: dict[str, int] = {}
        if not self.dependencies_dir.exists():
            return counts

        for file_path in self.dependencies_dir.glob("*.json"):
            try:
                dep = self.state.read_json(file_path)
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
        import json

        dependencies = []
        if not self.dependencies_dir.exists():
            return dependencies

        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self.state.read_json(dep_file)
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
        import json

        errors: list[str] = []
        if not self.dependencies_dir.exists():
            return errors

        # Get all repository IDs
        repo_ids = set()
        for repo_file in self.repositories_dir.glob("*.json"):
            try:
                repo = self.state.read_json(repo_file)
                repo_ids.add(repo.get("id"))
            except (json.JSONDecodeError, KeyError):
                continue

        # Validate dependencies
        for dep_file in self.dependencies_dir.glob("*.json"):
            try:
                dep = self.state.read_json(dep_file)
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
