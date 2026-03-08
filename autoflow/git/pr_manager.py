"""
PR Manager - PR state tracking and refresh management

This module provides PRManager class for PR state tracking.
Implementation will be added in subtask-2-1.
"""

from enum import Enum


class PRState:
    """
    PR state data model.

    Implementation will be added in subtask-2-1.
    """

    def __init__(self, pr_number: int, branch: str, base_branch: str):
        self.pr_number = pr_number
        self.branch = branch
        self.base_branch = base_branch


class PRManager:
    """
    Manages PR state tracking and refresh operations.

    Implementation will be added in subtask-2-1, subtask-2-2, and subtask-2-3.
    """

    def __init__(self, repo_path: str):
        """
        Initialize PRManager.

        Args:
            repo_path: Path to the git repository
        """
        self.repo_path = repo_path
