"""
Autoflow Git Operations Module

Provides git utilities for branch detection, rebasing, and conflict detection.
This module serves as the foundation for PR refresh functionality.

Usage:
    from autoflow.git.operations import GitOperations, GitError

    git_ops = GitOperations(repo_path="/path/to/repo")
    base_branch = git_ops.get_base_branch()
    current_branch = git_ops.get_current_branch()
    has_conflicts = git_ops.has_merge_conflicts()
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class GitError(Exception):
    """
    Exception raised for git operation errors.

    Attributes:
        message: Error message
        exit_code: Git exit code (if available)
        command: Command that failed
        repo_path: Repository path
    """

    def __init__(
        self,
        message: str,
        exit_code: Optional[int] = None,
        command: Optional[list[str]] = None,
        repo_path: Optional[Path] = None,
    ):
        self.message = message
        self.exit_code = exit_code
        self.command = command
        self.repo_path = repo_path
        super().__init__(message)


class BranchType(str, Enum):
    """Types of git branches."""

    MAIN = "main"
    MASTER = "master"
    DEVELOP = "develop"
    FEATURE = "feature"
    BUGFIX = "bugfix"
    HOTFIX = "hotfix"
    OTHER = "other"


@dataclass
class BranchInfo:
    """
    Information about a git branch.

    Attributes:
        name: Branch name
        branch_type: Type of branch (main, feature, etc.)
        is_current: Whether this is the current branch
        is_remote: Whether this is a remote branch
        commit_sha: Latest commit SHA
        commit_message: Latest commit message
    """

    name: str
    branch_type: BranchType = BranchType.OTHER
    is_current: bool = False
    is_remote: bool = False
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None

    def __repr__(self) -> str:
        """Return string representation."""
        current = "*" if self.is_current else " "
        remote = "remotes/" if self.is_remote else ""
        return f"{current} {remote}{self.name} ({self.branch_type.value})"


@dataclass
class RebaseResult:
    """
    Result of a rebase operation.

    Attributes:
        success: Whether rebase succeeded
        has_conflicts: Whether merge conflicts occurred
        current_commit: Current commit SHA after rebase
        conflicted_files: List of files with conflicts
        error: Error message if rebase failed
    """

    success: bool = False
    has_conflicts: bool = False
    current_commit: Optional[str] = None
    conflicted_files: list[str] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        """Initialize conflicted_files if not provided."""
        if self.conflicted_files is None:
            self.conflicted_files = []


class GitOperations:
    """
    Git operations utility class.

    Provides methods for branch detection, git status checks,
    and repository introspection. All operations are executed
    synchronously using subprocess.

    Key features:
    - Detect base branch (main/master)
    - Get current branch information
    - Check for merge conflicts
    - Execute git commands safely

    Example:
        >>> git_ops = GitOperations(repo_path="/path/to/repo")
        >>> base = git_ops.get_base_branch()
        >>> current = git_ops.get_current_branch()
        >>> if git_ops.has_merge_conflicts():
        ...     print("Merge conflicts detected!")
        >>> else:
        ...     print("Clean working directory")

    Attributes:
        repo_path: Path to git repository
        verbose: Whether to print debug output
    """

    DEFAULT_MAIN_BRANCHES = ["main", "master", "develop"]

    def __init__(self, repo_path: Optional[Path | str] = None, verbose: bool = False):
        """
        Initialize git operations.

        Args:
            repo_path: Path to git repository (defaults to current directory)
            verbose: Whether to print debug output

        Raises:
            GitError: If repo_path is not a valid git repository
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.verbose = verbose

        # Verify this is a git repository
        if not self._is_git_repo():
            raise GitError(
                f"Not a git repository: {self.repo_path}",
                repo_path=self.repo_path,
            )

    def _run_git(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """
        Run a git command in the repository.

        Args:
            args: Git command arguments (e.g., ["status", "--short"])
            check: Whether to raise on non-zero exit code
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess with command result

        Raises:
            GitError: If command fails and check=True
        """
        command = ["git"] + args

        if self.verbose:
            print(f"[git] {' '.join(command)}")

        try:
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                check=check,
                capture_output=capture_output,
                text=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise GitError(
                f"Git command failed: {e.stderr or str(e)}",
                exit_code=e.returncode,
                command=command,
                repo_path=self.repo_path,
            )
        except FileNotFoundError as e:
            raise GitError(
                f"Git not found: {e}",
                command=command,
                repo_path=self.repo_path,
            )

    def _is_git_repo(self) -> bool:
        """
        Check if the current path is a git repository.

        Returns:
            True if .git directory exists or this is inside a git repo
        """
        git_dir = self.repo_path / ".git"
        if git_dir.exists():
            return True

        # Check using git rev-parse
        try:
            result = self._run_git(["rev-parse", "--is-inside-work-tree"], check=False)
            return result.stdout.strip() == "true"
        except Exception:
            return False

    def get_base_branch(self) -> str:
        """
        Detect the base branch of the repository.

        Checks for common branch names (main, master, develop)
        and returns the first one that exists. Defaults to "main"
        if none found.

        Returns:
            Base branch name (e.g., "main", "master", "develop")

        Example:
            >>> git_ops = GitOperations()
            >>> base = git_ops.get_base_branch()
            >>> print(f"Base branch: {base}")
            Base branch: main
        """
        # Try common main branch names
        for branch in self.DEFAULT_MAIN_BRANCHES:
            result = self._run_git(
                ["rev-parse", "--verify", branch],
                check=False,
            )
            if result.returncode == 0:
                return branch

        # Fallback: return current branch or "main"
        try:
            current = self.get_current_branch()
            return current or "main"
        except GitError:
            return "main"

    def get_current_branch(self) -> str:
        """
        Get the name of the current branch.

        Returns:
            Current branch name

        Raises:
            GitError: If unable to determine current branch

        Example:
            >>> git_ops = GitOperations()
            >>> branch = git_ops.get_current_branch()
            >>> print(f"On branch: {branch}")
            On branch: feature/my-feature
        """
        result = self._run_git(["branch", "--show-current"])
        branch = result.stdout.strip()

        if not branch:
            raise GitError(
                "Unable to determine current branch (detached HEAD?)",
                repo_path=self.repo_path,
            )

        return branch

    def get_branch_info(self, branch_name: Optional[str] = None) -> BranchInfo:
        """
        Get detailed information about a branch.

        Args:
            branch_name: Branch name (defaults to current branch)

        Returns:
            BranchInfo with branch details

        Raises:
            GitError: If branch does not exist

        Example:
            >>> git_ops = GitOperations()
            >>> info = git_ops.get_branch_info("feature/my-feature")
            >>> print(f"{info.name} ({info.branch_type})")
            feature/my-feature (feature)
        """
        # Get current branch if not specified
        if branch_name is None:
            branch_name = self.get_current_branch()

        # Determine branch type
        branch_type = self._classify_branch(branch_name)

        # Check if current branch
        is_current = branch_name == self.get_current_branch()

        # Get latest commit info
        commit_sha = None
        commit_message = None
        try:
            result = self._run_git(
                ["log", "-1", "--format=%H|%s", branch_name],
                check=True,
            )
            output = result.stdout.strip()
            if "|" in output:
                commit_sha, commit_message = output.split("|", 1)
        except GitError:
            pass

        return BranchInfo(
            name=branch_name,
            branch_type=branch_type,
            is_current=is_current,
            is_remote=branch_name.startswith("remotes/"),
            commit_sha=commit_sha,
            commit_message=commit_message,
        )

    def _classify_branch(self, branch_name: str) -> BranchType:
        """
        Classify a branch by its name pattern.

        Args:
            branch_name: Branch name

        Returns:
            BranchType classification
        """
        # Remove remote prefix if present
        clean_name = branch_name.replace("remotes/origin/", "")

        # Check for standard branch types
        if clean_name in ["main", "master"]:
            return BranchType.MAIN
        elif clean_name == "develop":
            return BranchType.DEVELOP
        elif clean_name.startswith("feature/"):
            return BranchType.FEATURE
        elif clean_name.startswith("bugfix/"):
            return BranchType.BUGFIX
        elif clean_name.startswith("hotfix/"):
            return BranchType.HOTFIX
        else:
            return BranchType.OTHER

    def has_merge_conflicts(self) -> bool:
        """
        Check if there are unresolved merge conflicts.

        Returns:
            True if merge conflicts exist, False otherwise

        Example:
            >>> git_ops = GitOperations()
            >>> if git_ops.has_merge_conflicts():
            ...     print("Merge conflicts detected!")
        """
        try:
            result = self._run_git(["status", "--porcelain"])
            # Check for conflicted files (marked withUU)
            for line in result.stdout.strip().split("\n"):
                if line.startswith("UU") or line.startswith("AA"):
                    return True
            return False
        except GitError:
            return False

    def get_conflicted_files(self) -> list[str]:
        """
        Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts

        Example:
            >>> git_ops = GitOperations()
            >>> conflicts = git_ops.get_conflicted_files()
            >>> for file in conflicts:
            ...     print(f"Conflict in: {file}")
        """
        conflicted_files: list[str] = []

        try:
            result = self._run_git(["diff", "--name-only", "--diff-filter=U"])
            conflicted_files = [
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            ]
        except GitError:
            pass

        return conflicted_files

    def is_clean_working_dir(self) -> bool:
        """
        Check if the working directory is clean (no uncommitted changes).

        Returns:
            True if working directory is clean, False otherwise

        Example:
            >>> git_ops = GitOperations()
            >>> if git_ops.is_clean_working_dir():
            ...     print("Working directory is clean")
        """
        try:
            result = self._run_git(["status", "--porcelain"])
            return len(result.stdout.strip()) == 0
        except GitError:
            return False

    def get_repo_status(self) -> dict[str, Any]:
        """
        Get overall repository status.

        Returns:
            Dictionary with status information:
            - branch: Current branch name
            - clean: Whether working directory is clean
            - has_conflicts: Whether merge conflicts exist
            - staged: Number of staged files
            - unstaged: Number of unstaged files
            - untracked: Number of untracked files

        Example:
            >>> git_ops = GitOperations()
            >>> status = git_ops.get_repo_status()
            >>> print(f"Branch: {status['branch']}")
            >>> print(f"Clean: {status['clean']}")
        """
        status: dict[str, Any] = {
            "branch": "",
            "clean": False,
            "has_conflicts": False,
            "staged": 0,
            "unstaged": 0,
            "untracked": 0,
        }

        try:
            status["branch"] = self.get_current_branch()
        except GitError:
            status["branch"] = "HEAD"

        try:
            result = self._run_git(["status", "--porcelain"])

            staged = 0
            unstaged = 0
            untracked = 0

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                # Parse porcelain output
                status_char = line[0] if line else " "
                work_char = line[1] if len(line) > 1 else " "

                if status_char in "MADRC" or work_char in "MADRC":
                    if status_char != " " and status_char != "?":
                        staged += 1
                    if work_char != " " and work_char != "?":
                        unstaged += 1

                if status_char == "?" or work_char == "?":
                    untracked += 1

            status["staged"] = staged
            status["unstaged"] = unstaged
            status["untracked"] = untracked
            status["clean"] = (staged + unstaged + untracked) == 0
            status["has_conflicts"] = self.has_merge_conflicts()

        except GitError:
            pass

        return status

    def __repr__(self) -> str:
        """Return string representation."""
        try:
            branch = self.get_current_branch()
            return f"GitOperations(repo_path='{self.repo_path}', branch='{branch}')"
        except GitError:
            return f"GitOperations(repo_path='{self.repo_path}')"


def create_git_operations(repo_path: Optional[Path | str] = None) -> GitOperations:
    """
    Factory function to create a GitOperations instance.

    Args:
        repo_path: Path to git repository (defaults to current directory)

    Returns:
        Configured GitOperations instance

    Example:
        >>> git_ops = create_git_operations("/path/to/repo")
        >>> base = git_ops.get_base_branch()
    """
    return GitOperations(repo_path=repo_path)
