"""
Autoflow BMAD - Breakdown, Make, and Debug Handoff Framework

This module provides structured role handoffs with checkpoints and artifact validation:
- BMADCheckpoint: Define required artifacts for role transitions
- ArtifactSpec: Specify validation rules for artifacts
- Handoff: Track structured context transfers between roles
- BMADManager: Orchestrate checkpoints and validate handoffs

Enables sophisticated agent coordination and quality control during
role transitions, reducing context loss and ensuring complete work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# NOTE: These are stub implementations for module structure.
# Full implementations will be provided in subsequent subtasks.


@dataclass
class ArtifactSpec:
    """Specification for an artifact required during a role transition.

    Attributes:
        name: Identifier for this artifact.
        type: Type of artifact (file, directory, git_state, etc.).
        path: Relative path to the artifact.
        required: Whether this artifact must exist before handoff.
        description: Optional description of the artifact.
        content_check: Optional validation rule for artifact content.
    """

    name: str
    type: str
    path: str
    required: bool = True
    description: str = ""
    content_check: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert spec to dictionary.

        Returns:
            Dictionary representation of the spec.
        """
        return {
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "required": self.required,
        }


@dataclass
class BMADCheckpoint:
    """Checkpoint defining requirements for a role transition.

    A BMADCheckpoint specifies the artifacts that must be present
    before a handoff from one role to another can be completed.

    Attributes:
        from_role: Source role for the transition.
        to_role: Destination role for the transition.
        artifacts: List of artifact specifications for this transition.
        description: Optional description of this checkpoint.
    """

    from_role: str
    to_role: str
    artifacts: list[ArtifactSpec] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Initialize artifacts list if not provided."""
        if self.artifacts is None:
            self.artifacts = []

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary.

        Returns:
            Dictionary representation of the checkpoint.
        """
        return {
            "from_role": self.from_role,
            "to_role": self.to_role,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


# Forward declarations for classes that will be implemented in later subtasks
# These are imported here for API convenience but will be fully implemented later


__all__ = [
    # Core classes
    "ArtifactSpec",
    "BMADCheckpoint",
]
