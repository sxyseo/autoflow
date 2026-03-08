"""
Autoflow Repository Module

Provides data models for managing multiple git repositories with proper
dependency tracking and branch configuration.

Usage:
    from autoflow.core.repository import Repository

    repo = Repository(
        id="frontend",
        name="Frontend Monorepo",
        path="~/dev/frontend",
        url="https://github.com/org/frontend.git",
        branch="main"
    )
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

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
