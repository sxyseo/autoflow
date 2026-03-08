"""
Autoflow Repository Module

Provides data models for managing multiple git repositories with proper
dependency tracking and branch configuration.

Usage:
    from autoflow.core.repository import Repository, RepositoryDependency

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
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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
