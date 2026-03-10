"""
Autoflow BMAD Handoff Module

Provides structured context transfer between agent roles in the BMAD framework.
Handoffs track role transitions, preserve context, and validate that required
artifacts are present before completing the transition.

Usage:
    from autoflow.bmad.handoff import Handoff, HandoffStatus

    # Create a handoff from writer to reviewer
    handoff = Handoff(
        role="writer",
        next_role="reviewer",
        status=HandoffStatus.PENDING
    )

    # Mark as in progress
    handoff.mark_started()

    # Complete the handoff
    handoff.mark_complete(HandoffStatus.COMPLETED)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from typing_extensions import TypedDict

from autoflow.bmad.artifacts import ArtifactCollection
from autoflow.bmad.checkpoint import BMADCheckpoint


class MetadataDict(TypedDict, total=False):
    """
    TypedDict for metadata fields in BMAD handoffs.

    Provides type structure for metadata dictionaries used in
    HandoffContext and Handoff models. All fields are optional
    to support flexible metadata.

    Common metadata fields include:
    - created_by: Agent or user who created the handoff
    - updated_by: Agent or user who last updated the handoff
    - source: Source system or process
    - tags: List of tags for categorization
    - priority: Handoff priority
    - Any additional string-keyed values
    """

    created_by: str
    updated_by: str
    source: str
    tags: list[str]
    priority: int


class HandoffStatus(str, Enum):
    """Status of a role handoff."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class HandoffContext:
    """
    Context transferred during a handoff.

    Attributes:
        task_description: Description of the task being worked on
        artifacts: Collection of artifacts produced by the current role
        metadata: Additional context information
        notes: Free-form notes or observations
    """

    task_description: str = ""
    artifacts: ArtifactCollection = field(default_factory=ArtifactCollection)
    metadata: MetadataDict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "task_description": self.task_description,
            "artifacts": self.artifacts.to_dict(),
            "metadata": self.metadata,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffContext:
        """Create context from dictionary."""
        artifacts_data = data.get("artifacts", {})
        artifacts = ArtifactCollection.from_dict(artifacts_data)

        return cls(
            task_description=data.get("task_description", ""),
            artifacts=artifacts,
            metadata=data.get("metadata", {}),
            notes=data.get("notes", ""),
        )


@dataclass
class Handoff:
    """
    Structured handoff between agent roles.

    A Handoff represents the transition from one role to another, including
    the context that needs to be transferred and validation that required
    artifacts are present.

    Key features:
    - Role transition tracking (from_role → to_role)
    - Status management (pending → in_progress → completed/failed)
    - Context preservation across role boundaries
    - Artifact validation via checkpoints
    - Full audit trail for debugging

    Example:
        >>> from autoflow.bmad.handoff import Handoff, HandoffStatus
        >>>
        >>> # Create handoff
        >>> handoff = Handoff(
        ...     role="writer",
        ...     next_role="reviewer",
        ...     status=HandoffStatus.PENDING
        ... )
        >>>
        >>> # Mark as started
        >>> handoff.mark_started()
        >>>
        >>> # Complete the handoff
        >>> handoff.mark_complete(HandoffStatus.COMPLETED)

    Attributes:
        handoff_id: Unique identifier for this handoff
        role: Current role (source of the handoff)
        next_role: Next role (destination of the handoff)
        status: Current handoff status
        checkpoint: Optional checkpoint for artifact validation
        context: Context transferred between roles
        created_at: When the handoff was created
        started_at: When the handoff was started
        completed_at: When the handoff was completed
        duration_seconds: Total duration of the handoff
        validation_errors: List of validation errors (if any)
        metadata: Additional metadata for tracking
    """

    handoff_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: str = ""
    next_role: str = ""
    status: HandoffStatus = HandoffStatus.PENDING
    checkpoint: Optional[BMADCheckpoint] = None
    context: HandoffContext = field(default_factory=HandoffContext)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    validation_errors: list[str] = field(default_factory=list)
    metadata: MetadataDict = field(default_factory=dict)

    @property
    def from_role(self) -> str:
        """Alias for role (source role)."""
        return self.role

    @property
    def to_role(self) -> str:
        """Alias for next_role (destination role)."""
        return self.next_role

    @property
    def is_pending(self) -> bool:
        """Check if handoff is pending."""
        return self.status == HandoffStatus.PENDING

    @property
    def is_in_progress(self) -> bool:
        """Check if handoff is in progress."""
        return self.status == HandoffStatus.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        """Check if handoff completed successfully."""
        return self.status == HandoffStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """Check if handoff failed."""
        return self.status in (
            HandoffStatus.FAILED,
            HandoffStatus.CANCELLED,
            HandoffStatus.TIMEOUT,
        )

    @property
    def can_proceed(self) -> bool:
        """Check if handoff can proceed (not failed or cancelled)."""
        return not self.is_failed

    def mark_started(self) -> None:
        """Mark the handoff as started."""
        self.status = HandoffStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()

    def mark_validating(self) -> None:
        """Mark the handoff as validating artifacts."""
        self.status = HandoffStatus.VALIDATING

    def mark_complete(
        self,
        status: HandoffStatus,
        validation_errors: Optional[list[str]] = None,
    ) -> None:
        """
        Mark the handoff as complete.

        Args:
            status: Final handoff status
            validation_errors: Optional list of validation errors
        """
        self.status = status
        self.completed_at = datetime.utcnow()
        if validation_errors:
            self.validation_errors = validation_errors

        # Calculate duration
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def validate_artifacts(self, root: Optional[Path | str] = None) -> list[str]:
        """
        Validate required artifacts against the checkpoint.

        Args:
            root: Root directory for path resolution.

        Returns:
            List of validation errors (empty if validation passes).
        """
        self.validation_errors = []

        if self.checkpoint:
            self.mark_validating()
            errors = self.checkpoint.validate(root)
            self.validation_errors = errors

            if errors:
                self.mark_complete(HandoffStatus.FAILED, errors)
            else:
                self.mark_complete(HandoffStatus.COMPLETED)

        return self.validation_errors

    def add_artifact(
        self,
        name: str,
        path: str,
        artifact_type: str = "file",
        required: bool = True,
    ) -> None:
        """
        Add an artifact to the handoff context.

        Args:
            name: Artifact name
            path: Artifact path
            artifact_type: Type of artifact (file, directory, url, etc.)
            required: Whether artifact is required
        """
        from autoflow.bmad.artifacts import ArtifactSpec, ArtifactType

        # Convert string to ArtifactType if needed
        if isinstance(artifact_type, str):
            artifact_type = ArtifactType(artifact_type)

        artifact = ArtifactSpec(
            name=name,
            path=path,
            artifact_type=artifact_type,
            required=required,
        )

        self.context.artifacts.add_artifact(artifact)

    def set_task_description(self, description: str) -> None:
        """
        Set the task description for this handoff.

        Args:
            description: Task description
        """
        self.context.task_description = description

    def add_notes(self, notes: str) -> None:
        """
        Add notes to the handoff context.

        Args:
            notes: Notes to add
        """
        if self.context.notes:
            self.context.notes += f"\n{notes}"
        else:
            self.context.notes = notes

    def add_metadata(self, key: str, value: Any) -> None:
        """
        Add metadata to the handoff.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self.metadata[key] = value

    def to_dict(self) -> dict[str, Any]:
        """
        Convert handoff to dictionary.

        Returns:
            Dictionary representation of the handoff.
        """
        return {
            "handoff_id": self.handoff_id,
            "role": self.role,
            "next_role": self.next_role,
            "status": self.status.value,
            "checkpoint": self.checkpoint.to_dict() if self.checkpoint else None,
            "context": self.context.to_dict(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_seconds": self.duration_seconds,
            "validation_errors": self.validation_errors,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Handoff:
        """
        Create handoff from dictionary.

        Args:
            data: Dictionary containing handoff data.

        Returns:
            Handoff instance.
        """
        # Reconstruct checkpoint if present
        checkpoint = None
        if data.get("checkpoint"):
            checkpoint = BMADCheckpoint.from_dict(data["checkpoint"])

        # Reconstruct context
        context_data = data.get("context", {})
        context = HandoffContext.from_dict(context_data)

        # Parse datetime strings
        created_at = None
        started_at = None
        completed_at = None

        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])
        if data.get("started_at"):
            started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            completed_at = datetime.fromisoformat(data["completed_at"])

        return cls(
            handoff_id=data.get("handoff_id", ""),
            role=data.get("role", ""),
            next_role=data.get("next_role", ""),
            status=HandoffStatus(data.get("status", "pending")),
            checkpoint=checkpoint,
            context=context,
            created_at=created_at or datetime.utcnow(),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=data.get("duration_seconds"),
            validation_errors=data.get("validation_errors", []),
            metadata=data.get("metadata", {}),
        )

    def __repr__(self) -> str:
        """Return string representation of the handoff."""
        return (
            f"Handoff("
            f"id='{self.handoff_id}', "
            f"role='{self.role}', "
            f"next_role='{self.next_role}', "
            f"status='{self.status.value}')"
        )


def create_handoff(
    role: str,
    next_role: str,
    task_description: str = "",
    checkpoint: Optional[BMADCheckpoint] = None,
    metadata: Optional[MetadataDict] = None,
) -> Handoff:
    """
    Factory function to create a configured handoff.

    Args:
        role: Current role (source)
        next_role: Next role (destination)
        task_description: Optional task description
        checkpoint: Optional checkpoint for validation
        metadata: Optional metadata

    Returns:
        Configured Handoff instance

    Example:
        >>> from autoflow.bmad.handoff import create_handoff
        >>> from autoflow.bmad.checkpoint import BMADCheckpoint
        >>>
        >>> checkpoint = BMADCheckpoint(
        ...     from_role="writer",
        ...     to_role="reviewer"
        ... )
        >>>
        >>> handoff = create_handoff(
        ...     role="writer",
        ...     next_role="reviewer",
        ...     task_description="Write documentation",
        ...     checkpoint=checkpoint
        ... )
    """
    handoff = Handoff(
        role=role,
        next_role=next_role,
        checkpoint=checkpoint,
        metadata=metadata or {},
    )

    if task_description:
        handoff.set_task_description(task_description)

    return handoff
