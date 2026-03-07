"""
Unit Tests for Skill Registry

Tests the SkillRegistry, SkillMetadata, and SkillDefinition classes
for loading, validating, and managing skill definitions.

These tests use temporary directories and mock files to avoid
requiring actual skill files in the test environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.skills import (
    SkillDefinition,
    SkillMetadata,
    SkillRegistry,
    SkillRegistryError,
    SkillStatus,
    create_registry,
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
def valid_skill_content() -> str:
    """Return valid skill file content with frontmatter."""
    return """---
name: TEST_SKILL
description: A test skill for unit testing
version: "1.0.0"
triggers:
  - test_trigger
  - another_trigger
inputs:
  - input1
  - input2
outputs:
  - output1
agents:
  - claude-code
  - codex
enabled: true
---

## Role

This is a test skill for unit testing.

## Workflow

1. Step one
2. Step two
3. Step three
"""


@pytest.fixture
def minimal_skill_content() -> str:
    """Return minimal valid skill file content."""
    return """---
name: MINIMAL_SKILL
---

Minimal content.
"""


@pytest.fixture
def invalid_yaml_skill_content() -> str:
    """Return skill file content with invalid YAML."""
    return """---
name: INVALID_SKILL
description: [invalid yaml structure
---

Content here.
"""


@pytest.fixture
def no_frontmatter_content() -> str:
    """Return skill file content without frontmatter."""
    return """# Just Markdown

No YAML frontmatter here.
"""


@pytest.fixture
def registry() -> SkillRegistry:
    """Create a basic SkillRegistry instance for testing."""
    return SkillRegistry()


# ============================================================================
# Helper Functions
# ============================================================================


def create_skill_file(
    skills_dir: Path,
    skill_name: str,
    content: str,
    in_subdir: bool = True,
) -> Path:
    """Create a skill file in the skills directory."""
    if in_subdir:
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
    else:
        skill_file = skills_dir / "SKILL.md"

    skill_file.write_text(content, encoding="utf-8")
    return skill_file


# ============================================================================
# SkillMetadata Tests
# ============================================================================


class TestSkillMetadata:
    """Tests for SkillMetadata model."""

    def test_metadata_init_minimal(self) -> None:
        """Test metadata initialization with minimal fields."""
        metadata = SkillMetadata(name="TEST")

        assert metadata.name == "TEST"
        assert metadata.description == ""
        assert metadata.version == "1.0.0"
        assert metadata.triggers == []
        assert metadata.inputs == []
        assert metadata.outputs == []
        assert metadata.agents == ["claude-code"]
        assert metadata.enabled is True

    def test_metadata_init_full(self) -> None:
        """Test metadata initialization with all fields."""
        metadata = SkillMetadata(
            name="FULL_SKILL",
            description="Full skill description",
            version="2.0.0",
            triggers=["trigger1", "trigger2"],
            inputs=["input1"],
            outputs=["output1"],
            agents=["claude-code", "codex"],
            enabled=False,
        )

        assert metadata.name == "FULL_SKILL"
        assert metadata.description == "Full skill description"
        assert metadata.version == "2.0.0"
        assert metadata.triggers == ["trigger1", "trigger2"]
        assert metadata.inputs == ["input1"]
        assert metadata.outputs == ["output1"]
        assert metadata.agents == ["claude-code", "codex"]
        assert metadata.enabled is False

    def test_metadata_validate_name_empty(self) -> None:
        """Test that empty name raises validation error."""
        with pytest.raises(ValueError) as exc_info:
            SkillMetadata(name="")

        assert "cannot be empty" in str(exc_info.value)

    def test_metadata_validate_name_lowercase(self) -> None:
        """Test that lowercase name raises validation error."""
        with pytest.raises(ValueError) as exc_info:
            SkillMetadata(name="lowercase")

        assert "UPPER_SNAKE_CASE" in str(exc_info.value)

    def test_metadata_validate_name_special_chars(self) -> None:
        """Test that special characters in name raises validation error."""
        with pytest.raises(ValueError):
            SkillMetadata(name="INVALID-NAME")

    def test_metadata_validate_name_valid_formats(self) -> None:
        """Test valid name formats."""
        valid_names = [
            "TEST",
            "TEST_SKILL",
            "TEST_SKILL_123",
            "A",
            "SKILL_V2",
        ]

        for name in valid_names:
            metadata = SkillMetadata(name=name)
            assert metadata.name == name


# ============================================================================
# SkillDefinition Tests
# ============================================================================


class TestSkillDefinition:
    """Tests for SkillDefinition dataclass."""

    def test_definition_init(self) -> None:
        """Test skill definition initialization."""
        metadata = SkillMetadata(name="TEST_SKILL")
        content = "# Test Content"
        file_path = Path("/test/SKILL.md")

        definition = SkillDefinition(
            metadata=metadata,
            content=content,
            file_path=file_path,
        )

        assert definition.metadata == metadata
        assert definition.content == content
        assert definition.file_path == file_path
        assert definition.status == SkillStatus.LOADED
        assert definition.errors == []

    def test_definition_name_property(self) -> None:
        """Test name property returns metadata name."""
        metadata = SkillMetadata(name="MY_SKILL")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/test/SKILL.md"),
        )

        assert definition.name == "MY_SKILL"

    def test_definition_description_property(self) -> None:
        """Test description property returns metadata description."""
        metadata = SkillMetadata(name="TEST", description="My description")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/test/SKILL.md"),
        )

        assert definition.description == "My description"

    def test_definition_is_valid_true(self) -> None:
        """Test is_valid returns True for loaded skill without errors."""
        metadata = SkillMetadata(name="TEST")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/test/SKILL.md"),
            status=SkillStatus.LOADED,
            errors=[],
        )

        assert definition.is_valid is True

    def test_definition_is_valid_false_invalid_status(self) -> None:
        """Test is_valid returns False for invalid status."""
        metadata = SkillMetadata(name="TEST")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/test/SKILL.md"),
            status=SkillStatus.INVALID,
            errors=[],
        )

        assert definition.is_valid is False

    def test_definition_is_valid_false_with_errors(self) -> None:
        """Test is_valid returns False when errors exist."""
        metadata = SkillMetadata(name="TEST")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/test/SKILL.md"),
            status=SkillStatus.LOADED,
            errors=["Some error"],
        )

        assert definition.is_valid is False

    def test_definition_get_content_for_agent_compatible(self) -> None:
        """Test get_content_for_agent with compatible agent."""
        metadata = SkillMetadata(name="TEST", agents=["claude-code", "codex"])
        definition = SkillDefinition(
            metadata=metadata,
            content="Skill content",
            file_path=Path("/test/SKILL.md"),
        )

        content = definition.get_content_for_agent("claude-code")
        assert content == "Skill content"

    def test_definition_get_content_for_agent_incompatible(self) -> None:
        """Test get_content_for_agent raises for incompatible agent."""
        metadata = SkillMetadata(name="TEST", agents=["claude-code"])
        definition = SkillDefinition(
            metadata=metadata,
            content="Skill content",
            file_path=Path("/test/SKILL.md"),
        )

        with pytest.raises(ValueError) as exc_info:
            definition.get_content_for_agent("codex")

        assert "not compatible" in str(exc_info.value)

    def test_definition_repr(self) -> None:
        """Test string representation."""
        metadata = SkillMetadata(name="TEST_SKILL")
        definition = SkillDefinition(
            metadata=metadata,
            content="content",
            file_path=Path("/skills/TEST_SKILL/SKILL.md"),
            status=SkillStatus.LOADED,
        )

        repr_str = repr(definition)
        assert "TEST_SKILL" in repr_str
        assert "loaded" in repr_str
        assert "SKILL.md" in repr_str


# ============================================================================
# SkillRegistry Init Tests
# ============================================================================


class TestSkillRegistryInit:
    """Tests for SkillRegistry initialization."""

    def test_init_empty(self) -> None:
        """Test empty registry initialization."""
        registry = SkillRegistry()

        assert len(registry) == 0
        assert registry.list_skills() == []
        assert registry.get_errors() == []

    def test_init_with_skills_dir(self, temp_skills_dir: Path) -> None:
        """Test initialization with skills directory."""
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])

        assert len(registry._skills_dirs) == 1
        assert temp_skills_dir in registry._skills_dirs

    def test_init_with_multiple_dirs(self, temp_skills_dir: Path, tmp_path: Path) -> None:
        """Test initialization with multiple directories."""
        second_dir = tmp_path / "skills2"
        second_dir.mkdir()

        registry = SkillRegistry(skills_dirs=[temp_skills_dir, second_dir])

        assert len(registry._skills_dirs) == 2

    def test_init_auto_load(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test auto_load on initialization."""
        create_skill_file(temp_skills_dir, "TEST_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir], auto_load=True)

        assert len(registry) == 1
        assert registry.has_skill("TEST_SKILL")

    def test_init_creates_missing_dir(self, tmp_path: Path) -> None:
        """Test that missing directories are created."""
        missing_dir = tmp_path / "new_skills"

        registry = SkillRegistry(skills_dirs=[missing_dir])

        assert missing_dir.exists()


# ============================================================================
# SkillRegistry Add Skills Dir Tests
# ============================================================================


class TestSkillRegistryAddSkillsDir:
    """Tests for SkillRegistry.add_skills_dir method."""

    def test_add_skills_dir_existing(self, temp_skills_dir: Path) -> None:
        """Test adding an existing directory."""
        registry = SkillRegistry()
        registry.add_skills_dir(temp_skills_dir)

        assert temp_skills_dir in registry._skills_dirs

    def test_add_skills_dir_creates_missing(self, tmp_path: Path) -> None:
        """Test that adding missing directory creates it."""
        registry = SkillRegistry()
        missing_dir = tmp_path / "auto_created"

        registry.add_skills_dir(missing_dir)

        assert missing_dir.exists()
        assert missing_dir in registry._skills_dirs

    def test_add_skills_dir_string_path(self, temp_skills_dir: Path) -> None:
        """Test adding directory as string path."""
        registry = SkillRegistry()
        registry.add_skills_dir(str(temp_skills_dir))

        assert temp_skills_dir in registry._skills_dirs


# ============================================================================
# SkillRegistry Load Skills Tests
# ============================================================================


class TestSkillRegistryLoadSkills:
    """Tests for SkillRegistry.load_skills method."""

    def test_load_skills_from_subdirectory(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test loading skills from subdirectories."""
        create_skill_file(temp_skills_dir, "TEST_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 1
        assert registry.has_skill("TEST_SKILL")

    def test_load_skills_from_root(
        self,
        temp_skills_dir: Path,
        minimal_skill_content: str,
    ) -> None:
        """Test loading skills from root directory."""
        create_skill_file(temp_skills_dir, "ROOT_SKILL", minimal_skill_content, in_subdir=False)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 1
        assert registry.has_skill("ROOT_SKILL")

    def test_load_multiple_skills(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
        minimal_skill_content: str,
    ) -> None:
        """Test loading multiple skills."""
        create_skill_file(temp_skills_dir, "SKILL_ONE", valid_skill_content)
        create_skill_file(temp_skills_dir, "SKILL_TWO", minimal_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 2
        assert registry.has_skill("SKILL_ONE")
        assert registry.has_skill("SKILL_TWO")

    def test_load_skills_reload(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test reload parameter clears existing skills."""
        create_skill_file(temp_skills_dir, "FIRST_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()
        assert len(registry) == 1

        # Manually add another skill
        registry.register_skill(
            {"name": "MANUAL_SKILL"},
            "Manual content",
        )
        assert len(registry) == 2

        # Reload should clear and re-scan
        count = registry.load_skills(reload=True)
        assert count == 1
        assert registry.has_skill("FIRST_SKILL")
        assert not registry.has_skill("MANUAL_SKILL")

    def test_load_skills_default_dir(
        self,
        tmp_path: Path,
        valid_skill_content: str,
    ) -> None:
        """Test loading from default 'skills' directory."""
        # Create skills directory in current working directory simulation
        default_skills = tmp_path / "skills"
        default_skills.mkdir()
        create_skill_file(default_skills, "DEFAULT_SKILL", valid_skill_content)

        registry = SkillRegistry()
        with patch("autoflow.skills.registry.Path.resolve") as mock_resolve:
            mock_resolve.return_value = default_skills
            count = registry.load_skills()

        assert count == 1

    def test_load_skills_invalid_yaml(
        self,
        temp_skills_dir: Path,
        invalid_yaml_skill_content: str,
    ) -> None:
        """Test handling of invalid YAML in skill file."""
        create_skill_file(temp_skills_dir, "INVALID_YAML", invalid_yaml_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        # Invalid skill should not count as loaded
        assert count == 0
        assert len(registry.get_errors()) > 0

    def test_load_skills_no_frontmatter(
        self,
        temp_skills_dir: Path,
        no_frontmatter_content: str,
    ) -> None:
        """Test handling of skill file without frontmatter."""
        create_skill_file(temp_skills_dir, "NO_FRONTMATTER", no_frontmatter_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 0
        assert len(registry.get_errors()) > 0

    def test_load_skills_missing_name(
        self,
        temp_skills_dir: Path,
    ) -> None:
        """Test handling of skill file without name field."""
        content = """---
description: Skill without name
---

Content.
"""
        create_skill_file(temp_skills_dir, "NO_NAME", content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 0
        errors = registry.get_errors()
        assert any("name" in e.lower() for e in errors)


# ============================================================================
# SkillRegistry Get Methods Tests
# ============================================================================


class TestSkillRegistryGetMethods:
    """Tests for SkillRegistry get_* methods."""

    def test_get_skill_existing(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test getting an existing skill."""
        create_skill_file(temp_skills_dir, "MY_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        skill = registry.get_skill("MY_SKILL")

        assert skill is not None
        assert skill.name == "MY_SKILL"
        assert skill.description == "A test skill for unit testing"

    def test_get_skill_not_found(self, registry: SkillRegistry) -> None:
        """Test getting a non-existent skill."""
        skill = registry.get_skill("NONEXISTENT")

        assert skill is None

    def test_get_skills_for_agent(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
        minimal_skill_content: str,
    ) -> None:
        """Test filtering skills by agent type."""
        # Create skill with claude-code and codex
        create_skill_file(temp_skills_dir, "MULTI_AGENT", valid_skill_content)

        # Create skill with only claude-code (default)
        claude_only_content = """---
name: CLAUDE_ONLY
agents:
  - claude-code
---

Content.
"""
        create_skill_file(temp_skills_dir, "CLAUDE_ONLY", claude_only_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        codex_skills = registry.get_skills_for_agent("codex")
        claude_skills = registry.get_skills_for_agent("claude-code")

        assert len(codex_skills) == 1
        assert codex_skills[0].name == "MULTI_AGENT"

        assert len(claude_skills) == 2

    def test_get_skills_for_trigger(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test filtering skills by trigger."""
        create_skill_file(temp_skills_dir, "TRIGGERED_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        skills = registry.get_skills_for_trigger("test_trigger")

        assert len(skills) == 1
        assert skills[0].name == "TRIGGERED_SKILL"

        no_skills = registry.get_skills_for_trigger("unknown_trigger")
        assert len(no_skills) == 0

    def test_list_skills(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
        minimal_skill_content: str,
    ) -> None:
        """Test listing all skill names."""
        create_skill_file(temp_skills_dir, "SKILL_A", valid_skill_content)
        create_skill_file(temp_skills_dir, "SKILL_B", minimal_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        names = registry.list_skills()

        assert len(names) == 2
        assert "SKILL_A" in names
        assert "SKILL_B" in names

    def test_list_skills_include_invalid(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
        no_frontmatter_content: str,
    ) -> None:
        """Test listing skills including invalid ones."""
        create_skill_file(temp_skills_dir, "VALID_SKILL", valid_skill_content)
        create_skill_file(temp_skills_dir, "INVALID_SKILL", no_frontmatter_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        valid_names = registry.list_skills(include_invalid=False)
        all_names = registry.list_skills(include_invalid=True)

        assert len(valid_names) == 1
        assert "VALID_SKILL" in valid_names

        assert len(all_names) == 2

    def test_get_all_skills(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
        minimal_skill_content: str,
    ) -> None:
        """Test getting all skill definitions."""
        create_skill_file(temp_skills_dir, "SKILL_1", valid_skill_content)
        create_skill_file(temp_skills_dir, "SKILL_2", minimal_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        all_skills = registry.get_all_skills()

        assert len(all_skills) == 2
        names = [s.name for s in all_skills]
        assert "SKILL_1" in names
        assert "SKILL_2" in names


# ============================================================================
# SkillRegistry Registration Tests
# ============================================================================


class TestSkillRegistryRegistration:
    """Tests for SkillRegistry register/unregister methods."""

    def test_register_skill_with_metadata(self, registry: SkillRegistry) -> None:
        """Test registering a skill with SkillMetadata object."""
        metadata = SkillMetadata(
            name="REGISTERED_SKILL",
            description="Manually registered",
        )

        skill = registry.register_skill(metadata, "Skill content")

        assert skill.name == "REGISTERED_SKILL"
        assert registry.has_skill("REGISTERED_SKILL")

    def test_register_skill_with_dict(self, registry: SkillRegistry) -> None:
        """Test registering a skill with dict metadata."""
        skill = registry.register_skill(
            {"name": "DICT_SKILL", "description": "From dict"},
            "Content",
        )

        assert skill.name == "DICT_SKILL"
        assert registry.has_skill("DICT_SKILL")

    def test_register_skill_invalid_dict(self, registry: SkillRegistry) -> None:
        """Test registering with invalid dict raises error."""
        with pytest.raises(SkillRegistryError):
            registry.register_skill(
                {"name": "invalid name!", "description": "Bad name"},
                "Content",
            )

    def test_unregister_skill_existing(self, registry: SkillRegistry) -> None:
        """Test unregistering an existing skill."""
        registry.register_skill({"name": "TO_REMOVE"}, "Content")

        result = registry.unregister_skill("TO_REMOVE")

        assert result is True
        assert not registry.has_skill("TO_REMOVE")

    def test_unregister_skill_not_found(self, registry: SkillRegistry) -> None:
        """Test unregistering a non-existent skill."""
        result = registry.unregister_skill("NONEXISTENT")

        assert result is False

    def test_clear(self, registry: SkillRegistry) -> None:
        """Test clearing all skills."""
        registry.register_skill({"name": "SKILL_1"}, "Content 1")
        registry.register_skill({"name": "SKILL_2"}, "Content 2")

        assert len(registry) == 2

        registry.clear()

        assert len(registry) == 0
        assert registry.get_errors() == []


# ============================================================================
# SkillRegistry Query Methods Tests
# ============================================================================


class TestSkillRegistryQueryMethods:
    """Tests for SkillRegistry query methods."""

    def test_has_skill_true(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test has_skill returns True for valid skill."""
        create_skill_file(temp_skills_dir, "EXISTING", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        assert registry.has_skill("EXISTING") is True

    def test_has_skill_false(self, registry: SkillRegistry) -> None:
        """Test has_skill returns False for missing skill."""
        assert registry.has_skill("MISSING") is False

    def test_has_skill_invalid(
        self,
        temp_skills_dir: Path,
        no_frontmatter_content: str,
    ) -> None:
        """Test has_skill returns False for invalid skill."""
        create_skill_file(temp_skills_dir, "INVALID", no_frontmatter_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        # Invalid skill exists but has_skill returns False because is_valid is False
        assert registry.has_skill("INVALID") is False

    def test_contains(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test __contains__ operator."""
        create_skill_file(temp_skills_dir, "CONTAINS_TEST", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        assert "CONTAINS_TEST" in registry
        assert "NOT_IN_REGISTRY" not in registry

    def test_len(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test __len__ operator."""
        create_skill_file(temp_skills_dir, "LEN_TEST_1", valid_skill_content)
        create_skill_file(temp_skills_dir, "LEN_TEST_2", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        assert len(registry) == 2

    def test_iter(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test __iter__ operator."""
        create_skill_file(temp_skills_dir, "ITER_1", valid_skill_content)
        create_skill_file(temp_skills_dir, "ITER_2", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        names = list(registry)

        assert len(names) == 2
        assert "ITER_1" in names
        assert "ITER_2" in names


# ============================================================================
# SkillRegistry Representation Tests
# ============================================================================


class TestSkillRegistryRepr:
    """Tests for SkillRegistry string representation."""

    def test_repr_empty(self, registry: SkillRegistry) -> None:
        """Test repr of empty registry."""
        repr_str = repr(registry)

        assert "SkillRegistry" in repr_str
        assert "skills=0" in repr_str
        assert "valid=0" in repr_str

    def test_repr_with_skills(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test repr of registry with skills."""
        create_skill_file(temp_skills_dir, "REPR_SKILL", valid_skill_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        repr_str = repr(registry)

        assert "skills=1" in repr_str
        assert "valid=1" in repr_str
        assert "dirs=1" in repr_str


# ============================================================================
# SkillRegistry Error Handling Tests
# ============================================================================


class TestSkillRegistryErrorHandling:
    """Tests for SkillRegistry error handling."""

    def test_get_errors_empty(self, registry: SkillRegistry) -> None:
        """Test get_errors returns empty list when no errors."""
        assert registry.get_errors() == []

    def test_get_errors_copy(self, registry: SkillRegistry) -> None:
        """Test get_errors returns a copy."""
        registry._errors.append("Test error")

        errors = registry.get_errors()
        errors.append("Another error")

        assert len(registry.get_errors()) == 1

    def test_errors_on_invalid_skill(
        self,
        temp_skills_dir: Path,
        no_frontmatter_content: str,
    ) -> None:
        """Test errors are recorded for invalid skills."""
        create_skill_file(temp_skills_dir, "ERROR_SKILL", no_frontmatter_content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        errors = registry.get_errors()
        assert len(errors) > 0
        assert any("frontmatter" in e.lower() for e in errors)


# ============================================================================
# create_registry Factory Function Tests
# ============================================================================


class TestCreateRegistry:
    """Tests for create_registry factory function."""

    def test_create_registry_empty(self) -> None:
        """Test creating registry without auto_load."""
        registry = create_registry(auto_load=False)

        assert isinstance(registry, SkillRegistry)
        assert len(registry) == 0

    def test_create_registry_with_dirs(self, temp_skills_dir: Path) -> None:
        """Test creating registry with directories."""
        registry = create_registry(
            skills_dirs=[temp_skills_dir],
            auto_load=False,
        )

        assert len(registry._skills_dirs) == 1

    def test_create_registry_auto_load(
        self,
        temp_skills_dir: Path,
        valid_skill_content: str,
    ) -> None:
        """Test creating registry with auto_load."""
        create_skill_file(temp_skills_dir, "AUTO_LOADED", valid_skill_content)

        registry = create_registry(
            skills_dirs=[temp_skills_dir],
            auto_load=True,
        )

        assert registry.has_skill("AUTO_LOADED")


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================


class TestSkillRegistryEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_skill_override(
        self,
        tmp_path: Path,
        valid_skill_content: str,
    ) -> None:
        """Test that later directories can override earlier skills."""
        # Create first skill directory
        dir1 = tmp_path / "skills1"
        dir1.mkdir()
        create_skill_file(dir1, "OVERRIDE_SKILL", valid_skill_content)

        # Create second skill directory with same-named skill
        dir2 = tmp_path / "skills2"
        dir2.mkdir()
        override_content = """---
name: OVERRIDE_SKILL
description: Overridden skill
---

Override content.
"""
        create_skill_file(dir2, "OVERRIDE_SKILL", override_content)

        registry = SkillRegistry(skills_dirs=[dir1, dir2])
        registry.load_skills()

        skill = registry.get_skill("OVERRIDE_SKILL")
        assert skill is not None
        # Second directory should override first
        assert skill.description == "Overridden skill"

    def test_empty_skills_directory(self, temp_skills_dir: Path) -> None:
        """Test loading from empty directory."""
        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 0
        assert len(registry) == 0

    def test_skill_with_empty_content(
        self,
        temp_skills_dir: Path,
    ) -> None:
        """Test skill with only frontmatter, no content."""
        content = """---
name: EMPTY_CONTENT
---

"""
        create_skill_file(temp_skills_dir, "EMPTY_CONTENT", content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 1
        skill = registry.get_skill("EMPTY_CONTENT")
        assert skill is not None
        assert skill.content == ""

    def test_skill_with_complex_frontmatter(
        self,
        temp_skills_dir: Path,
    ) -> None:
        """Test skill with complex nested frontmatter."""
        content = """---
name: COMPLEX_SKILL
description: |
  This is a multi-line
  description for the skill.
triggers:
  - trigger1
  - trigger2
  - trigger3
inputs:
  - name: input1
    type: string
  - name: input2
    type: number
agents:
  - claude-code
  - codex
  - openclaw
---

Complex skill content.
"""
        create_skill_file(temp_skills_dir, "COMPLEX_SKILL", content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        count = registry.load_skills()

        assert count == 1
        skill = registry.get_skill("COMPLEX_SKILL")
        assert skill is not None
        assert "multi-line" in skill.description

    def test_disabled_skill(
        self,
        temp_skills_dir: Path,
    ) -> None:
        """Test that disabled skills are loaded but filtered."""
        content = """---
name: DISABLED_SKILL
enabled: false
---

Disabled skill content.
"""
        create_skill_file(temp_skills_dir, "DISABLED_SKILL", content)

        registry = SkillRegistry(skills_dirs=[temp_skills_dir])
        registry.load_skills()

        # Skill exists in registry
        assert "DISABLED_SKILL" in registry

        # But has_skill checks validity which includes enabled status
        # Note: Currently is_valid doesn't check enabled, but skills
        # with enabled=false are still loaded. This tests current behavior.
        skill = registry.get_skill("DISABLED_SKILL")
        assert skill is not None
        assert skill.metadata.enabled is False

    def test_skill_file_read_error(
        self,
        temp_skills_dir: Path,
    ) -> None:
        """Test handling of file read errors."""
        skill_dir = temp_skills_dir / "UNREADABLE"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"

        # Write valid content first
        skill_file.write_text("---\nname: UNREADABLE\n---\nContent", encoding="utf-8")

        # Mock read to raise error
        with patch("pathlib.Path.read_text", side_effect=PermissionError("No access")):
            registry = SkillRegistry(skills_dirs=[temp_skills_dir])
            registry.load_skills()

            # Should have recorded error
            assert len(registry.get_errors()) > 0
