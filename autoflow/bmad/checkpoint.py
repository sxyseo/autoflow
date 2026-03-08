"""BMAD checkpoint module for role transition requirements.

This module provides checkpoint functionality that defines required artifacts
for role transitions in the BMAD (Breakdown, Make, and Debug) framework.
Checkpoints ensure that agents have completed their work before handoff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from autoflow.bmad.artifacts import ArtifactSpec


@dataclass
class BMADCheckpoint:
    """Checkpoint defining requirements for a role transition.

    A BMADCheckpoint specifies the artifacts that must be present
    before a handoff from one role to another can be completed.
    This enables validation that agents have completed their work
    before transitioning to the next role.

    Attributes:
        from_role: Source role for the transition (e.g., 'writer', 'reviewer').
        to_role: Destination role for the transition (e.g., 'reviewer', 'integrator').
        artifacts: List of artifact specifications required for this transition.
        description: Optional description of this checkpoint and its purpose.
        required: Whether this checkpoint must pass for handoff to proceed.
        metadata: Additional checkpoint metadata for tracking and debugging.
    """

    from_role: str
    to_role: str
    artifacts: list[ArtifactSpec] = field(default_factory=list)
    description: str = ""
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_artifact(self, artifact: ArtifactSpec) -> None:
        """Add an artifact requirement to this checkpoint.

        Args:
            artifact: Artifact specification to add.
        """
        self.artifacts.append(artifact)

    def remove_artifact(self, artifact_name: str) -> bool:
        """Remove an artifact requirement from this checkpoint.

        Args:
            artifact_name: Name of the artifact to remove.

        Returns:
            True if artifact was removed, False if not found.
        """
        for i, artifact in enumerate(self.artifacts):
            if artifact.name == artifact_name:
                self.artifacts.pop(i)
                return True
        return False

    def get_required_artifacts(self) -> list[ArtifactSpec]:
        """Get list of required artifacts for this checkpoint.

        Returns:
            List of required artifact specifications.
        """
        return [a for a in self.artifacts if a.required]

    def get_optional_artifacts(self) -> list[ArtifactSpec]:
        """Get list of optional artifacts for this checkpoint.

        Returns:
            List of optional artifact specifications.
        """
        return [a for a in self.artifacts if not a.required]

    def validate(self, root: Optional[Path] = None) -> list[str]:
        """Validate that all required artifacts are present.

        Args:
            root: Root directory for path resolution. Defaults to current working directory.

        Returns:
            List of validation errors (empty if all required artifacts present).
        """
        errors: list[str] = []

        # Validate required artifacts
        for artifact in self.get_required_artifacts():
            artifact_errors = artifact.validate(root)
            if artifact_errors:
                errors.extend(artifact_errors)

        return errors

    def is_valid(self, root: Optional[Path] = None) -> bool:
        """Check if all required artifacts are present.

        Args:
            root: Root directory for path resolution.

        Returns:
            True if all required artifacts are present, False otherwise.
        """
        return len(self.validate(root)) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary.

        Returns:
            Dictionary representation of the checkpoint.
        """
        return {
            "from_role": self.from_role,
            "to_role": self.to_role,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "description": self.description,
            "required": self.required,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BMADCheckpoint:
        """Create checkpoint from dictionary.

        Args:
            data: Dictionary containing checkpoint data.

        Returns:
            BMADCheckpoint instance.
        """
        # Convert artifact dictionaries to ArtifactSpec objects
        artifacts = [
            ArtifactSpec.from_dict(a) for a in data.get("artifacts", [])
        ]

        return cls(
            from_role=data["from_role"],
            to_role=data["to_role"],
            artifacts=artifacts,
            description=data.get("description", ""),
            required=data.get("required", True),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        """Return string representation of the checkpoint."""
        return (
            f"BMADCheckpoint("
            f"from_role='{self.from_role}', "
            f"to_role='{self.to_role}', "
            f"artifacts={len(self.artifacts)}, "
            f"required={self.required})"
        )
