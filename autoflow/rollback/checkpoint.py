"""Checkpoint management module for git state snapshots.

This module provides checkpoint functionality that creates snapshots of git state
before significant changes, enabling automatic rollback to last known good states.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class CheckpointMetadata:
    """Metadata for a git checkpoint.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint.
        timestamp: ISO format timestamp when checkpoint was created.
        commit_hash: Git commit hash at checkpoint time.
        branch_name: Git branch name at checkpoint time.
        health_status: Health check status at checkpoint time.
        triggering_agent: Agent or process that created the checkpoint.
        description: Optional description of the checkpoint.
    """

    checkpoint_id: str
    timestamp: str
    commit_hash: str
    branch_name: str
    health_status: str
    triggering_agent: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary.

        Returns:
            Dictionary representation of metadata.
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointMetadata:
        """Create metadata from dictionary.

        Args:
            data: Dictionary containing checkpoint metadata.

        Returns:
            CheckpointMetadata instance.
        """
        return cls(**data)


class CheckpointManager:
    """Manage git state checkpoints for automatic rollback.

    The CheckpointManager creates snapshots of git state before significant
    changes, stores metadata for tracking, and enables recovery to known good
    states when health checks fail.

    Checkpoints are stored as JSON metadata files in .autoflow/checkpoints/,
    with references to git commits that can be restored during rollback.

    Example:
        manager = CheckpointManager(root=Path("/path/to/project"))

        # Create a checkpoint before making changes
        checkpoint = manager.create_checkpoint(
            triggering_agent="continuous_iteration",
            description="Before agent dispatch"
        )

        # List available checkpoints
        checkpoints = manager.list_checkpoints()

        # Get metadata for a specific checkpoint
        metadata = manager.get_checkpoint(checkpoint_id)
    """

    def __init__(self, root: Path | None = None) -> None:
        """Initialize checkpoint manager with project root directory.

        Args:
            root: Project root directory. Defaults to current working directory.
        """
        self.root = root or Path.cwd()
        self.checkpoints_dir = self.root / ".autoflow" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def _run_git_command(
        self,
        args: list[str],
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command and return the result.

        Args:
            args: Git command arguments (e.g., ['rev-parse', 'HEAD']).
            cwd: Working directory for command. Defaults to root.

        Returns:
            CompletedProcess with command output.

        Raises:
            subprocess.CalledProcessError: If git command fails.
        """
        working_dir = cwd or self.root
        return subprocess.run(
            ["git"] + args,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=True,
        )

    def _get_current_commit(self) -> str:
        """Get the current git commit hash.

        Returns:
            Current commit hash as a string.

        Raises:
            subprocess.CalledProcessError: If not in a git repository or git fails.
        """
        result = self._run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def _get_current_branch(self) -> str:
        """Get the current git branch name.

        Returns:
            Current branch name.

        Raises:
            subprocess.CalledProcessError: If git command fails.
        """
        try:
            result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
            branch = result.stdout.strip()
            # Handle detached HEAD state
            if branch == "HEAD":
                return "detached"
            return branch
        except subprocess.CalledProcessError:
            return "unknown"

    def _generate_checkpoint_id(self) -> str:
        """Generate a unique checkpoint ID.

        Returns:
            Checkpoint ID in format 'checkpoint-YYYYMMDD-HHMMSS-<short-hash>'.
        """
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        try:
            commit_hash = self._get_current_commit()[:8]
        except subprocess.CalledProcessError:
            commit_hash = "unknown"
        return f"checkpoint-{timestamp}-{commit_hash}"

    def create_checkpoint(
        self,
        triggering_agent: str,
        health_status: str = "unknown",
        description: str = "",
    ) -> CheckpointMetadata:
        """Create a checkpoint of the current git state.

        Args:
            triggering_agent: Agent or process creating the checkpoint.
            health_status: Health check status at checkpoint time.
            description: Optional description of the checkpoint.

        Returns:
            CheckpointMetadata object with checkpoint information.

        Raises:
            subprocess.CalledProcessError: If git commands fail.
            OSError: If unable to write checkpoint file.
        """
        # Get current git state
        commit_hash = self._get_current_commit()
        branch_name = self._get_current_branch()

        # Generate checkpoint ID and timestamp
        checkpoint_id = self._generate_checkpoint_id()
        timestamp = datetime.now().isoformat()

        # Create metadata
        metadata = CheckpointMetadata(
            checkpoint_id=checkpoint_id,
            timestamp=timestamp,
            commit_hash=commit_hash,
            branch_name=branch_name,
            health_status=health_status,
            triggering_agent=triggering_agent,
            description=description,
        )

        # Write checkpoint metadata to file
        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        try:
            with checkpoint_file.open("w") as f:
                json.dump(metadata.to_dict(), f, indent=2)
        except OSError as e:
            raise OSError(f"Failed to write checkpoint file: {e}") from e

        return metadata

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointMetadata | None:
        """Retrieve metadata for a specific checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to retrieve.

        Returns:
            CheckpointMetadata if found, None otherwise.
        """
        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        if not checkpoint_file.exists():
            return None

        try:
            with checkpoint_file.open("r") as f:
                data = json.load(f)
            return CheckpointMetadata.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def list_checkpoints(
        self,
        limit: int | None = None,
    ) -> list[CheckpointMetadata]:
        """List all available checkpoints.

        Args:
            limit: Maximum number of checkpoints to return (most recent first).

        Returns:
            List of CheckpointMetadata objects, sorted by timestamp (newest first).
        """
        checkpoints = []

        for checkpoint_file in self.checkpoints_dir.glob("checkpoint-*.json"):
            metadata = self.get_checkpoint(
                checkpoint_file.stem
            )
            if metadata:
                checkpoints.append(metadata)

        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda m: m.timestamp, reverse=True)

        if limit is not None:
            checkpoints = checkpoints[:limit]

        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint metadata file.

        Args:
            checkpoint_id: Checkpoint ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
        if not checkpoint_file.exists():
            return False

        try:
            checkpoint_file.unlink()
            return True
        except OSError:
            return False

    def get_latest_checkpoint(
        self,
        health_status: str | None = None,
    ) -> CheckpointMetadata | None:
        """Get the most recent checkpoint.

        Args:
            health_status: Optional filter for specific health status.

        Returns:
            Most recent CheckpointMetadata, or None if no checkpoints exist.
        """
        checkpoints = self.list_checkpoints()

        if health_status:
            checkpoints = [
                c for c in checkpoints if c.health_status == health_status
            ]

        return checkpoints[0] if checkpoints else None

    def restore_checkpoint(
        self,
        checkpoint_id: str,
    ) -> bool:
        """Restore the project state to a checkpoint using git reset.

        Args:
            checkpoint_id: Checkpoint ID to restore.

        Returns:
            True if restoration successful, False otherwise.

        Note:
            This performs a hard reset to the checkpoint's commit, which will
            discard all uncommitted changes. Use with caution.
        """
        metadata = self.get_checkpoint(checkpoint_id)
        if not metadata:
            return False

        try:
            # Hard reset to the checkpoint's commit
            self._run_git_command(["reset", "--hard", metadata.commit_hash])
            return True
        except subprocess.CalledProcessError:
            return False
