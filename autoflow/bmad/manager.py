"""BMAD Manager module for orchestrating checkpoints and handoffs.

This module provides the BMADManager class that manages checkpoints,
coordinates role transitions, and tracks handoff history. It serves as
the main interface for the BMAD framework.

Example:
    from autoflow.bmad.manager import BMADManager

    manager = BMADManager(root=Path("/path/to/project"))

    # Register a checkpoint
    checkpoint = manager.register_checkpoint(
        from_role="writer",
        to_role="reviewer",
        artifacts=[...]
    )

    # Get a checkpoint
    checkpoint = manager.get_checkpoint("writer", "reviewer")
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class BMADManager:
    """Manage BMAD checkpoints and orchestrate role transitions.

    The BMADManager serves as the central coordinator for the BMAD framework,
    managing checkpoints, validating handoffs, and maintaining handoff history.

    Key responsibilities:
    - Checkpoint registry: Store and retrieve checkpoints for role transitions
    - Handoff validation: Ensure artifacts are present before role transitions
    - History tracking: Maintain audit trail of all handoffs

    Checkpoints are stored as JSON files in .autoflow/bmad/checkpoints/,
    organized by role transition (e.g., "writer-to-reviewer.json").

    Example:
        manager = BMADManager(root=Path("/path/to/project"))

        # Register a checkpoint for a role transition
        checkpoint = manager.register_checkpoint(
            from_role="writer",
            to_role="reviewer",
            description="Writer must complete code and tests"
        )

        # Add artifacts to the checkpoint
        from autoflow.bmad.artifacts import ArtifactSpec, ArtifactType

        checkpoint.add_artifact(
            ArtifactSpec(
                name="code",
                type=ArtifactType.FILE,
                path="src/module.py",
                required=True
            )
        )

        # Retrieve checkpoint for validation
        checkpoint = manager.get_checkpoint("writer", "reviewer")
        errors = checkpoint.validate(root=manager.root)
    """

    def __init__(self, root: Optional[Path | str] = None) -> None:
        """Initialize BMAD manager with project root directory.

        Args:
            root: Project root directory. Defaults to current working directory.
        """
        # Convert root to Path if needed
        if isinstance(root, str):
            self.root = Path(root)
        elif root is None:
            self.root = Path.cwd()
        else:
            self.root = root

        # Set up checkpoints directory
        self.checkpoints_dir = self.root / ".autoflow" / "bmad" / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

        # Set up handoffs directory
        self.handoffs_dir = self.root / ".autoflow" / "bmad" / "handoffs"
        self.handoffs_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, from_role: str, to_role: str) -> Path:
        """Get the file path for a checkpoint.

        Args:
            from_role: Source role for the transition.
            to_role: Destination role for the transition.

        Returns:
            Path to the checkpoint file.
        """
        filename = f"{from_role}-to-{to_role}.json"
        return self.checkpoints_dir / filename

    def register_checkpoint(
        self,
        from_role: str,
        to_role: str,
        artifacts: Optional[list] = None,
        description: str = "",
        required: bool = True,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Register a checkpoint for a role transition.

        Creates a new checkpoint defining the artifacts required for
        a transition from one role to another.

        Args:
            from_role: Source role for the transition (e.g., 'writer').
            to_role: Destination role for the transition (e.g., 'reviewer').
            artifacts: List of ArtifactSpec objects required for this transition.
            description: Optional description of this checkpoint.
            required: Whether this checkpoint must pass for handoff to proceed.
            metadata: Additional checkpoint metadata.

        Returns:
            BMADCheckpoint object.

        Raises:
            OSError: If unable to write checkpoint file.
        """
        from autoflow.bmad.checkpoint import BMADCheckpoint

        # Create checkpoint
        checkpoint = BMADCheckpoint(
            from_role=from_role,
            to_role=to_role,
            artifacts=artifacts or [],
            description=description,
            required=required,
            metadata=metadata or {},
        )

        # Save checkpoint to file
        self._save_checkpoint(checkpoint)

        return checkpoint

    def _save_checkpoint(self, checkpoint: Any) -> None:
        """Save checkpoint to file.

        Args:
            checkpoint: BMADCheckpoint object to save.

        Raises:
            OSError: If unable to write checkpoint file.
        """
        checkpoint_path = self._get_checkpoint_path(
            checkpoint.from_role, checkpoint.to_role
        )

        try:
            with checkpoint_path.open("w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
        except OSError as e:
            raise OSError(f"Failed to write checkpoint file: {e}") from e

    def get_checkpoint(self, from_role: str, to_role: str) -> Any | None:
        """Retrieve a checkpoint for a role transition.

        Args:
            from_role: Source role for the transition.
            to_role: Destination role for the transition.

        Returns:
            BMADCheckpoint if found, None otherwise.
        """
        from autoflow.bmad.checkpoint import BMADCheckpoint

        checkpoint_path = self._get_checkpoint_path(from_role, to_role)

        if not checkpoint_path.exists():
            return None

        try:
            with checkpoint_path.open("r") as f:
                data = json.load(f)
            return BMADCheckpoint.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def list_checkpoints(self) -> list[Any]:
        """List all registered checkpoints.

        Returns:
            List of BMADCheckpoint objects, sorted by from_role and to_role.
        """
        from autoflow.bmad.checkpoint import BMADCheckpoint

        checkpoints = []

        for checkpoint_file in self.checkpoints_dir.glob("*.json"):
            try:
                with checkpoint_file.open("r") as f:
                    data = json.load(f)
                checkpoint = BMADCheckpoint.from_dict(data)
                checkpoints.append(checkpoint)
            except (OSError, json.JSONDecodeError):
                # Skip invalid checkpoint files
                continue

        # Sort by from_role, then to_role
        checkpoints.sort(key=lambda c: (c.from_role, c.to_role))

        return checkpoints

    def delete_checkpoint(self, from_role: str, to_role: str) -> bool:
        """Delete a checkpoint.

        Args:
            from_role: Source role for the transition.
            to_role: Destination role for the transition.

        Returns:
            True if deleted, False if not found.
        """
        checkpoint_path = self._get_checkpoint_path(from_role, to_role)

        if not checkpoint_path.exists():
            return False

        try:
            checkpoint_path.unlink()
            return True
        except OSError:
            return False

    def checkpoint_exists(self, from_role: str, to_role: str) -> bool:
        """Check if a checkpoint exists for a role transition.

        Args:
            from_role: Source role for the transition.
            to_role: Destination role for the transition.

        Returns:
            True if checkpoint exists, False otherwise.
        """
        checkpoint_path = self._get_checkpoint_path(from_role, to_role)
        return checkpoint_path.exists()

    def get_checkpoints_for_role(self, role: str) -> dict[str, Any]:
        """Get all checkpoints involving a specific role.

        Returns checkpoints where the role is either the source or destination.

        Args:
            role: Role to filter by.

        Returns:
            Dictionary mapping transition keys to checkpoints.
            Keys are in format "from_role-to-role".
        """
        checkpoints = {}

        for checkpoint in self.list_checkpoints():
            if checkpoint.from_role == role or checkpoint.to_role == role:
                key = f"{checkpoint.from_role}-to-{checkpoint.to_role}"
                checkpoints[key] = checkpoint

        return checkpoints

    def validate_checkpoint(
        self, from_role: str, to_role: str, root: Optional[Path | str] = None
    ) -> list[str]:
        """Validate a checkpoint's artifacts.

        Args:
            from_role: Source role for the transition.
            to_role: Destination role for the transition.
            root: Root directory for path resolution. Defaults to manager's root.

        Returns:
            List of validation errors (empty if valid).
        """
        checkpoint = self.get_checkpoint(from_role, to_role)

        if not checkpoint:
            return [f"Checkpoint not found: {from_role} → {to_role}"]

        # Use manager's root if not specified
        validation_root = root if root is not None else self.root

        return checkpoint.validate(validation_root)

    def _get_handoff_path(self, handoff_id: str) -> Path:
        """Get the file path for a handoff.

        Args:
            handoff_id: Unique handoff identifier.

        Returns:
            Path to the handoff file.
        """
        filename = f"{handoff_id}.json"
        return self.handoffs_dir / filename

    def _save_handoff(self, handoff: Any) -> None:
        """Save handoff to file.

        Args:
            handoff: Handoff object to save.

        Raises:
            OSError: If unable to write handoff file.
        """
        handoff_path = self._get_handoff_path(handoff.handoff_id)

        try:
            with handoff_path.open("w") as f:
                json.dump(handoff.to_dict(), f, indent=2)
        except OSError as e:
            raise OSError(f"Failed to write handoff file: {e}") from e

    def create_handoff(
        self,
        from_role: str,
        to_role: str,
        task_description: str = "",
        artifacts: Optional[list] = None,
        metadata: Optional[dict[str, Any]] = None,
        validate: bool = True,
    ) -> Any:
        """Create and optionally validate a handoff.

        Creates a new handoff for a role transition, optionally validating
        that required artifacts are present.

        Args:
            from_role: Source role for the transition (e.g., 'writer').
            to_role: Destination role for the transition (e.g., 'reviewer').
            task_description: Description of the task being handed off.
            artifacts: List of ArtifactSpec objects to include in handoff.
            metadata: Additional handoff metadata.
            validate: Whether to validate artifacts against checkpoint.

        Returns:
            Handoff object.

        Raises:
            ValueError: If validation fails and validate=True.
            OSError: If unable to write handoff file.
        """
        from autoflow.bmad.handoff import Handoff

        # Get checkpoint for this transition if it exists
        checkpoint = self.get_checkpoint(from_role, to_role)

        # Create handoff
        handoff = Handoff(
            role=from_role,
            next_role=to_role,
            checkpoint=checkpoint,
            metadata=metadata or {},
        )

        # Set task description if provided
        if task_description:
            handoff.set_task_description(task_description)

        # Add artifacts if provided
        if artifacts:
            for artifact in artifacts:
                handoff.context.artifacts.add_artifact(artifact)

        # Validate if requested
        if validate:
            errors = handoff.validate_artifacts(self.root)
            if errors and (checkpoint and checkpoint.required):
                raise ValueError(
                    f"Handoff validation failed for {from_role} → {to_role}: "
                    f"{', '.join(errors)}"
                )

        # Save handoff to file
        self._save_handoff(handoff)

        return handoff

    def get_handoff(self, handoff_id: str) -> Any | None:
        """Retrieve a handoff by ID.

        Args:
            handoff_id: Unique handoff identifier.

        Returns:
            Handoff if found, None otherwise.
        """
        from autoflow.bmad.handoff import Handoff

        handoff_path = self._get_handoff_path(handoff_id)

        if not handoff_path.exists():
            return None

        try:
            with handoff_path.open("r") as f:
                data = json.load(f)
            return Handoff.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return None

    def list_handoffs(
        self,
        from_role: Optional[str] = None,
        to_role: Optional[str] = None,
    ) -> list[Any]:
        """List handoffs, optionally filtered by roles.

        Args:
            from_role: Optional source role filter.
            to_role: Optional destination role filter.

        Returns:
            List of Handoff objects, sorted by created_at (newest first).
        """
        from autoflow.bmad.handoff import Handoff

        handoffs = []

        for handoff_file in self.handoffs_dir.glob("*.json"):
            try:
                with handoff_file.open("r") as f:
                    data = json.load(f)
                handoff = Handoff.from_dict(data)

                # Apply filters if specified
                if from_role and handoff.role != from_role:
                    continue
                if to_role and handoff.next_role != to_role:
                    continue

                handoffs.append(handoff)
            except (OSError, json.JSONDecodeError):
                # Skip invalid handoff files
                continue

        # Sort by created_at (newest first)
        handoffs.sort(key=lambda h: h.created_at or datetime.min, reverse=True)

        return handoffs

    def __repr__(self) -> str:
        """Return string representation of the manager."""
        checkpoint_count = len(self.list_checkpoints())
        handoff_count = len(self.list_handoffs())
        return f"BMADManager(root='{self.root}', checkpoints={checkpoint_count}, handoffs={handoff_count})"
