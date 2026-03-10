"""
Unit Tests for Skill Sharing and Versioning

Tests the SkillPackager, SkillImporter, and VersionManager classes
for packaging, importing, and versioning skill definitions.

These tests use temporary directories and mock files to avoid
requiring actual skill files in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import pytest

from autoflow.skills import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
)
from autoflow.skills.sharing import (
    ImportConflictResolution,
    ImportResult,
    PackageError,
    PackageFormat,
    SkillImporter,
    SkillPackager,
    SkillPackage,
    SkillPackageMetadata,
    VersionAction,
    VersionChangeResult,
    VersionHistoryEntry,
    VersionManager,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory for packages."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def valid_skill_content() -> str:
    """Return valid skill file content with frontmatter."""
    return """---
name: TEST_SKILL
description: A test skill for unit testing
version: "1.0.0"
triggers:
  - test_trigger
inputs:
  - input1
outputs:
  - output1
agents:
  - claude-code
enabled: true
---

## Role

This is a test skill for unit testing.

## Workflow

1. Step one
2. Step two
"""


@pytest.fixture
def registry_with_skill(
    temp_skills_dir: Path,
    valid_skill_content: str,
) -> SkillRegistry:
    """Create a registry with a test skill loaded."""
    skill_dir = temp_skills_dir / "test_skill"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(valid_skill_content, encoding="utf-8")

    registry = SkillRegistry(skills_dirs=[temp_skills_dir])
    registry.load_skills()
    return registry


@pytest.fixture
def packager(registry_with_skill: SkillRegistry) -> SkillPackager:
    """Create a SkillPackager with a test registry."""
    return SkillPackager(registry=registry_with_skill)


@pytest.fixture
def importer() -> SkillImporter:
    """Create a SkillImporter."""
    return SkillImporter()


@pytest.fixture
def version_manager(tmp_path: Path) -> VersionManager:
    """Create a VersionManager with temp directories."""
    skills_dir = tmp_path / "skills"
    history_dir = tmp_path / "history"
    backup_dir = tmp_path / "backups"

    return VersionManager(
        skills_dir=skills_dir,
        history_dir=history_dir,
        backup_dir=backup_dir,
    )


# ============================================================================
# Helper Functions
# ============================================================================


def create_skill_file(
    skills_dir: Path,
    skill_name: str,
    content: str,
) -> Path:
    """Create a skill file in the skills directory."""
    skill_dir = skills_dir / skill_name.lower()
    skill_dir.mkdir(exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def create_package_file(
    output_dir: Path,
    package_name: str,
    skill_content: str,
    format: PackageFormat = PackageFormat.TAR_GZ,
) -> Path:
    """Create a mock package file for testing imports."""
    import tarfile
    import json

    metadata = SkillPackageMetadata(
        name=package_name,
        version="1.0.0",
        description="Test package",
        skills=["TEST_SKILL"],
    )

    if format == PackageFormat.DIR:
        # Create as directory
        package_dir = output_dir / package_name
        package_dir.mkdir()

        skills_dir = package_dir / "skills"
        skills_dir.mkdir()

        skill_dir = skills_dir / "test_skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_content, encoding="utf-8")

        manifest_file = package_dir / "manifest.json"
        manifest_file.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

        return package_dir
    else:
        # Create as archive
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            skills_dir = temp_path / "skills"
            skills_dir.mkdir()

            skill_dir = skills_dir / "test_skill"
            skill_dir.mkdir()
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(skill_content, encoding="utf-8")

            manifest_file = temp_path / "manifest.json"
            manifest_file.write_text(json.dumps(metadata.to_dict(), indent=2), encoding="utf-8")

            # Create archive
            package_path = output_dir / f"{package_name}.{format.value}"
            mode = "w:gz" if format == PackageFormat.TAR_GZ else "w"

            with tarfile.open(package_path, mode) as tar:
                for item in temp_path.rglob("*"):
                    if item.is_file():
                        arcname = item.relative_to(temp_path)
                        tar.add(item, arcname=arcname)

            return package_path


# ============================================================================
# SkillPackageMetadata Tests
# ============================================================================


class TestSkillPackageMetadata:
    """Tests for SkillPackageMetadata dataclass."""

    def test_metadata_init_minimal(self) -> None:
        """Test metadata initialization with minimal fields."""
        metadata = SkillPackageMetadata(
            name="test_package",
            version="1.0.0",
        )

        assert metadata.name == "test_package"
        assert metadata.version == "1.0.0"
        assert metadata.description == ""
        assert metadata.skills == []
        assert metadata.created_by is None
        assert metadata.autoflow_version is None
        assert metadata.dependencies == []
        assert metadata.metadata == {}

    def test_metadata_init_full(self) -> None:
        """Test metadata initialization with all fields."""
        metadata = SkillPackageMetadata(
            name="full_package",
            version="2.0.0",
            description="Full description",
            skills=["SKILL_A", "SKILL_B"],
            created_by="test@example.com",
            autoflow_version="1.5.0",
            dependencies=["dep1", "dep2"],
            metadata={"key": "value"},
        )

        assert metadata.name == "full_package"
        assert metadata.version == "2.0.0"
        assert metadata.description == "Full description"
        assert metadata.skills == ["SKILL_A", "SKILL_B"]
        assert metadata.created_by == "test@example.com"
        assert metadata.autoflow_version == "1.5.0"
        assert metadata.dependencies == ["dep1", "dep2"]
        assert metadata.metadata == {"key": "value"}

    def test_metadata_to_dict(self) -> None:
        """Test converting metadata to dictionary."""
        metadata = SkillPackageMetadata(
            name="test",
            version="1.0.0",
            description="Test package",
        )

        data = metadata.to_dict()

        assert data["name"] == "test"
        assert data["version"] == "1.0.0"
        assert data["description"] == "Test package"
        assert "created_at" in data

    def test_metadata_from_dict(self) -> None:
        """Test creating metadata from dictionary."""
        data = {
            "name": "test",
            "version": "1.0.0",
            "description": "Test package",
            "skills": ["SKILL_A"],
            "created_at": "2024-01-01T00:00:00",
            "created_by": None,
            "autoflow_version": None,
            "dependencies": [],
            "metadata": {},
        }

        metadata = SkillPackageMetadata.from_dict(data)

        assert metadata.name == "test"
        assert metadata.version == "1.0.0"
        assert metadata.description == "Test package"

    def test_metadata_repr(self) -> None:
        """Test string representation."""
        metadata = SkillPackageMetadata(name="test", version="1.0.0")
        repr_str = repr(metadata)

        assert "SkillPackageMetadata" in repr_str
        assert "test" in repr_str
        assert "1.0.0" in repr_str


# ============================================================================
# SkillPackage Tests
# ============================================================================


class TestSkillPackage:
    """Tests for SkillPackage dataclass."""

    def test_package_init(self) -> None:
        """Test package initialization."""
        metadata = SkillPackageMetadata(name="test", version="1.0.0")
        package = SkillPackage(
            path=Path("/test/package.tar.gz"),
            metadata=metadata,
            format=PackageFormat.TAR_GZ,
            size=1024,
        )

        assert package.path == Path("/test/package.tar.gz")
        assert package.metadata == metadata
        assert package.format == PackageFormat.TAR_GZ
        assert package.size == 1024

    def test_package_repr(self) -> None:
        """Test string representation."""
        metadata = SkillPackageMetadata(
            name="test",
            version="1.0.0",
            skills=["SKILL_A", "SKILL_B"],
        )
        package = SkillPackage(
            path=Path("/test/package.tar.gz"),
            metadata=metadata,
            format=PackageFormat.TAR_GZ,
        )

        repr_str = repr(package)

        assert "SkillPackage" in repr_str
        assert "package.tar.gz" in repr_str
        assert "tar.gz" in repr_str
        assert "skills=2" in repr_str


# ============================================================================
# SkillPackager Tests
# ============================================================================


class TestSkillPackagerInit:
    """Tests for SkillPackager initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        packager = SkillPackager()

        assert packager.registry is not None
        assert isinstance(packager.registry, SkillRegistry)
        assert packager.include_metadata is True
        assert packager.get_errors() == []

    def test_init_with_registry(self, registry_with_skill: SkillRegistry) -> None:
        """Test initialization with registry."""
        packager = SkillPackager(registry=registry_with_skill)

        assert packager.registry == registry_with_skill
        assert packager.include_metadata is True

    def test_init_without_metadata(self) -> None:
        """Test initialization without metadata."""
        packager = SkillPackager(include_metadata=False)

        assert packager.include_metadata is False


class TestSkillPackagerExportSkill:
    """Tests for SkillPackager.export_skill method."""

    def test_export_skill_success(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test successful skill export."""
        output_path = temp_output_dir / "test-skill-1.0.0.tar.gz"

        package = packager.export_skill("TEST_SKILL", output_path)

        assert package.path == output_path
        assert package.format == PackageFormat.TAR_GZ
        assert package.metadata.name == "test_skill"
        assert package.metadata.version == "1.0.0"
        assert "TEST_SKILL" in package.metadata.skills
        assert output_path.exists()

    def test_export_skill_not_found(self, packager: SkillPackager) -> None:
        """Test exporting non-existent skill raises error."""
        with pytest.raises(PackageError) as exc_info:
            packager.export_skill("NONEXISTENT", "/tmp/output.tar.gz")

        assert "not found" in str(exc_info.value)

    def test_export_skill_custom_version(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting skill with custom version."""
        output_path = temp_output_dir / "test-skill-2.0.0.tar.gz"

        package = packager.export_skill("TEST_SKILL", output_path, version="2.0.0")

        assert package.metadata.version == "2.0.0"

    def test_export_skill_custom_description(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting skill with custom description."""
        output_path = temp_output_dir / "test-skill.tar.gz"

        package = packager.export_skill(
            "TEST_SKILL",
            output_path,
            description="Custom description",
        )

        assert package.metadata.description == "Custom description"

    def test_export_skill_tar_format(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting skill as tar archive."""
        output_path = temp_output_dir / "test-skill.tar"

        package = packager.export_skill("TEST_SKILL", output_path, format=PackageFormat.TAR)

        assert package.format == PackageFormat.TAR
        assert output_path.exists()

    def test_export_skill_dir_format(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting skill as directory."""
        output_path = temp_output_dir / "test-skill"

        package = packager.export_skill("TEST_SKILL", output_path, format=PackageFormat.DIR)

        assert package.format == PackageFormat.DIR
        assert output_path.is_dir()
        assert (output_path / "manifest.json").exists()
        assert (output_path / "skills" / "test_skill" / "SKILL.md").exists()

    def test_export_skill_dir_exists(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting to existing directory raises error."""
        output_path = temp_output_dir / "existing_dir"
        output_path.mkdir()

        with pytest.raises(PackageError) as exc_info:
            packager.export_skill("TEST_SKILL", output_path, format=PackageFormat.DIR)

        assert "already exists" in str(exc_info.value)


class TestSkillPackagerExportSkills:
    """Tests for SkillPackager.export_skills method."""

    def test_export_multiple_skills(
        self,
        temp_skills_dir: Path,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting multiple skills."""
        # Create multiple skills
        skill_content = """---
name: SKILL_A
version: "1.0.0"
---
Content A.
"""
        create_skill_file(temp_skills_dir, "skill_a", skill_content)

        skill_content_b = """---
name: SKILL_B
version: "1.0.0"
---
Content B.
"""
        create_skill_file(temp_skills_dir, "skill_b", skill_content_b)

        # Load into registry
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        packager = SkillPackager(registry=registry)
        output_path = temp_output_dir / "collection-1.0.0.tar.gz"

        package = packager.export_skills(["SKILL_A", "SKILL_B"], output_path)

        assert package.metadata.name == "skill_a"
        assert len(package.metadata.skills) == 2
        assert "SKILL_A" in package.metadata.skills
        assert "SKILL_B" in package.metadata.skills

    def test_export_skills_empty_list(self, packager: SkillPackager) -> None:
        """Test exporting empty skill list raises error."""
        with pytest.raises(PackageError) as exc_info:
            packager.export_skills([], "/tmp/output.tar.gz")

        assert "No skills specified" in str(exc_info.value)

    def test_export_skills_missing_skill(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting with missing skill raises error."""
        output_path = temp_output_dir / "collection.tar.gz"

        with pytest.raises(PackageError) as exc_info:
            packager.export_skills(["TEST_SKILL", "MISSING"], output_path)

        assert "not found" in str(exc_info.value)

    def test_export_skills_custom_name(
        self,
        packager: SkillPackager,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting skills with custom package name."""
        output_path = temp_output_dir / "custom-name.tar.gz"

        package = packager.export_skills(
            ["TEST_SKILL"],
            output_path,
            name="custom_collection",
        )

        assert package.metadata.name == "custom_collection"


class TestSkillPackagerRepr:
    """Tests for SkillPackager string representation."""

    def test_repr(self, packager: SkillPackager) -> None:
        """Test string representation."""
        repr_str = repr(packager)

        assert "SkillPackager" in repr_str
        assert "registry" in repr_str


# ============================================================================
# SkillImporter Tests
# ============================================================================


class TestSkillImporterInit:
    """Tests for SkillImporter initialization."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        importer = SkillImporter()

        assert importer.registry is not None
        assert isinstance(importer.registry, SkillRegistry)
        assert importer.get_errors() == []

    def test_init_with_registry(self, registry_with_skill: SkillRegistry) -> None:
        """Test initialization with registry."""
        importer = SkillImporter(registry=registry_with_skill)

        assert importer.registry == registry_with_skill


class TestSkillImporterImportPackage:
    """Tests for SkillImporter.import_package method."""

    def test_import_tar_gz_success(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test importing tar.gz package successfully."""
        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.TAR_GZ,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.ERROR,
        )

        assert result.success
        assert "TEST_SKILL" in result.imported
        assert len(result.skipped) == 0
        assert len(result.conflicts) == 0
        assert (temp_skills_dir / "test_skill" / "SKILL.md").exists()

    def test_import_tar_success(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test importing tar package successfully."""
        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.TAR,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.ERROR,
        )

        assert result.success
        assert "TEST_SKILL" in result.imported

    def test_import_dir_success(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test importing directory package successfully."""
        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.DIR,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.ERROR,
        )

        assert result.success
        assert "TEST_SKILL" in result.imported

    def test_import_conflict_error(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test import with conflict raises error."""
        # Create existing skill
        create_skill_file(temp_skills_dir, "test_skill", valid_skill_content)

        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.TAR_GZ,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.ERROR,
        )

        assert "TEST_SKILL" in result.conflicts
        assert len(result.imported) == 0

    def test_import_conflict_skip(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test import with conflict skips existing skill."""
        # Create existing skill
        create_skill_file(temp_skills_dir, "test_skill", valid_skill_content)

        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.TAR_GZ,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.SKIP,
        )

        assert "TEST_SKILL" in result.skipped
        assert len(result.imported) == 0

    def test_import_conflict_overwrite(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test import with conflict overwrites existing skill."""
        # Create existing skill with different content
        old_content = """---
name: TEST_SKILL
version: "0.5.0"
---
Old content.
"""
        create_skill_file(temp_skills_dir, "test_skill", old_content)

        package_path = create_package_file(
            temp_output_dir,
            "test-package",
            valid_skill_content,
            PackageFormat.TAR_GZ,
        )

        result = importer.import_package(
            package_path,
            temp_skills_dir,
            conflict_resolution=ImportConflictResolution.OVERWRITE,
        )

        assert "TEST_SKILL" in result.imported
        # Verify content was updated
        skill_file = temp_skills_dir / "test_skill" / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        assert "A test skill for unit testing" in content

    def test_import_missing_manifest(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
    ) -> None:
        """Test importing package without manifest raises error."""
        # Create invalid package without manifest
        import tarfile
        package_path = temp_output_dir / "invalid.tar.gz"

        with tarfile.open(package_path, "w:gz") as tar:
            # Add some file but no manifest.json
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
                f.write("test")
                f.flush()
                tar.add(f.name, arcname="test.txt")

        with pytest.raises(PackageError) as exc_info:
            importer.import_package(package_path, temp_skills_dir)

        assert "manifest" in str(exc_info.value).lower()

    def test_import_missing_skills_dir(
        self,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
    ) -> None:
        """Test importing package without skills directory raises error."""
        # Create package with manifest but no skills dir
        import tarfile
        import json
        import tempfile

        package_path = temp_output_dir / "invalid.tar.gz"

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            metadata = SkillPackageMetadata(name="test", version="1.0.0")
            manifest_path.write_text(json.dumps(metadata.to_dict()), encoding="utf-8")

            with tarfile.open(package_path, "w:gz") as tar:
                tar.add(manifest_path, arcname="manifest.json")

        with pytest.raises(PackageError) as exc_info:
            importer.import_package(package_path, temp_skills_dir)

        assert "skills" in str(exc_info.value).lower()


class TestSkillImporterRepr:
    """Tests for SkillImporter string representation."""

    def test_repr(self, importer: SkillImporter) -> None:
        """Test string representation."""
        repr_str = repr(importer)

        assert "SkillImporter" in repr_str
        assert "registry" in repr_str


# ============================================================================
# ImportResult Tests
# ============================================================================


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_result_init_default(self) -> None:
        """Test default initialization."""
        result = ImportResult()

        assert result.imported == []
        assert result.skipped == []
        assert result.conflicts == []
        assert result.errors == []
        assert result.backup_paths == {}

    def test_result_success_property(self) -> None:
        """Test success property."""
        result = ImportResult()
        assert result.success is True

        result.errors.append("Some error")
        assert result.success is False

    def test_result_repr(self) -> None:
        """Test string representation."""
        result = ImportResult(
            imported=["SKILL_A", "SKILL_B"],
            skipped=["SKILL_C"],
        )

        repr_str = repr(result)

        assert "ImportResult" in repr_str
        assert "imported=2" in repr_str
        assert "skipped=1" in repr_str


# ============================================================================
# VersionHistoryEntry Tests
# ============================================================================


class TestVersionHistoryEntry:
    """Tests for VersionHistoryEntry dataclass."""

    def test_entry_init(self) -> None:
        """Test entry initialization."""
        entry = VersionHistoryEntry(
            version="1.0.0",
            installed_at="2024-01-01T00:00:00",
            file_path=Path("/skills/test/SKILL.md"),
            action=VersionAction.INSTALL,
        )

        assert entry.version == "1.0.0"
        assert entry.installed_at == "2024-01-01T00:00:00"
        assert entry.file_path == Path("/skills/test/SKILL.md")
        assert entry.action == VersionAction.INSTALL
        assert entry.package_path is None
        assert entry.metadata == {}

    def test_entry_to_dict(self) -> None:
        """Test converting entry to dictionary."""
        entry = VersionHistoryEntry(
            version="1.0.0",
            installed_at="2024-01-01T00:00:00",
            file_path=Path("/skills/test/SKILL.md"),
            package_path=Path("/packages/test-1.0.0.tar.gz"),
            action=VersionAction.UPGRADE,
        )

        data = entry.to_dict()

        assert data["version"] == "1.0.0"
        assert data["installed_at"] == "2024-01-01T00:00:00"
        assert data["file_path"] == "/skills/test/SKILL.md"
        assert data["package_path"] == "/packages/test-1.0.0.tar.gz"
        assert data["action"] == "upgrade"

    def test_entry_from_dict(self) -> None:
        """Test creating entry from dictionary."""
        data = {
            "version": "1.0.0",
            "installed_at": "2024-01-01T00:00:00",
            "file_path": "/skills/test/SKILL.md",
            "package_path": "/packages/test-1.0.0.tar.gz",
            "action": "upgrade",
            "metadata": {},
        }

        entry = VersionHistoryEntry.from_dict(data)

        assert entry.version == "1.0.0"
        assert entry.file_path == Path("/skills/test/SKILL.md")
        assert entry.package_path == Path("/packages/test-1.0.0.tar.gz")
        assert entry.action == VersionAction.UPGRADE

    def test_entry_repr(self) -> None:
        """Test string representation."""
        entry = VersionHistoryEntry(
            version="1.0.0",
            installed_at="2024-01-01T00:00:00",
            file_path=Path("/skills/test/SKILL.md"),
            action=VersionAction.INSTALL,
        )

        repr_str = repr(entry)

        assert "VersionHistoryEntry" in repr_str
        assert "1.0.0" in repr_str
        assert "install" in repr_str


# ============================================================================
# VersionChangeResult Tests
# ============================================================================


class TestVersionChangeResult:
    """Tests for VersionChangeResult dataclass."""

    def test_result_init(self) -> None:
        """Test result initialization."""
        result = VersionChangeResult(
            success=True,
            action=VersionAction.UPGRADE,
            skill_name="TEST_SKILL",
            new_version="2.0.0",
            previous_version="1.0.0",
        )

        assert result.success is True
        assert result.action == VersionAction.UPGRADE
        assert result.skill_name == "TEST_SKILL"
        assert result.new_version == "2.0.0"
        assert result.previous_version == "1.0.0"
        assert result.backup_path is None
        assert result.message == ""

    def test_result_repr(self) -> None:
        """Test string representation."""
        result = VersionChangeResult(
            success=True,
            action=VersionAction.UPGRADE,
            skill_name="TEST_SKILL",
            new_version="2.0.0",
            previous_version="1.0.0",
        )

        repr_str = repr(result)

        assert "VersionChangeResult" in repr_str
        assert "success=True" in repr_str
        assert "upgrade" in repr_str.lower()
        assert "TEST_SKILL" in repr_str


# ============================================================================
# VersionManager Tests
# ============================================================================


class TestVersionManagerInit:
    """Tests for VersionManager initialization."""

    def test_init_default(self, tmp_path: Path) -> None:
        """Test default initialization."""
        manager = VersionManager()

        assert manager.skills_dir == Path("skills").resolve()
        assert manager.history_dir == Path(".autoflow").resolve()
        assert manager.backup_dir == Path(".autoflow/backups").resolve()

    def test_init_custom_paths(self, tmp_path: Path) -> None:
        """Test initialization with custom paths."""
        skills_dir = tmp_path / "skills"
        history_dir = tmp_path / "history"
        backup_dir = tmp_path / "backups"

        manager = VersionManager(
            skills_dir=skills_dir,
            history_dir=history_dir,
            backup_dir=backup_dir,
        )

        assert manager.skills_dir == skills_dir.resolve()
        assert manager.history_dir == history_dir.resolve()
        assert manager.backup_dir == backup_dir.resolve()

    def test_init_creates_directories(self, tmp_path: Path) -> None:
        """Test that initialization creates directories."""
        history_dir = tmp_path / "new_history"
        backup_dir = tmp_path / "new_backups"

        manager = VersionManager(
            history_dir=history_dir,
            backup_dir=backup_dir,
        )

        assert history_dir.exists()
        assert backup_dir.exists()


class TestVersionManagerVersionComparison:
    """Tests for VersionManager version comparison methods."""

    def test_compare_versions_equal(self, version_manager: VersionManager) -> None:
        """Test comparing equal versions."""
        result = version_manager.compare_versions("1.0.0", "1.0.0")
        assert result == 0

    def test_compare_versions_greater(self, version_manager: VersionManager) -> None:
        """Test comparing greater version."""
        result = version_manager.compare_versions("2.0.0", "1.0.0")
        assert result == 1

        result = version_manager.compare_versions("1.2.0", "1.1.0")
        assert result == 1

        result = version_manager.compare_versions("1.0.1", "1.0.0")
        assert result == 1

    def test_compare_versions_lesser(self, version_manager: VersionManager) -> None:
        """Test comparing lesser version."""
        result = version_manager.compare_versions("1.0.0", "2.0.0")
        assert result == -1

        result = version_manager.compare_versions("1.1.0", "1.2.0")
        assert result == -1

    def test_compare_versions_different_lengths(
        self,
        version_manager: VersionManager,
    ) -> None:
        """Test comparing versions with different lengths."""
        result = version_manager.compare_versions("1.0", "1.0.0")
        assert result == -1

        result = version_manager.compare_versions("1.0.0", "1.0")
        assert result == 1

    def test_parse_version_valid(self, version_manager: VersionManager) -> None:
        """Test parsing valid version strings."""
        result = version_manager._parse_version("1.2.3")
        assert result == (1, 2, 3)

        result = version_manager._parse_version("2.0")
        assert result == (2, 0)

    def test_parse_version_with_suffix(self, version_manager: VersionManager) -> None:
        """Test parsing version strings with suffixes."""
        result = version_manager._parse_version("1.2.3-beta")
        assert result == (1, 2, 3)

        result = version_manager._parse_version("1.2.3-rc1")
        assert result == (1, 2, 3)

    def test_parse_version_invalid(self, version_manager: VersionManager) -> None:
        """Test parsing invalid version strings."""
        result = version_manager._parse_version("invalid")
        assert result == (0,)


class TestVersionManagerHistory:
    """Tests for VersionManager history methods."""

    def test_get_version_history_empty(self, version_manager: VersionManager) -> None:
        """Test getting history for skill with no history."""
        history = version_manager.get_version_history("NONEXISTENT")

        assert history == []

    def test_get_current_version_none(self, version_manager: VersionManager) -> None:
        """Test getting current version when not installed."""
        version = version_manager.get_current_version("NONEXISTENT")

        assert version is None

    def test_add_history_entry(self, version_manager: VersionManager) -> None:
        """Test adding history entry."""
        version_manager._add_history_entry(
            skill_name="TEST_SKILL",
            version="1.0.0",
            file_path=Path("/skills/test/SKILL.md"),
            package_path=None,
            action=VersionAction.INSTALL,
        )

        history = version_manager.get_version_history("TEST_SKILL")

        assert len(history) == 1
        assert history[0].version == "1.0.0"
        assert history[0].action == VersionAction.INSTALL

    def test_get_current_version(self, version_manager: VersionManager) -> None:
        """Test getting current version after adding entries."""
        version_manager._add_history_entry(
            skill_name="TEST_SKILL",
            version="1.0.0",
            file_path=Path("/skills/test/SKILL.md"),
            package_path=None,
            action=VersionAction.INSTALL,
        )

        version = version_manager.get_current_version("TEST_SKILL")

        assert version == "1.0.0"

    def test_get_history_file(self, version_manager: VersionManager) -> None:
        """Test getting history file path."""
        history_file = version_manager._get_history_file("TEST_SKILL")

        assert history_file.name == "test_skill_history.json"
        assert history_file.parent == version_manager.history_dir


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestSkillSharingEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_export_import_roundtrip(
        self,
        packager: SkillPackager,
        importer: SkillImporter,
        temp_output_dir: Path,
        temp_skills_dir: Path,
    ) -> None:
        """Test exporting and importing a skill maintains data."""
        # Export skill
        package_path = temp_output_dir / "test-skill.tar.gz"
        packager.export_skill("TEST_SKILL", package_path)

        # Import to different location
        import_dir = temp_skills_dir / "imported"
        import_dir.mkdir()

        result = importer.import_package(
            package_path,
            import_dir,
            conflict_resolution=ImportConflictResolution.ERROR,
        )

        assert result.success
        assert "TEST_SKILL" in result.imported

        # Verify content
        imported_skill_file = import_dir / "test_skill" / "SKILL.md"
        assert imported_skill_file.exists()

        content = imported_skill_file.read_text(encoding="utf-8")
        assert "A test skill for unit testing" in content

    def test_export_import_multiple_skills(
        self,
        temp_skills_dir: Path,
        temp_output_dir: Path,
    ) -> None:
        """Test exporting and importing multiple skills."""
        # Create skills
        skill_a = """---
name: SKILL_A
version: "1.0.0"
---
Content A.
"""
        skill_b = """---
name: SKILL_B
version: "1.0.0"
---
Content B.
"""
        create_skill_file(temp_skills_dir, "skill_a", skill_a)
        create_skill_file(temp_skills_dir, "skill_b", skill_b)

        # Load and export
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        packager = SkillPackager(registry=registry)
        package_path = temp_output_dir / "collection.tar.gz"
        packager.export_skills(["SKILL_A", "SKILL_B"], package_path)

        # Import to new location
        import_dir = temp_skills_dir / "imported"
        import_dir.mkdir()

        importer = SkillImporter()
        result = importer.import_package(package_path, import_dir)

        assert len(result.imported) == 2
        assert "SKILL_A" in result.imported
        assert "SKILL_B" in result.imported

    def test_package_format_enum_values(self) -> None:
        """Test PackageFormat enum values."""
        assert PackageFormat.TAR_GZ.value == "tar.gz"
        assert PackageFormat.TAR.value == "tar"
        assert PackageFormat.DIR.value == "dir"

    def test_version_action_enum_values(self) -> None:
        """Test VersionAction enum values."""
        assert VersionAction.UPGRADE.value == "upgrade"
        assert VersionAction.DOWNGRADE.value == "downgrade"
        assert VersionAction.REINSTALL.value == "reinstall"
        assert VersionAction.INSTALL.value == "install"

    def test_import_conflict_resolution_enum_values(self) -> None:
        """Test ImportConflictResolution enum values."""
        assert ImportConflictResolution.ERROR.value == "error"
        assert ImportConflictResolution.SKIP.value == "skip"
        assert ImportConflictResolution.OVERWRITE.value == "overwrite"
        assert ImportConflictResolution.BACKUP.value == "backup"
        assert ImportConflictResolution.RENAME.value == "rename"

    def test_package_error_is_exception(self) -> None:
        """Test that PackageError is an exception."""
        error = PackageError("Test error")

        assert isinstance(error, Exception)
        assert str(error) == "Test error"

        with pytest.raises(PackageError):
            raise error
