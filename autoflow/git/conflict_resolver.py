"""
Autoflow Conflict Resolver Module

Provides automatic merge conflict resolution with intelligent strategies.
Detects conflicts, attempts resolution, and extracts context for fix tasks.

Usage:
    from autoflow.git.conflict_resolver import ConflictResolver, ConflictResult, ConflictResolutionType

    resolver = ConflictResolver(repo_path="/path/to/repo")
    result = resolver.attempt_resolution(strategy=ConflictResolutionType.THEIRS_FULL)
    if result.success:
        print("Conflicts resolved!")
    else:
        print(f"Failed to resolve: {result.conflicted_files}")
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class ConflictError(Exception):
    """
    Exception raised for conflict resolution errors.

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


class ConflictResolutionType(str, Enum):
    """Types of conflict resolution strategies."""

    THEIRS_FULL = "theirs_full"
    """Accept all changes from the incoming branch."""

    OURS_FULL = "ours_full"
    """Accept all changes from the current branch."""

    MARKER_RESOLUTION = "marker_resolution"
    """Attempt to resolve conflict markers intelligently."""

    MANUAL = "manual"
    """Mark conflicts as requiring manual intervention."""


@dataclass
class ConflictMarker:
    """
    Represents a conflict marker in a file.

    Attributes:
        file_path: Path to the conflicted file
        start_line: Line number where conflict starts
        end_line: Line number where conflict ends
        ours_content: Content from the current branch
        theirs_content: Content from the incoming branch
        base_content: Optional base content (if available)
    """

    file_path: str
    start_line: int
    end_line: int
    ours_content: list[str] = field(default_factory=list)
    theirs_content: list[str] = field(default_factory=list)
    base_content: Optional[list[str]] = None

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ConflictMarker(file='{self.file_path}', "
            f"lines={self.start_line}-{self.end_line})"
        )


@dataclass
class ConflictResult:
    """
    Result of a conflict resolution attempt.

    Attributes:
        success: Whether resolution succeeded
        strategy_used: The resolution strategy that was attempted
        resolved_files: List of files that were successfully resolved
        conflicted_files: List of files still with conflicts
        markers: List of conflict markers found (if any)
        error: Error message if resolution failed
        resolution_summary: Summary of what was done
    """

    success: bool = False
    strategy_used: ConflictResolutionType = ConflictResolutionType.MANUAL
    resolved_files: list[str] = field(default_factory=list)
    conflicted_files: list[str] = field(default_factory=list)
    markers: list[ConflictMarker] = field(default_factory=list)
    error: Optional[str] = None
    resolution_summary: Optional[str] = None

    def __repr__(self) -> str:
        """Return string representation."""
        status = "✓" if self.success else "✗"
        return (
            f"{status} ConflictResult(strategy={self.strategy_used.value}, "
            f"resolved={len(self.resolved_files)}, "
            f"conflicts={len(self.conflicted_files)})"
        )


class ConflictResolver:
    """
    Automatic merge conflict resolution with intelligent strategies.

    This class provides methods to detect, analyze, and resolve merge conflicts
    that occur during git operations like rebasing or merging. It supports multiple
    resolution strategies and can extract conflict context for creating fix tasks.

    Key features:
    - Detect merge conflicts in working directory
    - Apply automatic resolution strategies (theirs, ours, marker-based)
    - Extract conflict context for fix task generation
    - Analyze conflict markers to understand what changed

    Example:
        >>> resolver = ConflictResolver(repo_path="/path/to/repo")
        >>>
        >>> # Detect conflicts
        >>> if resolver.has_conflicts():
        ...     # Attempt automatic resolution
        ...     result = resolver.attempt_resolution(
        ...         strategy=ConflictResolutionType.THEIRS_FULL
        ...     )
        ...     if result.success:
        ...         print("Resolved automatically!")
        ...     else:
        ...         # Extract context for manual resolution
        ...         context = resolver.extract_conflict_context()
        ...         print(f"Manual resolution needed: {context}")

    Attributes:
        repo_path: Path to git repository
        verbose: Whether to print debug output
    """

    # Conflict marker patterns
    CONFLICT_START = re.compile(r"^<<<<<<<")
    CONFLICT_SEPARATOR = re.compile(r"^=======\s*$")
    CONFLICT_END = re.compile(r"^>>>>>>>")

    def __init__(
        self,
        repo_path: Optional[Path | str] = None,
        verbose: bool = False
    ):
        """
        Initialize conflict resolver.

        Args:
            repo_path: Path to git repository (defaults to current directory)
            verbose: Whether to print debug output

        Raises:
            ConflictError: If repo_path is not a valid git repository
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.verbose = verbose

        # Verify this is a git repository
        if not self._is_git_repo():
            raise ConflictError(
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
            ConflictError: If command fails and check=True
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
            raise ConflictError(
                f"Git command failed: {e.stderr or str(e)}",
                exit_code=e.returncode,
                command=command,
                repo_path=self.repo_path,
            )
        except FileNotFoundError as e:
            raise ConflictError(
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
            result = self._run_git(
                ["rev-parse", "--is-inside-work-tree"],
                check=False
            )
            return result.stdout.strip() == "true"
        except Exception:
            return False

    def has_conflicts(self) -> bool:
        """
        Check if there are unresolved merge conflicts.

        Returns:
            True if merge conflicts exist, False otherwise

        Example:
            >>> resolver = ConflictResolver()
            >>> if resolver.has_conflicts():
            ...     print("Conflicts detected!")
        """
        try:
            result = self._run_git(["status", "--porcelain"])
            # Check for conflicted files (marked with UU or AA)
            for line in result.stdout.strip().split("\n"):
                if line.startswith("UU") or line.startswith("AA"):
                    return True
            return False
        except ConflictError:
            return False

    def get_conflicted_files(self) -> list[str]:
        """
        Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts

        Example:
            >>> resolver = ConflictResolver()
            >>> conflicts = resolver.get_conflicted_files()
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
        except ConflictError:
            pass

        return conflicted_files

    def get_conflict_markers(self, file_path: str) -> list[ConflictMarker]:
        """
        Extract conflict markers from a file.

        Args:
            file_path: Path to the conflicted file

        Returns:
            List of ConflictMarker objects

        Example:
            >>> resolver = ConflictResolver()
            >>> markers = resolver.get_conflict_markers("src/file.py")
            >>> for marker in markers:
            ...     print(f"Conflict at lines {marker.start_line}-{marker.end_line}")
        """
        full_path = self.repo_path / file_path

        if not full_path.exists():
            return []

        markers: list[ConflictMarker] = []
        current_marker: Optional[ConflictMarker] = None
        current_section = None  # 'ours' or 'theirs'

        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                for line_num, line in enumerate(f, start=1):
                    # Check for conflict start
                    if self.CONFLICT_START.match(line):
                        current_marker = ConflictMarker(
                            file_path=file_path,
                            start_line=line_num,
                            end_line=line_num,
                        )
                        current_section = 'ours'
                        continue

                    # Check for conflict separator
                    if current_marker and self.CONFLICT_SEPARATOR.match(line):
                        current_section = 'theirs'
                        continue

                    # Check for conflict end
                    if current_marker and self.CONFLICT_END.match(line):
                        current_marker.end_line = line_num
                        markers.append(current_marker)
                        current_marker = None
                        current_section = None
                        continue

                    # Collect content for current section
                    if current_marker and current_section:
                        if current_section == 'ours':
                            current_marker.ours_content.append(line)
                        elif current_section == 'theirs':
                            current_marker.theirs_content.append(line)

        except (IOError, UnicodeDecodeError):
            pass

        return markers

    def attempt_resolution(
        self,
        strategy: ConflictResolutionType = ConflictResolutionType.THEIRS_FULL,
    ) -> ConflictResult:
        """
        Attempt to resolve merge conflicts using the specified strategy.

        This method applies the chosen resolution strategy to all conflicted
        files in the repository. It updates the git index to mark conflicts as
        resolved.

        Args:
            strategy: Resolution strategy to apply

        Returns:
            ConflictResult with resolution outcome

        Example:
            >>> resolver = ConflictResolver()
            >>> result = resolver.attempt_resolution(
            ...     strategy=ConflictResolutionType.THEIRS_FULL
            ... )
            >>> if result.success:
            ...     print("All conflicts resolved!")
        """
        result = ConflictResult(strategy_used=strategy)
        conflicted_files = self.get_conflicted_files()

        if not conflicted_files:
            result.success = True
            result.resolution_summary = "No conflicts to resolve"
            return result

        if self.verbose:
            print(f"[resolver] Attempting {strategy.value} for {len(conflicted_files)} files")

        try:
            if strategy == ConflictResolutionType.THEIRS_FULL:
                resolved = self._resolve_theirs_full(conflicted_files)
            elif strategy == ConflictResolutionType.OURS_FULL:
                resolved = self._resolve_ours_full(conflicted_files)
            elif strategy == ConflictResolutionType.MARKER_RESOLUTION:
                resolved = self._resolve_markers(conflicted_files)
            else:
                # MANUAL - just return current state
                resolved = []

            result.resolved_files = resolved
            result.conflicted_files = [
                f for f in conflicted_files
                if f not in resolved
            ]

            # Check if all conflicts were resolved
            result.success = len(result.conflicted_files) == 0

            if result.success:
                result.resolution_summary = (
                    f"Resolved all {len(conflicted_files)} files using {strategy.value}"
                )
            else:
                result.resolution_summary = (
                    f"Resolved {len(resolved)}/{len(conflicted_files)} files. "
                    f"{len(result.conflicted_files)} remain conflicted."
                )

        except ConflictError as e:
            result.error = str(e)
            result.success = False
            result.resolution_summary = f"Resolution failed: {e}"

        return result

    def _resolve_theirs_full(self, files: list[str]) -> list[str]:
        """
        Resolve conflicts by accepting incoming changes for all files.

        Args:
            files: List of conflicted file paths

        Returns:
            List of files that were resolved
        """
        resolved: list[str] = []

        for file_path in files:
            try:
                # Use git checkout --theirs to accept incoming changes
                self._run_git(["checkout", "--theirs", file_path])
                # Stage the resolved file
                self._run_git(["add", file_path])
                resolved.append(file_path)

                if self.verbose:
                    print(f"[resolver] Accepted theirs for: {file_path}")

            except ConflictError:
                if self.verbose:
                    print(f"[resolver] Failed to resolve: {file_path}")

        return resolved

    def _resolve_ours_full(self, files: list[str]) -> list[str]:
        """
        Resolve conflicts by keeping current changes for all files.

        Args:
            files: List of conflicted file paths

        Returns:
            List of files that were resolved
        """
        resolved: list[str] = []

        for file_path in files:
            try:
                # Use git checkout --ours to keep current changes
                self._run_git(["checkout", "--ours", file_path])
                # Stage the resolved file
                self._run_git(["add", file_path])
                resolved.append(file_path)

                if self.verbose:
                    print(f"[resolver] Kept ours for: {file_path}")

            except ConflictError:
                if self.verbose:
                    print(f"[resolver] Failed to resolve: {file_path}")

        return resolved

    def _resolve_markers(self, files: list[str]) -> list[str]:
        """
        Attempt intelligent resolution by analyzing conflict markers.

        This strategy tries to make smart decisions about conflicts:
        - If both sides added the same content, keep one
        - If one side is only whitespace, keep the other
        - Otherwise, mark as needing manual resolution

        Args:
            files: List of conflicted file paths

        Returns:
            List of files that were resolved
        """
        resolved: list[str] = []

        for file_path in files:
            try:
                markers = self.get_conflict_markers(file_path)

                if not markers:
                    # No markers found - might already be resolved
                    self._run_git(["add", file_path])
                    resolved.append(file_path)
                    continue

                # Try intelligent resolution for each marker
                file_resolved = True
                full_path = self.repo_path / file_path

                for marker in markers:
                    if not self._try_resolve_marker(full_path, marker):
                        file_resolved = False
                        break

                if file_resolved:
                    # Stage the resolved file
                    self._run_git(["add", file_path])
                    resolved.append(file_path)

                    if self.verbose:
                        print(f"[resolver] Marker resolution successful: {file_path}")
                else:
                    if self.verbose:
                        print(f"[resolver] Marker resolution failed: {file_path}")

            except ConflictError:
                if self.verbose:
                    print(f"[resolver] Failed to resolve markers: {file_path}")

        return resolved

    def _try_resolve_marker(
        self,
        file_path: Path,
        marker: ConflictMarker
    ) -> bool:
        """
        Attempt to resolve a single conflict marker.

        Args:
            file_path: Full path to the file
            marker: ConflictMarker to resolve

        Returns:
            True if marker was resolved, False otherwise
        """
        # Strategy: if both sides are identical, accept one
        if marker.ours_content == marker.theirs_content:
            return True  # Already resolved by keeping content

        # Strategy: if one side is only whitespace, accept the other
        ours_stripped = [line.strip() for line in marker.ours_content if line.strip()]
        theirs_stripped = [line.strip() for line in marker.theirs_content if line.strip()]

        if not ours_stripped and theirs_stripped:
            return True  # Accept theirs (ours is empty)
        if ours_stripped and not theirs_stripped:
            return True  # Accept ours (theirs is empty)

        # Cannot resolve automatically
        return False

    def extract_conflict_context(self) -> dict[str, Any]:
        """
        Extract detailed context about current conflicts for fix task generation.

        This method gathers information about all conflicted files, including
        conflict markers, file paths, and content differences. The returned
        dictionary can be used to generate fix tasks or provide context to
        developers.

        Returns:
            Dictionary with conflict context:
            - conflicted_files: List of file paths with conflicts
            - total_conflicts: Total number of conflict markers
            - file_details: Dict mapping file paths to their conflict markers
            - repository_path: Path to the repository
            - suggested_approach: Recommended resolution approach

        Example:
            >>> resolver = ConflictResolver()
            >>> context = resolver.extract_conflict_context()
            >>> print(f"Found {context['total_conflicts']} conflicts")
            >>> for file, markers in context['file_details'].items():
            ...     print(f"{file}: {len(markers)} conflict(s)")
        """
        conflicted_files = self.get_conflicted_files()
        file_details: dict[str, list[dict]] = {}
        total_conflicts = 0

        for file_path in conflicted_files:
            markers = self.get_conflict_markers(file_path)

            # Convert markers to dict for JSON serialization
            marker_dicts = []
            for marker in markers:
                marker_dicts.append({
                    "file_path": marker.file_path,
                    "start_line": marker.start_line,
                    "end_line": marker.end_line,
                    "ours_preview": self._preview_content(marker.ours_content),
                    "theirs_preview": self._preview_content(marker.theirs_content),
                })

            file_details[file_path] = marker_dicts
            total_conflicts += len(markers)

        # Determine suggested approach
        if total_conflicts == 0:
            suggested_approach = "no_conflicts"
        elif len(conflicted_files) == 1:
            suggested_approach = "single_file"
        elif total_conflicts > 10:
            suggested_approach = "complex_manual"
        else:
            suggested_approach = "standard_manual"

        return {
            "conflicted_files": conflicted_files,
            "total_conflicts": total_conflicts,
            "file_details": file_details,
            "repository_path": str(self.repo_path),
            "suggested_approach": suggested_approach,
        }

    def _preview_content(self, content: list[str], max_lines: int = 3) -> list[str]:
        """
        Create a preview of content (first few lines).

        Args:
            content: List of content lines
            max_lines: Maximum lines to include in preview

        Returns:
            Preview of content
        """
        return content[:max_lines]

    def __repr__(self) -> str:
        """Return string representation."""
        has_conflicts = self.has_conflicts()
        return (
            f"ConflictResolver(repo_path='{self.repo_path}', "
            f"has_conflicts={has_conflicts})"
        )


def create_conflict_resolver(
    repo_path: Optional[Path | str] = None,
    verbose: bool = False
) -> ConflictResolver:
    """
    Factory function to create a ConflictResolver instance.

    Args:
        repo_path: Path to git repository (defaults to current directory)
        verbose: Whether to print debug output

    Returns:
        Configured ConflictResolver instance

    Example:
        >>> resolver = create_conflict_resolver("/path/to/repo")
        >>> result = resolver.attempt_resolution()
    """
    return ConflictResolver(repo_path=repo_path, verbose=verbose)
