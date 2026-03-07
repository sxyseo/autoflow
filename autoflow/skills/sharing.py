"""
Autoflow Skill Sharing Module

Provides skill packaging, export, and import functionality for sharing
skills across teams and projects. Skills can be exported as distributable
packages with version tracking and dependency management.

Usage:
    from autoflow.skills.sharing import SkillPackager, SkillPackage

    packager = SkillPackager()
    package = packager.export_skill("MY_SKILL", "my-skill-1.0.0.tar.gz")

    importer = SkillImporter()
    importer.import_package("my-skill-1.0.0.tar.gz", "/path/to/skills")
"""

from __future__ import annotations

import json
import re
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from autoflow.skills.registry import SkillDefinition, SkillMetadata, SkillRegistry


class PackageFormat(str, Enum):
    """Supported package formats for skill distribution."""

    TAR_GZ = "tar.gz"
    TAR = "tar"
    DIR = "dir"


class VersionAction(str, Enum):
    """Type of version action performed."""

    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    REINSTALL = "reinstall"
    INSTALL = "install"


class PackageError(Exception):
    """Exception raised for package-related errors."""

    pass


@dataclass
class SkillPackageMetadata:
    """
    Metadata for a skill package.

    Contains information about the package, including version, dependencies,
    and export information. This metadata is stored in the package manifest.

    Attributes:
        name: Package name (usually matches skill name)
        version: Package version string
        description: Human-readable description
        skills: List of skill names included in the package
        created_at: Timestamp when package was created
        created_by: Optional creator information
        autoflow_version: Optional Autoflow version requirement
        dependencies: List of required skill dependencies
        metadata: Additional custom metadata
    """

    name: str
    version: str
    description: str = ""
    skills: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: Optional[str] = None
    autoflow_version: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert metadata to dictionary.

        Returns:
            Dictionary representation of metadata
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "skills": self.skills,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "autoflow_version": self.autoflow_version,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillPackageMetadata:
        """
        Create metadata from dictionary.

        Args:
            data: Dictionary containing metadata

        Returns:
            SkillPackageMetadata instance
        """
        return cls(**data)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SkillPackageMetadata(name={self.name!r}, version={self.version!r})"


@dataclass
class SkillPackage:
    """
    Represents a skill package ready for distribution.

    Contains the package file path and metadata. This is returned by
    the SkillPackager after successful export.

    Attributes:
        path: Path to the package file or directory
        metadata: Package metadata
        format: Package format (tar.gz, tar, dir)
        size: Package size in bytes (if applicable)
    """

    path: Path
    metadata: SkillPackageMetadata
    format: PackageFormat
    size: int = 0

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SkillPackage(path={self.path.name!r}, "
            f"format={self.format.value}, "
            f"skills={len(self.metadata.skills)})"
        )


class SkillPackager:
    """
    Packages skills for distribution and sharing.

    The SkillPackager exports skills from a registry into distributable
    packages that can be shared across teams and projects. Packages can
    be single skills or collections of related skills.

    Packages include:
    - Skill definition files (SKILL.md)
    - Package metadata (manifest.json)
    - Optional dependency information

    Example:
        >>> packager = SkillPackager()
        >>> registry = SkillRegistry()
        >>> registry.load_skills()
        >>>
        >>> # Export single skill
        >>> package = packager.export_skill(
        ...     "MY_SKILL",
        ...     "my-skill-1.0.0.tar.gz"
        ... )
        >>>
        >>> # Export multiple skills
        >>> package = packager.export_skills(
        ...     ["SKILL_A", "SKILL_B"],
        ...     "skill-collection-1.0.0.tar.gz"
        ... )

    Attributes:
        registry: SkillRegistry to source skills from
        include_metadata: Whether to include metadata in packages
    """

    MANIFEST_FILE = "manifest.json"
    SKILLS_DIR = "skills"

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        include_metadata: bool = True,
    ):
        """
        Initialize the skill packager.

        Args:
            registry: Optional SkillRegistry to use for loading skills.
                     If None, creates a new registry.
            include_metadata: Whether to include metadata in packages
        """
        self.registry = registry or SkillRegistry()
        self.include_metadata = include_metadata
        self._errors: list[str] = []

    def export_skill(
        self,
        skill_name: str,
        output_path: Union[str, Path],
        format: Union[str, PackageFormat] = PackageFormat.TAR_GZ,
        version: Optional[str] = None,
        description: Optional[str] = None,
    ) -> SkillPackage:
        """
        Export a single skill to a distributable package.

        Args:
            skill_name: Name of the skill to export
            output_path: Path for the output package
            format: Package format (tar.gz, tar, or dir)
            version: Optional version string (defaults to skill version)
            description: Optional package description

        Returns:
            SkillPackage containing export information

        Raises:
            PackageError: If skill not found or export fails
        """
        # Ensure skill exists
        skill = self.registry.get_skill(skill_name)
        if not skill:
            raise PackageError(f"Skill '{skill_name}' not found in registry")

        if not skill.is_valid:
            raise PackageError(
                f"Skill '{skill_name}' is not valid: {', '.join(skill.errors)}"
            )

        # Use skill version if not provided
        if version is None:
            version = skill.metadata.version

        # Create package metadata
        metadata = SkillPackageMetadata(
            name=skill_name.lower(),
            version=version,
            description=description or skill.description,
            skills=[skill_name],
        )

        return self._create_package(
            skills=[skill],
            metadata=metadata,
            output_path=Path(output_path),
            format=PackageFormat(format),
        )

    def export_skills(
        self,
        skill_names: list[str],
        output_path: Union[str, Path],
        format: Union[str, PackageFormat] = PackageFormat.TAR_GZ,
        version: str = "1.0.0",
        name: Optional[str] = None,
        description: str = "",
    ) -> SkillPackage:
        """
        Export multiple skills to a distributable package.

        Args:
            skill_names: List of skill names to export
            output_path: Path for the output package
            format: Package format (tar.gz, tar, or dir)
            version: Package version string
            name: Optional package name (defaults to first skill name)
            description: Optional package description

        Returns:
            SkillPackage containing export information

        Raises:
            PackageError: If any skill not found or export fails
        """
        if not skill_names:
            raise PackageError("No skills specified for export")

        skills: list[SkillDefinition] = []
        missing_skills: list[str] = []

        for skill_name in skill_names:
            skill = self.registry.get_skill(skill_name)
            if not skill:
                missing_skills.append(skill_name)
            elif not skill.is_valid:
                raise PackageError(
                    f"Skill '{skill_name}' is not valid: {', '.join(skill.errors)}"
                )
            else:
                skills.append(skill)

        if missing_skills:
            raise PackageError(f"Skills not found: {', '.join(missing_skills)}")

        # Use first skill name as package name if not provided
        if name is None:
            name = skill_names[0].lower()

        # Create package metadata
        metadata = SkillPackageMetadata(
            name=name,
            version=version,
            description=description,
            skills=skill_names,
        )

        return self._create_package(
            skills=skills,
            metadata=metadata,
            output_path=Path(output_path),
            format=PackageFormat(format),
        )

    def _create_package(
        self,
        skills: list[SkillDefinition],
        metadata: SkillPackageMetadata,
        output_path: Path,
        format: PackageFormat,
    ) -> SkillPackage:
        """
        Create a package from skills.

        Args:
            skills: List of skill definitions to package
            metadata: Package metadata
            output_path: Path for output package
            format: Package format

        Returns:
            SkillPackage containing export information

        Raises:
            PackageError: If package creation fails
        """
        try:
            # Create temporary directory for package contents
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Create skills directory structure
                skills_dir = temp_path / self.SKILLS_DIR
                skills_dir.mkdir()

                # Copy skill files to package
                for skill in skills:
                    self._copy_skill_to_package(skill, skills_dir)

                # Write manifest
                manifest_path = temp_path / self.MANIFEST_FILE
                manifest_path.write_text(
                    json.dumps(metadata.to_dict(), indent=2),
                    encoding="utf-8",
                )

                # Create output package
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)

                if format == PackageFormat.DIR:
                    # Export as directory
                    if output_path.exists():
                        raise PackageError(f"Output path already exists: {output_path}")
                    output_path.mkdir(parents=True)
                    self._copy_directory(temp_path, output_path)
                    size = sum(f.stat().st_size for f in output_path.rglob("*") if f.is_file())

                else:
                    # Export as archive
                    self._create_archive(temp_path, output_path, format)
                    size = output_path.stat().st_size

                return SkillPackage(
                    path=output_path,
                    metadata=metadata,
                    format=format,
                    size=size,
                )

        except Exception as e:
            raise PackageError(f"Failed to create package: {e}") from e

    def _copy_skill_to_package(
        self,
        skill: SkillDefinition,
        skills_dir: Path,
    ) -> None:
        """
        Copy a skill file to the package.

        Args:
            skill: Skill definition to copy
            skills_dir: Directory to copy skill to
        """
        # Create skill directory
        skill_dir = skills_dir / skill.name.lower()
        skill_dir.mkdir(exist_ok=True)

        # Copy SKILL.md file
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            self._format_skill_content(skill),
            encoding="utf-8",
        )

        # Copy additional files from skill directory if they exist
        if skill.file_path.parent != Path("<registered>"):
            skill_source_dir = skill.file_path.parent
            for file_path in skill_source_dir.iterdir():
                if file_path.name != "SKILL.md" and file_path.is_file():
                    dest_file = skill_dir / file_path.name
                    dest_file.write_bytes(file_path.read_bytes())

    def _format_skill_content(self, skill: SkillDefinition) -> str:
        """
        Format skill content with YAML frontmatter.

        Args:
            skill: Skill definition to format

        Returns:
            Formatted skill content string
        """
        # Convert metadata to YAML
        import yaml

        metadata_dict = skill.metadata.model_dump()
        yaml_content = yaml.dump(metadata_dict, default_flow_style=False)

        return f"---\n{yaml_content}---\n\n{skill.content}"

    def _create_archive(
        self,
        source_dir: Path,
        output_path: Path,
        format: PackageFormat,
    ) -> None:
        """
        Create an archive from a directory.

        Args:
            source_dir: Directory to archive
            output_path: Path for output archive
            format: Archive format (tar.gz or tar)
        """
        mode = "w:gz" if format == PackageFormat.TAR_GZ else "w"

        with tarfile.open(output_path, mode) as tar:
            for item in source_dir.rglob("*"):
                if item.is_file():
                    arcname = item.relative_to(source_dir)
                    tar.add(item, arcname=arcname)

    def _copy_directory(self, source: Path, destination: Path) -> None:
        """
        Copy directory contents recursively.

        Args:
            source: Source directory
            destination: Destination directory
        """
        import shutil

        for item in source.rglob("*"):
            if item.is_file():
                dest_file = destination / item.relative_to(source)
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_file)

    def get_errors(self) -> list[str]:
        """
        Get any errors from packaging operations.

        Returns:
            List of error messages
        """
        return self._errors.copy()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SkillPackager(registry={self.registry})"


class ImportConflictResolution(str, Enum):
    """Strategy for resolving version conflicts during import."""

    ERROR = "error"  # Raise error on conflict
    SKIP = "skip"  # Skip conflicting skills
    OVERWRITE = "overwrite"  # Replace existing skills
    BACKUP = "backup"  # Backup existing skills before replacing
    RENAME = "rename"  # Rename imported skill to avoid conflict


@dataclass
class ImportResult:
    """
    Result of a skill import operation.

    Contains information about which skills were imported, which were
    skipped, and any conflicts that occurred.

    Attributes:
        imported: List of successfully imported skill names
        skipped: List of skipped skill names
        conflicts: List of conflicting skill names
        errors: List of error messages
        backup_paths: Map of skill name to backup file path (if backup was used)
    """

    imported: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    backup_paths: dict[str, Path] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if import was successful (no errors)."""
        return not self.errors

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ImportResult(imported={len(self.imported)}, "
            f"skipped={len(self.skipped)}, "
            f"conflicts={len(self.conflicts)}, "
            f"errors={len(self.errors)})"
        )


class SkillImporter:
    """
    Imports skill packages into a skill registry.

    The SkillImporter extracts skill packages created by SkillPackager
    and integrates them into a SkillRegistry. It handles version conflicts
    through configurable resolution strategies.

    Supported package formats:
    - tar.gz archives
    - tar archives
    - Directories

    Example:
        >>> importer = SkillImporter()
        >>> registry = SkillRegistry()
        >>>
        >>> # Import with error on conflict
        >>> result = importer.import_package(
        ...     "my-skill-1.0.0.tar.gz",
        ...     registry,
        ...     conflict_resolution=ImportConflictResolution.ERROR
        ... )
        >>>
        >>> # Import with overwrite
        >>> result = importer.import_package(
        ...     "my-skill-1.0.0.tar.gz",
        ...     registry,
        ...     conflict_resolution=ImportConflictResolution.OVERWRITE
        ... )

    Attributes:
        registry: SkillRegistry to import skills into
    """

    MANIFEST_FILE = "manifest.json"
    SKILLS_DIR = "skills"

    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
    ):
        """
        Initialize the skill importer.

        Args:
            registry: Optional SkillRegistry to import skills into.
                     If None, creates a new registry.
        """
        self.registry = registry or SkillRegistry()
        self._errors: list[str] = []

    def import_package(
        self,
        package_path: Union[str, Path],
        target_dir: Union[str, Path],
        conflict_resolution: Union[str, ImportConflictResolution] = ImportConflictResolution.ERROR,
        registry: Optional[SkillRegistry] = None,
    ) -> ImportResult:
        """
        Import a skill package into a target directory.

        Args:
            package_path: Path to the package file or directory
            target_dir: Directory to extract skills to
            conflict_resolution: Strategy for handling version conflicts
            registry: Optional SkillRegistry to load imported skills into

        Returns:
            ImportResult with details of the import operation

        Raises:
            PackageError: If package is invalid or import fails critically
        """
        package_path = Path(package_path)
        target_dir = Path(target_dir)
        conflict_resolution = ImportConflictResolution(conflict_resolution)

        # Use provided registry or default
        if registry:
            self.registry = registry

        result = ImportResult()

        try:
            # Extract package to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract based on format
                if package_path.is_file():
                    self._extract_archive(package_path, temp_path)
                elif package_path.is_dir():
                    self._copy_directory(package_path, temp_path)
                else:
                    raise PackageError(f"Package path does not exist: {package_path}")

                # Load manifest
                manifest_path = temp_path / self.MANIFEST_FILE
                if not manifest_path.exists():
                    raise PackageError(
                        f"Invalid package: missing {self.MANIFEST_FILE}"
                    )

                metadata = self._load_manifest(manifest_path)

                # Import skills
                skills_dir = temp_path / self.SKILLS_DIR
                if not skills_dir.exists():
                    raise PackageError(
                        f"Invalid package: missing {self.SKILLS_DIR} directory"
                    )

                for skill_dir in skills_dir.iterdir():
                    if skill_dir.is_dir():
                        import_result = self._import_skill(
                            skill_dir,
                            target_dir,
                            conflict_resolution,
                        )

                        if import_result == "imported":
                            result.imported.append(skill_dir.name.upper())
                        elif import_result == "skipped":
                            result.skipped.append(skill_dir.name.upper())
                        elif import_result == "conflict":
                            result.conflicts.append(skill_dir.name.upper())

        except Exception as e:
            result.errors.append(str(e))
            if isinstance(e, PackageError):
                raise

        return result

    def _import_skill(
        self,
        skill_dir: Path,
        target_dir: Path,
        conflict_resolution: ImportConflictResolution,
    ) -> str:
        """
        Import a single skill directory.

        Args:
            skill_dir: Directory containing skill files
            target_dir: Target directory for skills
            conflict_resolution: Strategy for handling conflicts

        Returns:
            "imported", "skipped", or "conflict"
        """
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return "skipped"

        # Parse skill to get name
        try:
            content = skill_file.read_text(encoding="utf-8")
            match = SkillRegistry.FRONTMATTER_PATTERN.match(content)
            if not match:
                return "skipped"

            import yaml
            yaml_content = yaml.safe_load(match.group(1))
            skill_name = yaml_content.get("name", skill_dir.name.upper())
        except Exception:
            return "skipped"

        # Determine target path
        target_skill_dir = target_dir / skill_name.lower()
        target_skill_file = target_skill_dir / "SKILL.md"

        # Check for conflict
        if target_skill_file.exists():
            if conflict_resolution == ImportConflictResolution.ERROR:
                return "conflict"
            elif conflict_resolution == ImportConflictResolution.SKIP:
                return "skipped"
            elif conflict_resolution == ImportConflictResolution.BACKUP:
                self._backup_skill(target_skill_dir, skill_name)

        # Create target directory and copy skill
        target_skill_dir.mkdir(parents=True, exist_ok=True)
        self._copy_directory(skill_dir, target_skill_dir)

        return "imported"

    def _backup_skill(self, skill_dir: Path, skill_name: str) -> None:
        """
        Backup an existing skill directory.

        Args:
            skill_dir: Directory to backup
            skill_name: Name of the skill
        """
        import shutil
        from datetime import datetime

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = skill_dir.parent / f"{skill_dir.name}_{timestamp}.bak"

        if skill_dir.exists():
            shutil.copytree(skill_dir, backup_path)

    def _extract_archive(
        self,
        archive_path: Path,
        target_dir: Path,
    ) -> None:
        """
        Extract a skill package archive.

        Args:
            archive_path: Path to the archive file
            target_dir: Directory to extract to

        Raises:
            PackageError: If extraction fails
        """
        try:
            if archive_path.suffixes == [".tar", ".gz"] or archive_path.suffix == ".tgz":
                mode = "r:gz"
            elif archive_path.suffix == ".tar":
                mode = "r"
            else:
                raise PackageError(f"Unsupported archive format: {archive_path.suffix}")

            with tarfile.open(archive_path, mode) as tar:
                tar.extractall(target_dir)

        except tarfile.TarError as e:
            raise PackageError(f"Failed to extract archive: {e}") from e

    def _load_manifest(self, manifest_path: Path) -> SkillPackageMetadata:
        """
        Load package manifest metadata.

        Args:
            manifest_path: Path to manifest.json

        Returns:
            SkillPackageMetadata instance

        Raises:
            PackageError: If manifest is invalid
        """
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return SkillPackageMetadata.from_dict(data)
        except Exception as e:
            raise PackageError(f"Invalid manifest: {e}") from e

    def _copy_directory(self, source: Path, destination: Path) -> None:
        """
        Copy directory contents recursively.

        Args:
            source: Source directory
            destination: Destination directory
        """
        import shutil

        for item in source.rglob("*"):
            if item.is_file():
                dest_file = destination / item.relative_to(source)
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_file)

    def get_errors(self) -> list[str]:
        """
        Get any errors from import operations.

        Returns:
            List of error messages
        """
        return self._errors.copy()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"SkillImporter(registry={self.registry})"


@dataclass
class VersionHistoryEntry:
    """
    Entry in the version history for a skill.

    Tracks information about each version installation including
    timestamps, file locations, and metadata.

    Attributes:
        version: Version string
        installed_at: Timestamp when version was installed
        file_path: Path to the skill file
        package_path: Path to the package file (if available)
        action: Action performed (install, upgrade, downgrade)
        metadata: Optional additional metadata about the version
    """

    version: str
    installed_at: str
    file_path: Path
    package_path: Optional[Path] = None
    action: Union[VersionAction, str] = VersionAction.INSTALL
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert entry to dictionary.

        Returns:
            Dictionary representation of the entry
        """
        return {
            "version": self.version,
            "installed_at": self.installed_at,
            "file_path": str(self.file_path),
            "package_path": str(self.package_path) if self.package_path else None,
            "action": self.action.value if isinstance(self.action, VersionAction) else self.action,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionHistoryEntry:
        """
        Create entry from dictionary.

        Args:
            data: Dictionary containing entry data

        Returns:
            VersionHistoryEntry instance
        """
        data = data.copy()
        data["file_path"] = Path(data["file_path"])
        if data.get("package_path"):
            data["package_path"] = Path(data["package_path"])
        return cls(**data)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"VersionHistoryEntry(version={self.version!r}, "
            f"action={self.action.value if isinstance(self.action, VersionAction) else self.action}, "
            f"installed_at={self.installed_at!r})"
        )


@dataclass
class VersionChangeResult:
    """
    Result of a version change operation.

    Contains information about whether the operation succeeded,
    what action was performed, and any relevant details.

    Attributes:
        success: Whether the operation succeeded
        action: Action performed (upgrade, downgrade, reinstall, install)
        previous_version: Previous version (if any)
        new_version: New version installed
        skill_name: Name of the skill
        backup_path: Path to backup file (if backup was created)
        message: Optional message describing the result
    """

    success: bool
    action: Union[VersionAction, str]
    skill_name: str
    new_version: str
    previous_version: Optional[str] = None
    backup_path: Optional[Path] = None
    message: str = ""

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"VersionChangeResult(success={self.success}, "
            f"action={self.action.value if isinstance(self.action, VersionAction) else self.action}, "
            f"skill={self.skill_name!r}, "
            f"from={self.previous_version!r}, to={self.new_version!r})"
        )


class VersionManager:
    """
    Manages version history and upgrade/downgrade operations for skills.

    The VersionManager tracks the installation history of skills, enabling
    safe upgrades and downgrades with automatic backups. It maintains a
    version history file for each skill that tracks all installed versions.

    Version comparison follows semantic versioning (semver) principles:
    - Versions are compared as major.minor.patch
    - Higher versions are considered upgrades
    - Lower versions are considered downgrades

    Example:
        >>> manager = VersionManager()
        >>>
        >>> # Upgrade a skill
        >>> result = manager.upgrade_skill(
        ...     "MY_SKILL",
        ...     "2.0.0",
        ...     package_path="my-skill-2.0.0.tar.gz"
        ... )
        >>>
        >>> # Downgrade to a previous version
        >>> result = manager.downgrade_skill(
        ...     "MY_SKILL",
        ...     "1.5.0"
        ... )
        >>>
        >>> # View version history
        >>> history = manager.get_version_history("MY_SKILL")
        >>> for entry in history:
        ...     print(f"{entry.version} - {entry.installed_at}")

    Attributes:
        skills_dir: Base directory for skills
        history_dir: Directory for version history files
        backup_dir: Directory for version backups
    """

    HISTORY_FILE = "version_history.json"
    BACKUP_SUFFIX = ".bak"

    def __init__(
        self,
        skills_dir: Optional[Union[str, Path]] = None,
        history_dir: Optional[Union[str, Path]] = None,
        backup_dir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize the version manager.

        Args:
            skills_dir: Base directory containing skills
            history_dir: Directory for version history files
            backup_dir: Directory for version backups
        """
        self.skills_dir = Path(skills_dir or "skills").resolve()
        self.history_dir = Path(history_dir or ".autoflow").resolve()
        self.backup_dir = Path(backup_dir or ".autoflow/backups").resolve()

        # Create directories if they don't exist
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._histories: dict[str, list[VersionHistoryEntry]] = {}

    def _get_history_file(self, skill_name: str) -> Path:
        """
        Get the path to the history file for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Path to the history file
        """
        return self.history_dir / f"{skill_name.lower()}_history.json"

    def _load_history(self, skill_name: str) -> list[VersionHistoryEntry]:
        """
        Load version history for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            List of history entries
        """
        if skill_name in self._histories:
            return self._histories[skill_name]

        history_file = self._get_history_file(skill_name)
        if not history_file.exists():
            self._histories[skill_name] = []
            return []

        try:
            data = json.loads(history_file.read_text(encoding="utf-8"))
            entries = [VersionHistoryEntry.from_dict(entry) for entry in data]
            self._histories[skill_name] = entries
            return entries
        except Exception:
            self._histories[skill_name] = []
            return []

    def _save_history(self, skill_name: str) -> None:
        """
        Save version history for a skill.

        Args:
            skill_name: Name of the skill
        """
        history_file = self._get_history_file(skill_name)
        entries = self._load_history(skill_name)

        data = [entry.to_dict() for entry in entries]
        history_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _add_history_entry(
        self,
        skill_name: str,
        version: str,
        file_path: Path,
        package_path: Optional[Path],
        action: Union[VersionAction, str],
    ) -> None:
        """
        Add an entry to version history.

        Args:
            skill_name: Name of the skill
            version: Version string
            file_path: Path to the skill file
            package_path: Path to the package file
            action: Action performed
        """
        history = self._load_history(skill_name)

        entry = VersionHistoryEntry(
            version=version,
            installed_at=datetime.utcnow().isoformat(),
            file_path=file_path,
            package_path=package_path,
            action=action,
        )

        history.append(entry)
        self._histories[skill_name] = history
        self._save_history(skill_name)

    def get_version_history(self, skill_name: str) -> list[VersionHistoryEntry]:
        """
        Get the version history for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            List of history entries, oldest to newest
        """
        return self._load_history(skill_name).copy()

    def get_current_version(self, skill_name: str) -> Optional[str]:
        """
        Get the current installed version of a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            Current version string, or None if not found
        """
        history = self._load_history(skill_name)
        if not history:
            return None

        # Get the most recent entry
        return history[-1].version if history else None

    def compare_versions(self, version1: str, version2: str) -> int:
        """
        Compare two version strings.

        Args:
            version1: First version string
            version2: Second version string

        Returns:
            -1 if version1 < version2
            0 if version1 == version2
            1 if version1 > version2
        """
        # Parse version strings
        v1_parts = self._parse_version(version1)
        v2_parts = self._parse_version(version2)

        # Compare parts
        for v1, v2 in zip(v1_parts, v2_parts):
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1

        # If all parts equal so far, check length
        if len(v1_parts) < len(v2_parts):
            return -1
        elif len(v1_parts) > len(v2_parts):
            return 1

        return 0

    def _parse_version(self, version: str) -> tuple[int, ...]:
        """
        Parse a version string into numeric parts.

        Args:
            version: Version string (e.g., "1.2.3")

        Returns:
            Tuple of integer version parts
        """
        # Remove any non-numeric suffixes (like -beta, -rc1, etc.)
        match = re.match(r"^(\d+(?:\.\d+)*)", version)
        if not match:
            return (0,)

        parts = match.group(1).split(".")
        return tuple(int(p) for p in parts)

    def upgrade_skill(
        self,
        skill_name: str,
        new_version: str,
        package_path: Union[str, Path],
        create_backup: bool = True,
    ) -> VersionChangeResult:
        """
        Upgrade a skill to a new version.

        Args:
            skill_name: Name of the skill to upgrade
            new_version: New version to install
            package_path: Path to the package file
            create_backup: Whether to backup the current version

        Returns:
            VersionChangeResult with operation details

        Raises:
            PackageError: If upgrade fails
        """
        current_version = self.get_current_version(skill_name)

        # Check if this is actually an upgrade
        if current_version:
            comparison = self.compare_versions(new_version, current_version)
            if comparison < 0:
                return VersionChangeResult(
                    success=False,
                    action=VersionAction.UPGRADE,
                    skill_name=skill_name,
                    new_version=new_version,
                    previous_version=current_version,
                    message=f"Cannot upgrade: new version {new_version} is older than current {current_version}",
                )
            elif comparison == 0:
                return VersionChangeResult(
                    success=False,
                    action=VersionAction.UPGRADE,
                    skill_name=skill_name,
                    new_version=new_version,
                    previous_version=current_version,
                    message=f"Already at version {new_version}",
                )

        # Backup current version if requested
        backup_path = None
        if create_backup and current_version:
            backup_path = self._backup_skill(skill_name, current_version)

        # Import new version
        importer = SkillImporter()
        result = importer.import_package(
            package_path,
            self.skills_dir,
            conflict_resolution=ImportConflictResolution.OVERWRITE,
        )

        if not result.success or skill_name not in result.imported:
            return VersionChangeResult(
                success=False,
                action=VersionAction.UPGRADE,
                skill_name=skill_name,
                new_version=new_version,
                previous_version=current_version,
                message=f"Failed to import package: {result.errors}",
            )

        # Record in history
        skill_dir = self.skills_dir / skill_name.lower()
        skill_file = skill_dir / "SKILL.md"
        self._add_history_entry(
            skill_name=skill_name,
            version=new_version,
            file_path=skill_file,
            package_path=Path(package_path),
            action=VersionAction.UPGRADE,
        )

        return VersionChangeResult(
            success=True,
            action=VersionAction.UPGRADE,
            skill_name=skill_name,
            new_version=new_version,
            previous_version=current_version,
            backup_path=backup_path,
            message=f"Successfully upgraded from {current_version} to {new_version}",
        )

    def downgrade_skill(
        self,
        skill_name: str,
        target_version: str,
        create_backup: bool = True,
    ) -> VersionChangeResult:
        """
        Downgrade a skill to a previous version.

        Args:
            skill_name: Name of the skill to downgrade
            target_version: Version to downgrade to
            create_backup: Whether to backup the current version

        Returns:
            VersionChangeResult with operation details

        Raises:
            PackageError: If downgrade fails
        """
        current_version = self.get_current_version(skill_name)

        if not current_version:
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=None,
                message=f"Skill {skill_name} is not installed",
            )

        # Check if this is actually a downgrade
        comparison = self.compare_versions(target_version, current_version)
        if comparison > 0:
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=current_version,
                message=f"Cannot downgrade: target version {target_version} is newer than current {current_version}",
            )
        elif comparison == 0:
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=current_version,
                message=f"Already at version {target_version}",
            )

        # Find target version in history
        history = self._load_history(skill_name)
        target_entry = None
        for entry in history:
            if entry.version == target_version:
                target_entry = entry
                break

        if not target_entry:
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=current_version,
                message=f"Version {target_version} not found in history",
            )

        # Check if package file exists
        if not target_entry.package_path or not target_entry.package_path.exists():
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=current_version,
                message=f"Package file for version {target_version} not found",
            )

        # Backup current version if requested
        backup_path = None
        if create_backup:
            backup_path = self._backup_skill(skill_name, current_version)

        # Import target version
        importer = SkillImporter()
        result = importer.import_package(
            target_entry.package_path,
            self.skills_dir,
            conflict_resolution=ImportConflictResolution.OVERWRITE,
        )

        if not result.success or skill_name not in result.imported:
            return VersionChangeResult(
                success=False,
                action=VersionAction.DOWNGRADE,
                skill_name=skill_name,
                new_version=target_version,
                previous_version=current_version,
                message=f"Failed to import package: {result.errors}",
            )

        # Record in history
        skill_dir = self.skills_dir / skill_name.lower()
        skill_file = skill_dir / "SKILL.md"
        self._add_history_entry(
            skill_name=skill_name,
            version=target_version,
            file_path=skill_file,
            package_path=target_entry.package_path,
            action=VersionAction.DOWNGRADE,
        )

        return VersionChangeResult(
            success=True,
            action=VersionAction.DOWNGRADE,
            skill_name=skill_name,
            new_version=target_version,
            previous_version=current_version,
            backup_path=backup_path,
            message=f"Successfully downgraded from {current_version} to {target_version}",
        )

    def _backup_skill(self, skill_name: str, version: str) -> Optional[Path]:
        """
        Create a backup of a skill.

        Args:
            skill_name: Name of the skill
            version: Version being backed up

        Returns:
            Path to backup file, or None if backup failed
        """
        import shutil

        skill_dir = self.skills_dir / skill_name.lower()
        if not skill_dir.exists():
            return None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{skill_name.lower()}_{version}_{timestamp}{self.BACKUP_SUFFIX}"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copytree(skill_dir, backup_path)
            return backup_path
        except Exception:
            return None

    def restore_backup(self, skill_name: str, backup_path: Union[str, Path]) -> VersionChangeResult:
        """
        Restore a skill from a backup.

        Args:
            skill_name: Name of the skill
            backup_path: Path to the backup directory

        Returns:
            VersionChangeResult with operation details

        Raises:
            PackageError: If restore fails
        """
        import shutil

        backup_path = Path(backup_path)
        if not backup_path.exists():
            return VersionChangeResult(
                success=False,
                action=VersionAction.REINSTALL,
                skill_name=skill_name,
                new_version="unknown",
                previous_version=self.get_current_version(skill_name),
                message=f"Backup path does not exist: {backup_path}",
            )

        # Get current version
        current_version = self.get_current_version(skill_name)

        # Restore from backup
        skill_dir = self.skills_dir / skill_name.lower()

        try:
            # Remove existing skill directory
            if skill_dir.exists():
                shutil.rmtree(skill_dir)

            # Copy from backup
            shutil.copytree(backup_path, skill_dir)

            # Extract version from backup name or skill file
            version = self._extract_version_from_backup(backup_path, skill_name)

            # Record in history
            skill_file = skill_dir / "SKILL.md"
            self._add_history_entry(
                skill_name=skill_name,
                version=version,
                file_path=skill_file,
                package_path=None,
                action=VersionAction.REINSTALL,
            )

            return VersionChangeResult(
                success=True,
                action=VersionAction.REINSTALL,
                skill_name=skill_name,
                new_version=version,
                previous_version=current_version,
                message=f"Successfully restored from backup",
            )

        except Exception as e:
            return VersionChangeResult(
                success=False,
                action=VersionAction.REINSTALL,
                skill_name=skill_name,
                new_version="unknown",
                previous_version=current_version,
                message=f"Failed to restore backup: {e}",
            )

    def _extract_version_from_backup(self, backup_path: Path, skill_name: str) -> str:
        """
        Extract version from a backup directory name or skill file.

        Args:
            backup_path: Path to the backup directory
            skill_name: Name of the skill

        Returns:
            Version string
        """
        # Try to extract from backup name first
        # Format: skillname_version_timestamp.bak
        match = re.match(rf"{re.escape(skill_name.lower())}_(.+?)_\d+{{8}}_\d+{{6}}", backup_path.stem)
        if match:
            return match.group(1)

        # Try to read from skill file
        skill_file = backup_path / "SKILL.md"
        if skill_file.exists():
            try:
                content = skill_file.read_text(encoding="utf-8")
                match = SkillRegistry.FRONTMATTER_PATTERN.match(content)
                if match:
                    import yaml
                    metadata = yaml.safe_load(match.group(1))
                    if isinstance(metadata, dict) and "version" in metadata:
                        return str(metadata["version"])
            except Exception:
                pass

        return "unknown"

    def list_backups(self, skill_name: Optional[str] = None) -> list[Path]:
        """
        List available backups.

        Args:
            skill_name: Optional skill name to filter by

        Returns:
            List of backup paths
        """
        if not self.backup_dir.exists():
            return []

        backups = []
        for backup in self.backup_dir.glob(f"*{self.BACKUP_SUFFIX}"):
            if backup.is_dir():
                if skill_name is None or backup.name.startswith(skill_name.lower()):
                    backups.append(backup)

        return sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"VersionManager(skills_dir={self.skills_dir}, "
            f"history_dir={self.history_dir}, "
            f"backup_dir={self.backup_dir})"
        )


def create_packager(
    registry: Optional[SkillRegistry] = None,
    include_metadata: bool = True,
) -> SkillPackager:
    """
    Factory function to create a skill packager.

    Args:
        registry: Optional SkillRegistry to use
        include_metadata: Whether to include metadata in packages

    Returns:
        Configured SkillPackager instance

    Example:
        >>> from autoflow.skills.registry import create_registry
        >>> registry = create_registry()
        >>> packager = create_packager(registry)
        >>> package = packager.export_skill("MY_SKILL", "output.tar.gz")
    """
    return SkillPackager(registry=registry, include_metadata=include_metadata)


def create_importer(
    registry: Optional[SkillRegistry] = None,
) -> SkillImporter:
    """
    Factory function to create a skill importer.

    Args:
        registry: Optional SkillRegistry to use

    Returns:
        Configured SkillImporter instance

    Example:
        >>> from autoflow.skills.registry import create_registry
        >>> registry = create_registry()
        >>> importer = create_importer(registry)
        >>> result = importer.import_package("my-skill-1.0.0.tar.gz", "skills")
    """
    return SkillImporter(registry=registry)
