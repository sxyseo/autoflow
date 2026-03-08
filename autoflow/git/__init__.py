"""
Autoflow Git - Git Operations, PR Management, and Conflict Resolution

This module provides git utilities for PR refresh functionality:
- GitOperations: Branch detection, rebasing, and conflict detection
- PRManager: PR state tracking and refresh management
- ConflictResolver: Automatic merge conflict resolution

Enables automatic PR rebasing and intelligent conflict resolution for
continuous development workflows.

Usage:
    from autoflow.git import GitOperations, PRManager, ConflictResolver

    git_ops = GitOperations(repo_path="/path/to/repo")
    pr_manager = PRManager(repo_path="/path/to/repo")
    resolver = ConflictResolver(repo_path="/path/to/repo")
"""

from autoflow.git.operations import (
    BranchInfo,
    BranchType,
    GitError,
    GitOperations,
    RebaseResult,
    create_git_operations,
)
from autoflow.git.pr_manager import (
    PRManager,
    PRState,
)
from autoflow.git.conflict_resolver import (
    ConflictResolver,
    ConflictResult,
)

__all__ = [
    # Git Operations
    "GitOperations",
    "GitError",
    "BranchInfo",
    "BranchType",
    "RebaseResult",
    "create_git_operations",
    # PR Manager
    "PRManager",
    "PRState",
    # Conflict Resolver
    "ConflictResolver",
    "ConflictResult",
]
