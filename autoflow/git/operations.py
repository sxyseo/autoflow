"""
Git Operations - Branch detection, rebasing, and conflict detection

This module provides GitOperations class for git operations.
Implementation will be added in subtask-1-2.
"""


class GitError(Exception):
    """Base exception for git operation errors."""
    pass


class GitOperations:
    """
    Git operations for branch management, rebasing, and conflict detection.

    Implementation will be added in subtask-1-2 and subtask-1-3.
    """

    def __init__(self, repo_path: str):
        """
        Initialize GitOperations.

        Args:
            repo_path: Path to the git repository
        """
        self.repo_path = repo_path
