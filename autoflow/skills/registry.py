"""
Autoflow Skill Registry Module

Provides skill loading, validation, and registration for OpenClaw-compatible
skill definitions. Skills are defined in SKILL.md files with YAML frontmatter.

Usage:
    from autoflow.skills.registry import SkillRegistry, SkillDefinition

    registry = SkillRegistry()
    registry.load_skills()

    skill = registry.get_skill("IMPLEMENTER")
    print(skill.description)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class SkillStatus(StrEnum):
    """Status of a skill in the registry."""

    LOADED = "loaded"
    INVALID = "invalid"
    DISABLED = "disabled"


class SkillMetadata(BaseModel):
    """
    Metadata parsed from SKILL.md YAML frontmatter.

    This is the structured data extracted from the YAML header
    at the top of a skill definition file.

    Attributes:
        name: Unique skill identifier (e.g., "IMPLEMENTER")
        description: Human-readable description of the skill
        version: Optional version string
        triggers: Events that should trigger this skill
        inputs: Expected input parameters
        outputs: Expected output values
        agents: Compatible agent types (e.g., ["claude-code", "codex"])
        enabled: Whether this skill is active
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    triggers: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=lambda: ["claude-code"])
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate skill name format."""
        if not v:
            raise ValueError("Skill name cannot be empty")
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(f"Skill name must be UPPER_SNAKE_CASE: {v}")
        return v


@dataclass
class SkillDefinition:
    """
    Complete skill definition including content.

    Represents a fully loaded skill with both metadata and
    the markdown content that defines the skill's behavior.

    Attributes:
        metadata: Parsed YAML frontmatter
        content: Markdown content after frontmatter
        file_path: Path to the SKILL.md file
        status: Current status of the skill
        errors: Validation errors if any
    """

    metadata: SkillMetadata
    content: str
    file_path: Path
    status: SkillStatus = SkillStatus.LOADED
    errors: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """Get skill name from metadata."""
        return self.metadata.name

    @property
    def description(self) -> str:
        """Get skill description from metadata."""
        return self.metadata.description

    @property
    def is_valid(self) -> bool:
        """Check if skill is valid and usable."""
        return self.status == SkillStatus.LOADED and not self.errors

    def get_content_for_agent(self, agent_type: str) -> str:
        """
        Get skill content formatted for a specific agent type.

        Args:
            agent_type: The agent type to format for

        Returns:
            Formatted content string
        """
        if agent_type not in self.metadata.agents:
            raise ValueError(
                f"Agent type '{agent_type}' not compatible with skill '{self.name}'. "
                f"Compatible agents: {self.metadata.agents}"
            )
        return self.content

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SkillDefinition(name={self.name!r}, "
            f"status={self.status.value}, file={self.file_path.name})"
        )


class SkillRegistryError(Exception):
    """Exception raised for skill registry errors."""

    pass


class SkillRegistry:
    """
    Registry for loading and managing skill definitions.

    The SkillRegistry discovers SKILL.md files in configured directories,
    parses their YAML frontmatter, validates the definitions, and provides
    access to skills by name.

    Directories are searched in order, with later directories potentially
    overriding skills from earlier ones.

    Example:
        >>> registry = SkillRegistry()
        >>> registry.add_skills_dir(Path("skills"))
        >>> registry.load_skills()
        >>> skill = registry.get_skill("IMPLEMENTER")
        >>> print(skill.description)
        'Executes code implementation tasks'

    Attributes:
        skills: Dictionary of loaded skills by name
        skills_dirs: List of directories to search for skills
    """

    # Pattern to match YAML frontmatter
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

    def __init__(
        self,
        skills_dirs: list[str | Path] | None = None,
        auto_load: bool = False,
    ):
        """
        Initialize the skill registry.

        Args:
            skills_dirs: Optional list of directories to search for skills
            auto_load: Whether to automatically load skills on init
        """
        self._skills: dict[str, SkillDefinition] = {}
        self._skills_dirs: list[Path] = []
        self._errors: list[str] = []

        if skills_dirs:
            for dir_path in skills_dirs:
                self.add_skills_dir(dir_path)

        if auto_load:
            self.load_skills()

    def add_skills_dir(self, dir_path: str | Path) -> None:
        """
        Add a directory to search for skills.

        Args:
            dir_path: Path to directory containing skill subdirectories

        Raises:
            SkillRegistryError: If directory doesn't exist
        """
        path = Path(dir_path).resolve()
        if not path.exists():
            # Create directory if it doesn't exist (for flexibility)
            path.mkdir(parents=True, exist_ok=True)
        self._skills_dirs.append(path)

    def load_skills(self, reload: bool = False) -> int:
        """
        Load all skills from configured directories.

        Args:
            reload: If True, clear existing skills before loading

        Returns:
            Number of successfully loaded skills

        Raises:
            SkillRegistryError: If no skills directories are configured
        """
        if reload:
            self._skills.clear()
            self._errors.clear()

        if not self._skills_dirs:
            # Default to 'skills' directory if none configured
            default_dir = Path("skills").resolve()
            if default_dir.exists():
                self.add_skills_dir(default_dir)

        loaded_count = 0

        for skills_dir in self._skills_dirs:
            count = self._load_skills_from_dir(skills_dir)
            loaded_count += count

        return loaded_count

    def _load_skills_from_dir(self, skills_dir: Path) -> int:
        """
        Load all skills from a specific directory.

        Args:
            skills_dir: Directory to search for SKILL.md files

        Returns:
            Number of successfully loaded skills from this directory
        """
        loaded_count = 0

        if not skills_dir.exists():
            return 0

        # Look for SKILL.md files in subdirectories
        for skill_file in skills_dir.glob("*/SKILL.md"):
            try:
                skill = self._load_skill_file(skill_file)
                if skill and skill.is_valid:
                    self._skills[skill.name] = skill
                    loaded_count += 1
                elif skill:
                    # Store invalid skills for debugging
                    self._skills[skill.name] = skill
                    self._errors.append(
                        f"Invalid skill '{skill.name}': {', '.join(skill.errors)}"
                    )
            except Exception as e:
                self._errors.append(f"Failed to load skill from {skill_file}: {e}")

        # Also check for SKILL.md files directly in the directory
        for skill_file in skills_dir.glob("SKILL.md"):
            try:
                skill = self._load_skill_file(skill_file)
                if skill and skill.is_valid:
                    self._skills[skill.name] = skill
                    loaded_count += 1
            except Exception as e:
                self._errors.append(f"Failed to load skill from {skill_file}: {e}")

        return loaded_count

    def _load_skill_file(self, file_path: Path) -> SkillDefinition | None:
        """
        Load and parse a single SKILL.md file.

        Args:
            file_path: Path to the SKILL.md file

        Returns:
            SkillDefinition if valid, None if file couldn't be read

        Raises:
            SkillRegistryError: If file parsing fails
        """
        if not file_path.exists():
            return None

        content = file_path.read_text(encoding="utf-8")

        # Parse frontmatter
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            return SkillDefinition(
                metadata=SkillMetadata(name="UNKNOWN"),
                content=content,
                file_path=file_path,
                status=SkillStatus.INVALID,
                errors=["No valid YAML frontmatter found"],
            )

        yaml_content, markdown_content = match.groups()

        try:
            metadata_dict = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return SkillDefinition(
                metadata=SkillMetadata(name="UNKNOWN"),
                content=content,
                file_path=file_path,
                status=SkillStatus.INVALID,
                errors=[f"Invalid YAML frontmatter: {e}"],
            )

        if not isinstance(metadata_dict, dict):
            return SkillDefinition(
                metadata=SkillMetadata(name="UNKNOWN"),
                content=content,
                file_path=file_path,
                status=SkillStatus.INVALID,
                errors=["Frontmatter must be a YAML mapping"],
            )

        # Validate metadata
        errors: list[str] = []

        # Ensure name is present
        if "name" not in metadata_dict:
            errors.append("Skill name is required in frontmatter")

        try:
            metadata = SkillMetadata(**metadata_dict)
        except Exception as e:
            # If we have a name, use it; otherwise UNKNOWN
            name = metadata_dict.get("name", "UNKNOWN")
            metadata = SkillMetadata(name=name if isinstance(name, str) else "UNKNOWN")
            errors.append(f"Invalid metadata: {e}")

        status = SkillStatus.LOADED if not errors else SkillStatus.INVALID

        return SkillDefinition(
            metadata=metadata,
            content=markdown_content.strip(),
            file_path=file_path,
            status=status,
            errors=errors,
        )

    def get_skill(self, name: str) -> SkillDefinition | None:
        """
        Get a skill by name.

        Args:
            name: Skill name to look up

        Returns:
            SkillDefinition if found, None otherwise
        """
        return self._skills.get(name)

    def get_skills_for_agent(self, agent_type: str) -> list[SkillDefinition]:
        """
        Get all skills compatible with a specific agent type.

        Args:
            agent_type: Agent type to filter by (e.g., "claude-code")

        Returns:
            List of compatible skill definitions
        """
        return [
            skill
            for skill in self._skills.values()
            if skill.is_valid and agent_type in skill.metadata.agents
        ]

    def get_skills_for_trigger(self, trigger: str) -> list[SkillDefinition]:
        """
        Get all skills that should be triggered by an event.

        Args:
            trigger: Trigger event to filter by

        Returns:
            List of skills that respond to this trigger
        """
        return [
            skill
            for skill in self._skills.values()
            if skill.is_valid and trigger in skill.metadata.triggers
        ]

    def list_skills(self, include_invalid: bool = False) -> list[str]:
        """
        List all registered skill names.

        Args:
            include_invalid: Whether to include invalid skills

        Returns:
            List of skill names
        """
        if include_invalid:
            return list(self._skills.keys())
        return [name for name, skill in self._skills.items() if skill.is_valid]

    def get_all_skills(self) -> list[SkillDefinition]:
        """
        Get all loaded skill definitions.

        Returns:
            List of all skill definitions
        """
        return list(self._skills.values())

    def get_errors(self) -> list[str]:
        """
        Get all errors from loading skills.

        Returns:
            List of error messages
        """
        return self._errors.copy()

    def has_skill(self, name: str) -> bool:
        """
        Check if a skill is registered and valid.

        Args:
            name: Skill name to check

        Returns:
            True if skill exists and is valid
        """
        skill = self._skills.get(name)
        return skill is not None and skill.is_valid

    def register_skill(
        self,
        metadata: SkillMetadata | dict[str, Any],
        content: str,
    ) -> SkillDefinition:
        """
        Manually register a skill definition.

        Args:
            metadata: Skill metadata (SkillMetadata object or dict)
            content: Skill markdown content

        Returns:
            The registered SkillDefinition

        Raises:
            SkillRegistryError: If metadata is invalid
        """
        if isinstance(metadata, dict):
            try:
                metadata = SkillMetadata(**metadata)
            except Exception as e:
                raise SkillRegistryError(f"Invalid metadata: {e}") from e

        skill = SkillDefinition(
            metadata=metadata,
            content=content,
            file_path=Path("<registered>"),
            status=SkillStatus.LOADED,
        )

        self._skills[skill.name] = skill
        return skill

    def unregister_skill(self, name: str) -> bool:
        """
        Remove a skill from the registry.

        Args:
            name: Name of skill to remove

        Returns:
            True if skill was removed, False if not found
        """
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered skills."""
        self._skills.clear()
        self._errors.clear()

    def __len__(self) -> int:
        """Return number of registered skills."""
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        """Check if a skill is registered."""
        return name in self._skills

    def __iter__(self):
        """Iterate over skill names."""
        return iter(self._skills)

    def __repr__(self) -> str:
        """Return string representation."""
        valid_count = sum(1 for s in self._skills.values() if s.is_valid)
        return (
            f"SkillRegistry(skills={len(self._skills)}, "
            f"valid={valid_count}, dirs={len(self._skills_dirs)})"
        )


def create_registry(
    skills_dirs: list[str | Path] | None = None,
    auto_load: bool = True,
) -> SkillRegistry:
    """
    Factory function to create and optionally load a skill registry.

    Args:
        skills_dirs: Optional list of directories to search
        auto_load: Whether to automatically load skills

    Returns:
        Configured SkillRegistry instance

    Example:
        >>> registry = create_registry(["skills", "custom_skills"])
        >>> print(registry.list_skills())
        ['IMPLEMENTER', 'REVIEWER']
    """
    return SkillRegistry(skills_dirs=skills_dirs, auto_load=auto_load)
