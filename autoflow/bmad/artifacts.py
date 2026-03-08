"""BMAD artifact specifications module.

This module provides data structures for defining required artifacts
that must be present before role transitions can occur. Artifacts
represent deliverables like files, directories, or documentation
that agents must produce during their work.

Usage:
    from autoflow.bmad.artifacts import ArtifactSpec, ArtifactType

    # Define a required file artifact
    artifact = ArtifactSpec(
        name="implementation_plan",
        type=ArtifactType.FILE,
        path="implementation_plan.json",
        required=True
    )

    # Check if artifact exists
    if artifact.exists():
        print("Artifact is present")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ArtifactType(str, Enum):
    """Types of artifacts that can be required."""

    FILE = "file"
    DIRECTORY = "directory"
    DOCUMENTATION = "documentation"
    TEST = "test"
    CONFIG = "config"
    CUSTOM = "custom"


@dataclass
class ArtifactSpec:
    """
    Specification for a required artifact.

    Artifacts represent deliverables that must be present before
    a role transition can occur. This enables validation that
    agents have completed their work before handoff.

    Attributes:
        name: Unique identifier for this artifact
        type: Type of artifact (file, directory, etc.)
        path: Relative path to the artifact
        required: Whether this artifact must be present
        description: Optional description of the artifact
        content_check: Optional content validation rule
        metadata: Additional artifact metadata
    """

    name: str
    type: ArtifactType
    path: str
    required: bool = True
    description: str = ""
    content_check: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def exists(self, root: Optional[Path] = None) -> bool:
        """
        Check if the artifact exists.

        Args:
            root: Root directory for path resolution. Defaults to current working directory.

        Returns:
            True if artifact exists, False otherwise.
        """
        base_path = root or Path.cwd()
        artifact_path = base_path / self.path

        if self.type == ArtifactType.FILE:
            return artifact_path.is_file()
        elif self.type == ArtifactType.DIRECTORY:
            return artifact_path.is_dir()
        else:
            # For other types, check if path exists (file or dir)
            return artifact_path.exists()

    def validate(self, root: Optional[Path] = None) -> list[str]:
        """
        Validate the artifact specification.

        Args:
            root: Root directory for path resolution.

        Returns:
            List of validation errors (empty if valid).
        """
        errors: list[str] = []

        base_path = root or Path.cwd()
        artifact_path = base_path / self.path

        # Check if artifact exists
        if not self.exists(root):
            if self.required:
                errors.append(
                    f"Required artifact '{self.name}' not found at {self.path}"
                )
        else:
            # Perform content validation if specified
            if self.content_check:
                content_errors = self._validate_content(artifact_path)
                errors.extend(content_errors)

        return errors

    def _validate_content(self, artifact_path: Path) -> list[str]:
        """
        Validate artifact content based on content_check rule.

        Args:
            artifact_path: Path to the artifact.

        Returns:
            List of validation errors.
        """
        errors: list[str] = []

        if self.content_check == "not_empty":
            if artifact_path.is_file():
                if artifact_path.stat().st_size == 0:
                    errors.append(f"Artifact '{self.name}' is empty")
            elif artifact_path.is_dir():
                if not list(artifact_path.iterdir()):
                    errors.append(f"Artifact '{self.name}' directory is empty")

        elif self.content_check == "valid_json":
            if artifact_path.is_file():
                try:
                    import json

                    with artifact_path.open("r") as f:
                        json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    errors.append(f"Artifact '{self.name}' is not valid JSON: {e}")

        elif self.content_check == "valid_yaml":
            if artifact_path.is_file():
                try:
                    import yaml

                    with artifact_path.open("r") as f:
                        yaml.safe_load(f)
                except (yaml.YAMLError, OSError) as e:
                    errors.append(f"Artifact '{self.name}' is not valid YAML: {e}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """
        Convert artifact specification to dictionary.

        Returns:
            Dictionary representation of the artifact.
        """
        return {
            "name": self.name,
            "type": self.type.value,
            "path": self.path,
            "required": self.required,
            "description": self.description,
            "content_check": self.content_check,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactSpec:
        """
        Create artifact specification from dictionary.

        Args:
            data: Dictionary containing artifact specification.

        Returns:
            ArtifactSpec instance.
        """
        # Convert type string to ArtifactType enum
        if "type" in data and isinstance(data["type"], str):
            data = data.copy()
            data["type"] = ArtifactType(data["type"])

        return cls(**data)


@dataclass
class ArtifactCollection:
    """
    Collection of artifact specifications.

    Manages multiple artifacts that must be validated together,
    typically for a specific role transition checkpoint.

    Attributes:
        artifacts: List of artifact specifications
        name: Optional name for this collection
        metadata: Additional collection metadata
    """

    artifacts: list[ArtifactSpec] = field(default_factory=list)
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_artifact(self, artifact: ArtifactSpec) -> None:
        """
        Add an artifact to the collection.

        Args:
            artifact: Artifact specification to add.
        """
        self.artifacts.append(artifact)

    def validate(self, root: Optional[Path] = None) -> dict[str, list[str]]:
        """
        Validate all artifacts in the collection.

        Args:
            root: Root directory for path resolution.

        Returns:
            Dictionary mapping artifact names to validation errors.
        """
        errors: dict[str, list[str]] = {}

        for artifact in self.artifacts:
            artifact_errors = artifact.validate(root)
            if artifact_errors:
                errors[artifact.name] = artifact_errors

        return errors

    def get_required_artifacts(self) -> list[ArtifactSpec]:
        """
        Get list of required artifacts.

        Returns:
            List of required artifact specifications.
        """
        return [a for a in self.artifacts if a.required]

    def get_optional_artifacts(self) -> list[ArtifactSpec]:
        """
        Get list of optional artifacts.

        Returns:
            List of optional artifact specifications.
        """
        return [a for a in self.artifacts if not a.required]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert collection to dictionary.

        Returns:
            Dictionary representation of the collection.
        """
        return {
            "name": self.name,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactCollection:
        """
        Create collection from dictionary.

        Args:
            data: Dictionary containing collection data.

        Returns:
            ArtifactCollection instance.
        """
        artifacts = [
            ArtifactSpec.from_dict(a) for a in data.get("artifacts", [])
        ]
        return cls(
            artifacts=artifacts,
            name=data.get("name", ""),
            metadata=data.get("metadata", {}),
        )
