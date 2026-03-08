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
from autoflow.bmad.checkpoint import BMADCheckpoint
from autoflow.bmad.handoff import (
    Handoff,
    HandoffContext,
    HandoffStatus,
    create_handoff,
)


__all__ = [
    # Core classes
    "ArtifactSpec",
    "ArtifactType",
    "ArtifactCollection",
    "BMADCheckpoint",
    "Handoff",
    "HandoffContext",
    "HandoffStatus",
    "create_handoff",
]
