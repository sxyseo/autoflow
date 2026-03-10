"""Tests for BMAD artifact specifications module."""

import json
import tempfile
from pathlib import Path

import pytest

from autoflow.bmad.artifacts import ArtifactSpec, ArtifactType, ArtifactCollection


class TestArtifactSpec:
    """Test ArtifactSpec functionality."""

    def test_file_artifact_exists(self, tmp_path: Path) -> None:
        """Test that file artifact existence check works."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Create artifact spec
        artifact = ArtifactSpec(
            name="test_file",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
        )

        # Test existence check
        assert artifact.exists(root=tmp_path)

    def test_file_artifact_not_exists(self, tmp_path: Path) -> None:
        """Test that missing file artifact is detected."""
        artifact = ArtifactSpec(
            name="missing_file",
            type=ArtifactType.FILE,
            path="nonexistent.txt",
            required=True,
        )

        assert not artifact.exists(root=tmp_path)

    def test_directory_artifact_exists(self, tmp_path: Path) -> None:
        """Test that directory artifact existence check works."""
        # Create a test directory
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        artifact = ArtifactSpec(
            name="test_dir",
            type=ArtifactType.DIRECTORY,
            path=str(test_dir.relative_to(tmp_path)),
            required=True,
        )

        assert artifact.exists(root=tmp_path)

    def test_directory_artifact_not_exists(self, tmp_path: Path) -> None:
        """Test that missing directory artifact is detected."""
        artifact = ArtifactSpec(
            name="missing_dir",
            type=ArtifactType.DIRECTORY,
            path="nonexistent_dir",
            required=True,
        )

        assert not artifact.exists(root=tmp_path)

    def test_custom_artifact_exists(self, tmp_path: Path) -> None:
        """Test that custom artifact existence check works."""
        # Create a test file
        test_file = tmp_path / "custom.txt"
        test_file.write_text("custom content")

        artifact = ArtifactSpec(
            name="custom_artifact",
            type=ArtifactType.CUSTOM,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
        )

        assert artifact.exists(root=tmp_path)

    def test_validate_required_artifact_missing(self, tmp_path: Path) -> None:
        """Test validation fails when required artifact is missing."""
        artifact = ArtifactSpec(
            name="missing_required",
            type=ArtifactType.FILE,
            path="missing.txt",
            required=True,
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) > 0
        assert "not found" in errors[0].lower()

    def test_validate_optional_artifact_missing(self, tmp_path: Path) -> None:
        """Test validation passes when optional artifact is missing."""
        artifact = ArtifactSpec(
            name="missing_optional",
            type=ArtifactType.FILE,
            path="missing.txt",
            required=False,
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) == 0

    def test_validate_required_artifact_present(self, tmp_path: Path) -> None:
        """Test validation passes when required artifact is present."""
        test_file = tmp_path / "present.txt"
        test_file.write_text("content")

        artifact = ArtifactSpec(
            name="present_required",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) == 0

    def test_validate_empty_file_with_not_empty_check(self, tmp_path: Path) -> None:
        """Test content validation detects empty files."""
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        artifact = ArtifactSpec(
            name="empty_file",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
            content_check="not_empty",
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) > 0
        assert "empty" in errors[0].lower()

    def test_validate_non_empty_file(self, tmp_path: Path) -> None:
        """Test content validation passes for non-empty files."""
        test_file = tmp_path / "nonempty.txt"
        test_file.write_text("some content")

        artifact = ArtifactSpec(
            name="nonempty_file",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
            content_check="not_empty",
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) == 0

    def test_validate_valid_json(self, tmp_path: Path) -> None:
        """Test JSON validation passes for valid JSON."""
        test_file = tmp_path / "valid.json"
        test_file.write_text('{"key": "value"}')

        artifact = ArtifactSpec(
            name="valid_json",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
            content_check="valid_json",
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) == 0

    def test_validate_invalid_json(self, tmp_path: Path) -> None:
        """Test JSON validation fails for invalid JSON."""
        test_file = tmp_path / "invalid.json"
        test_file.write_text('{"key": invalid}')

        artifact = ArtifactSpec(
            name="invalid_json",
            type=ArtifactType.FILE,
            path=str(test_file.relative_to(tmp_path)),
            required=True,
            content_check="valid_json",
        )

        errors = artifact.validate(root=tmp_path)
        assert len(errors) > 0
        assert "not valid json" in errors[0].lower()

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        artifact = ArtifactSpec(
            name="test_artifact",
            type=ArtifactType.FILE,
            path="test.txt",
            required=True,
            description="Test artifact",
            content_check="not_empty",
        )

        artifact_dict = artifact.to_dict()
        assert artifact_dict["name"] == "test_artifact"
        assert artifact_dict["type"] == "file"
        assert artifact_dict["path"] == "test.txt"
        assert artifact_dict["required"] is True
        assert artifact_dict["description"] == "Test artifact"
        assert artifact_dict["content_check"] == "not_empty"

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        artifact_dict = {
            "name": "test_artifact",
            "type": "file",
            "path": "test.txt",
            "required": True,
            "description": "Test artifact",
            "content_check": "not_empty",
            "metadata": {"key": "value"},
        }

        artifact = ArtifactSpec.from_dict(artifact_dict)
        assert artifact.name == "test_artifact"
        assert artifact.type == ArtifactType.FILE
        assert artifact.path == "test.txt"
        assert artifact.required is True
        assert artifact.description == "Test artifact"
        assert artifact.content_check == "not_empty"
        assert artifact.metadata == {"key": "value"}


class TestArtifactCollection:
    """Test ArtifactCollection functionality."""

    def test_add_artifact(self) -> None:
        """Test adding artifacts to collection."""
        collection = ArtifactCollection(name="test_collection")
        artifact = ArtifactSpec(
            name="test", type=ArtifactType.FILE, path="test.txt"
        )

        collection.add_artifact(artifact)
        assert len(collection.artifacts) == 1
        assert collection.artifacts[0].name == "test"

    def test_validate_all_artifacts_pass(self, tmp_path: Path) -> None:
        """Test validation passes when all artifacts present."""
        # Create test files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        collection = ArtifactCollection(name="test_collection")
        collection.add_artifact(
            ArtifactSpec(
                name="file1",
                type=ArtifactType.FILE,
                path=str(file1.relative_to(tmp_path)),
                required=True,
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="file2",
                type=ArtifactType.FILE,
                path=str(file2.relative_to(tmp_path)),
                required=True,
            )
        )

        errors = collection.validate(root=tmp_path)
        assert len(errors) == 0

    def test_validate_artifacts_with_errors(self, tmp_path: Path) -> None:
        """Test validation returns errors for missing artifacts."""
        collection = ArtifactCollection(name="test_collection")
        collection.add_artifact(
            ArtifactSpec(
                name="present",
                type=ArtifactType.FILE,
                path="present.txt",
                required=True,
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="missing", type=ArtifactType.FILE, path="missing.txt", required=True
            )
        )

        # Create only one file
        (tmp_path / "present.txt").write_text("content")

        errors = collection.validate(root=tmp_path)
        assert len(errors) == 1
        assert "missing" in errors

    def test_get_required_artifacts(self) -> None:
        """Test filtering required artifacts."""
        collection = ArtifactCollection()
        collection.add_artifact(
            ArtifactSpec(
                name="required1", type=ArtifactType.FILE, path="req1.txt", required=True
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="optional1", type=ArtifactType.FILE, path="opt1.txt", required=False
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="required2", type=ArtifactType.FILE, path="req2.txt", required=True
            )
        )

        required = collection.get_required_artifacts()
        assert len(required) == 2
        assert all(a.required for a in required)

    def test_get_optional_artifacts(self) -> None:
        """Test filtering optional artifacts."""
        collection = ArtifactCollection()
        collection.add_artifact(
            ArtifactSpec(
                name="required1", type=ArtifactType.FILE, path="req1.txt", required=True
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="optional1", type=ArtifactType.FILE, path="opt1.txt", required=False
            )
        )
        collection.add_artifact(
            ArtifactSpec(
                name="optional2", type=ArtifactType.FILE, path="opt2.txt", required=False
            )
        )

        optional = collection.get_optional_artifacts()
        assert len(optional) == 2
        assert all(not a.required for a in optional)

    def test_to_dict(self) -> None:
        """Test collection conversion to dictionary."""
        collection = ArtifactCollection(
            name="test_collection", metadata={"key": "value"}
        )
        collection.add_artifact(
            ArtifactSpec(
                name="test", type=ArtifactType.FILE, path="test.txt", required=True
            )
        )

        collection_dict = collection.to_dict()
        assert collection_dict["name"] == "test_collection"
        assert len(collection_dict["artifacts"]) == 1
        assert collection_dict["metadata"]["key"] == "value"

    def test_from_dict(self) -> None:
        """Test collection creation from dictionary."""
        collection_dict = {
            "name": "test_collection",
            "artifacts": [
                {
                    "name": "test",
                    "type": "file",
                    "path": "test.txt",
                    "required": True,
                    "description": "",
                    "content_check": None,
                    "metadata": {},
                }
            ],
            "metadata": {"key": "value"},
        }

        collection = ArtifactCollection.from_dict(collection_dict)
        assert collection.name == "test_collection"
        assert len(collection.artifacts) == 1
        assert collection.artifacts[0].name == "test"
        assert collection.metadata["key"] == "value"
