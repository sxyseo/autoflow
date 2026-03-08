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

from autoflow.bmad.artifacts import (
    ArtifactCollection,
    ArtifactSpec,
    ArtifactType,
)


# NOTE: BMADCheckpoint is a stub implementation for module structure.
# Full implementation will be provided in subtask-1-3.

from dataclasses import dataclass
from typing import Any


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


__all__ = [
    # Core classes
    "ArtifactSpec",
    "ArtifactType",
    "ArtifactCollection",
    "BMADCheckpoint",
]
