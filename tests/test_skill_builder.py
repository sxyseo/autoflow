"""
Unit Tests for Skill Builder

Tests the SkillBuilder, BuilderConfig, and related classes
for creating custom skills from templates with user prompts.

These tests use temporary directories and mocked user input
to avoid requiring actual user interaction in test environment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autoflow.skills.builder import (
    BuilderConfig,
    PromptResponse,
    SkillBuilder,
    SkillBuilderError,
    create_builder,
)
from autoflow.skills.templates import (
    TemplateCategory,
    TemplateLoader,
    TemplateRenderer,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory for skill files."""
    output_dir = tmp_path / "skills"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def basic_config() -> BuilderConfig:
    """Return a basic BuilderConfig instance."""
    return BuilderConfig()


@pytest.fixture
def custom_config() -> BuilderConfig:
    """Return a BuilderConfig with custom settings."""
    return BuilderConfig(
        output_dir="custom_skills",
        overwrite=True,
        use_defaults=True,
        validate_before_write=False,
        create_metadata=False,
    )


@pytest.fixture
def template_loader() -> TemplateLoader:
    """Return a TemplateLoader instance."""
    return TemplateLoader()


@pytest.fixture
def builder(template_loader: TemplateLoader) -> SkillBuilder:
    """Return a basic SkillBuilder instance for testing."""
    return SkillBuilder(template_loader=template_loader)


@pytest.fixture
def builder_with_config(template_loader: TemplateLoader) -> SkillBuilder:
    """Return a SkillBuilder instance with custom config."""
    config = BuilderConfig(output_dir="test_output", overwrite=True)
    return SkillBuilder(config=config, template_loader=template_loader)


# ============================================================================
# Helper Functions
# ============================================================================


def create_mock_template(
    name: str = "test_template",
    variables: list[str] | None = None,
) -> MagicMock:
    """Create a mock template for testing."""
    mock_template = MagicMock()
    mock_template.name = name
    mock_template.display_name = name.title()
    mock_template.description = f"Template for {name}"
    mock_template.category = TemplateCategory.CUSTOM
    mock_template.variables = variables or []
    mock_template.get_required_variables.return_value = variables or []
    return mock_template


def read_skill_file(skill_dir: Path) -> tuple[str, dict[str, Any] | None]:
    """Read skill file content and metadata."""
    skill_file = skill_dir / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    metadata = None
    if content.startswith("---\n"):
        # Split frontmatter
        parts = content.split("---\n", 2)
        if len(parts) >= 3:
            import yaml

            try:
                metadata = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                pass
            content = parts[2]

    return content, metadata


# ============================================================================
# BuilderConfig Tests
# ============================================================================


class TestBuilderConfig:
    """Tests for BuilderConfig model."""

    def test_config_init_defaults(self) -> None:
        """Test config initialization with default values."""
        config = BuilderConfig()

        assert config.output_dir == "skills"
        assert config.overwrite is False
        assert config.use_defaults is False
        assert config.validate_before_write is True
        assert config.create_metadata is True

    def test_config_init_custom(self) -> None:
        """Test config initialization with custom values."""
        config = BuilderConfig(
            output_dir="custom",
            overwrite=True,
            use_defaults=True,
            validate_before_write=False,
            create_metadata=False,
        )

        assert config.output_dir == "custom"
        assert config.overwrite is True
        assert config.use_defaults is True
        assert config.validate_before_write is False
        assert config.create_metadata is False

    def test_config_expand_output_dir_tilde(self) -> None:
        """Test that output_dir expands tilde to home directory."""
        with patch.dict("os.environ", {"HOME": "/test/home"}):
            config = BuilderConfig(output_dir="~/skills")

            assert config.output_dir == "/test/home/skills"

    def test_config_expand_output_dir_env_var(self) -> None:
        """Test that output_dir expands environment variables."""
        with patch.dict("os.environ", {"SKILLS_DIR": "/custom/skills"}):
            config = BuilderConfig(output_dir="$SKILLS_DIR")

            assert config.output_dir == "/custom/skills"

    def test_config_expand_output_dir_combined(self) -> None:
        """Test expansion with both tilde and env vars."""
        with patch.dict("os.environ", {"HOME": "/test/home", "PROJECT": "myproject"}):
            config = BuilderConfig(output_dir="~/skills/$PROJECT")

            assert config.output_dir == "/test/home/skills/myproject"

    def test_config_output_dir_no_expansion(self) -> None:
        """Test that normal paths are not expanded."""
        config = BuilderConfig(output_dir="just/a/path")

        assert config.output_dir == "just/a/path"


# ============================================================================
# PromptResponse Tests
# ============================================================================


class TestPromptResponse:
    """Tests for PromptResponse model."""

    def test_response_init_basic(self) -> None:
        """Test response initialization with minimal fields."""
        response = PromptResponse(value="test_value")

        assert response.value == "test_value"
        assert response.skipped is False
        assert response.default_used is False

    def test_response_init_full(self) -> None:
        """Test response initialization with all fields."""
        response = PromptResponse(
            value="test_value",
            skipped=True,
            default_used=True,
        )

        assert response.value == "test_value"
        assert response.skipped is True
        assert response.default_used is True

    def test_response_with_empty_value(self) -> None:
        """Test response with empty string value."""
        response = PromptResponse(value="")

        assert response.value == ""
        assert response.skipped is False
        assert response.default_used is False


# ============================================================================
# SkillBuilderError Tests
# ============================================================================


class TestSkillBuilderError:
    """Tests for SkillBuilderError exception."""

    def test_error_creation(self) -> None:
        """Test creating skill builder error."""
        error = SkillBuilderError("Test error message")

        assert str(error) == "Test error message"
        assert isinstance(error, Exception)

    def test_error_raising(self) -> None:
        """Test raising skill builder error."""
        with pytest.raises(SkillBuilderError) as exc_info:
            raise SkillBuilderError("Build failed")

        assert "Build failed" in str(exc_info.value)


# ============================================================================
# SkillBuilder Init Tests
# ============================================================================


class TestSkillBuilderInit:
    """Tests for SkillBuilder initialization."""

    def test_init_default_config(self, template_loader: TemplateLoader) -> None:
        """Test initialization with default config."""
        builder = SkillBuilder(template_loader=template_loader)

        assert builder.config is not None
        assert builder.config.output_dir == "skills"
        assert builder.template_loader == template_loader
        assert builder.renderer is not None
        assert isinstance(builder.renderer, TemplateRenderer)
        assert builder._prompts_history == []

    def test_init_custom_config(self, template_loader: TemplateLoader) -> None:
        """Test initialization with custom config."""
        config = BuilderConfig(output_dir="custom_output")
        builder = SkillBuilder(config=config, template_loader=template_loader)

        assert builder.config == config
        assert builder.config.output_dir == "custom_output"

    def test_init_default_template_loader(self) -> None:
        """Test initialization creates default template loader."""
        builder = SkillBuilder()

        assert builder.template_loader is not None
        assert isinstance(builder.template_loader, TemplateLoader)

    def test_init_empty_history(self, builder: SkillBuilder) -> None:
        """Test that prompt history starts empty."""
        assert builder.get_prompt_history() == []


# ============================================================================
# SkillBuilder Build Tests
# ============================================================================


class TestSkillBuilderBuild:
    """Tests for SkillBuilder.build method."""

    def test_build_basic(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test basic skill building."""
        skill_path = builder.build(
            name="TEST_SKILL",
            template="implementer",
            variables={
                "name": "TEST_SKILL",
                "description": "A test skill",
            },
            output_dir=temp_output_dir,
        )

        assert skill_path == temp_output_dir / "TEST_SKILL"
        assert skill_path.exists()
        assert (skill_path / "SKILL.md").exists()

    def test_build_with_metadata(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building skill with metadata."""
        builder.config.create_metadata = True

        skill_path = builder.build(
            name="METADATA_SKILL",
            template="implementer",
            variables={
                "name": "METADATA_SKILL",
                "description": "Test metadata",
            },
            output_dir=temp_output_dir,
        )

        content, metadata = read_skill_file(skill_path)

        assert metadata is not None
        assert metadata["name"] == "METADATA_SKILL"

    def test_build_without_metadata(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building skill without metadata."""
        builder.config.create_metadata = False

        skill_path = builder.build(
            name="NO_METADATA_SKILL",
            template="planner",
            variables={
                "name": "NO_METADATA_SKILL",
                "description": "No metadata",
            },
            output_dir=temp_output_dir,
        )

        content, metadata = read_skill_file(skill_path)

        assert metadata is None
        assert "# NO_METADATA_SKILL" in content

    def test_build_invalid_name_raises(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that invalid skill name raises error."""
        with pytest.raises(SkillBuilderError) as exc_info:
            builder.build(
                name="invalid_name",
                template="implementer",
                variables={"name": "INVALID", "description": "Test"},
                output_dir=temp_output_dir,
            )

        assert "UPPER_SNAKE_CASE" in str(exc_info.value)

    def test_build_missing_template_raises(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that missing template raises error."""
        with pytest.raises(SkillBuilderError) as exc_info:
            builder.build(
                name="TEST_SKILL",
                template="nonexistent_template",
                variables={"name": "TEST_SKILL"},
                output_dir=temp_output_dir,
            )

        assert "not found" in str(exc_info.value)

    def test_build_existing_skill_no_overwrite(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that existing skill raises error without overwrite."""
        # Create skill first
        builder.build(
            name="EXISTING_SKILL",
            template="implementer",
            variables={"name": "EXISTING_SKILL", "description": "First"},
            output_dir=temp_output_dir,
        )

        # Try to create again without overwrite
        with pytest.raises(SkillBuilderError) as exc_info:
            builder.build(
                name="EXISTING_SKILL",
                template="implementer",
                variables={"name": "EXISTING_SKILL", "description": "Second"},
                output_dir=temp_output_dir,
            )

        assert "already exists" in str(exc_info.value)

    def test_build_existing_skill_with_overwrite(
        self,
        builder_with_config: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that existing skill can be overwritten."""
        # Create skill first
        first_path = builder_with_config.build(
            name="OVERWRITE_SKILL",
            template="implementer",
            variables={"name": "OVERWRITE_SKILL", "description": "First"},
            output_dir=temp_output_dir,
        )

        # Create again with overwrite=True
        second_path = builder_with_config.build(
            name="OVERWRITE_SKILL",
            template="implementer",
            variables={"name": "OVERWRITE_SKILL", "description": "Second"},
            output_dir=temp_output_dir,
        )

        assert first_path == second_path
        # Verify content was updated
        content, _ = read_skill_file(second_path)
        assert "Second" in content

    def test_build_uses_default_output_dir(
        self,
        builder: SkillBuilder,
        tmp_path: Path,
    ) -> None:
        """Test that build uses config output_dir when not specified."""
        # Change to temp directory
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            builder.config.output_dir = "default_skills"

            skill_path = builder.build(
                name="DEFAULT_DIR_SKILL",
                template="implementer",
                variables={"name": "DEFAULT_DIR_SKILL", "description": "Test"},
            )

            assert skill_path == tmp_path / "default_skills" / "DEFAULT_DIR_SKILL"
        finally:
            os.chdir(original_cwd)

    def test_build_creates_parent_directories(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that build creates parent directories."""
        nested_dir = temp_output_dir / "nested" / "deep" / "path"

        skill_path = builder.build(
            name="NESTED_SKILL",
            template="planner",
            variables={"name": "NESTED_SKILL", "description": "Test"},
            output_dir=nested_dir,
        )

        assert skill_path.exists()
        assert nested_dir.exists()


# ============================================================================
# SkillBuilder Create Skill File Tests
# ============================================================================


class TestSkillBuilderCreateSkillFile:
    """Tests for SkillBuilder.create_skill_file method."""

    def test_create_skill_file_basic(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test basic skill file creation."""
        skill_path = builder.create_skill_file(
            output_dir=temp_output_dir,
            name="BASIC_SKILL",
            content="# Basic Skill\n\nBasic content.",
        )

        assert skill_path == temp_output_dir / "BASIC_SKILL"
        assert skill_path.exists()

        content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        assert "# Basic Skill" in content
        assert "Basic content." in content

    def test_create_skill_file_with_metadata(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test creating skill file with metadata."""
        builder.config.create_metadata = True

        skill_path = builder.create_skill_file(
            output_dir=temp_output_dir,
            name="META_SKILL",
            content="# Meta Skill",
            metadata={"name": "META_SKILL", "description": "Has metadata"},
        )

        content, metadata = read_skill_file(skill_path)

        assert metadata is not None
        assert metadata["name"] == "META_SKILL"
        assert metadata["description"] == "Has metadata"
        assert "# Meta Skill" in content

    def test_create_skill_file_without_metadata(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test creating skill file without metadata."""
        builder.config.create_metadata = False

        skill_path = builder.create_skill_file(
            output_dir=temp_output_dir,
            name="NO_META_SKILL",
            content="# No Meta",
            metadata={"name": "NO_META_SKILL"},
        )

        content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        assert content.startswith("# No Meta")
        assert "---" not in content

    def test_create_skill_file_string_path(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test creating skill file with string path."""
        skill_path = builder.create_skill_file(
            output_dir=str(temp_output_dir),
            name="STRING_PATH_SKILL",
            content="# String Path",
        )

        assert skill_path.exists()
        assert isinstance(skill_path, Path)


# ============================================================================
# SkillBuilder Validation Tests
# ============================================================================


class TestSkillBuilderValidation:
    """Tests for SkillBuilder validation methods."""

    def test_validate_skill_name_valid(self, builder: SkillBuilder) -> None:
        """Test validation of valid skill names."""
        valid_names = [
            "TEST",
            "TEST_SKILL",
            "MY_CUSTOM_SKILL",
            "SKILL_123",
            "A",
            "SKILL_V2",
        ]

        for name in valid_names:
            # Should not raise
            builder._validate_skill_name(name)

    def test_validate_skill_name_empty(self, builder: SkillBuilder) -> None:
        """Test that empty name raises error."""
        with pytest.raises(ValueError) as exc_info:
            builder._validate_skill_name("")

        assert "cannot be empty" in str(exc_info.value)

    def test_validate_skill_name_lowercase(self, builder: SkillBuilder) -> None:
        """Test that lowercase name raises error."""
        with pytest.raises(ValueError) as exc_info:
            builder._validate_skill_name("lowercase")

        assert "UPPER_SNAKE_CASE" in str(exc_info.value)

    def test_validate_skill_name_mixed_case(self, builder: SkillBuilder) -> None:
        """Test that mixed case name raises error."""
        with pytest.raises(ValueError):
            builder._validate_skill_name("Mixed_Case")

    def test_validate_skill_name_special_chars(self, builder: SkillBuilder) -> None:
        """Test that special characters raise error."""
        invalid_names = ["INVALID-NAME", "INVALID.NAME", "INVALID NAME"]

        for name in invalid_names:
            with pytest.raises(ValueError):
                builder._validate_skill_name(name)

    def test_validate_skill_name_starts_with_number(self, builder: SkillBuilder) -> None:
        """Test that name starting with number raises error."""
        with pytest.raises(ValueError):
            builder._validate_skill_name("123_SKILL")

    def test_validate_skill_name_starts_with_underscore(self, builder: SkillBuilder) -> None:
        """Test that name starting with underscore raises error."""
        with pytest.raises(ValueError):
            builder._validate_skill_name("_PRIVATE_SKILL")


# ============================================================================
# SkillBuilder Variable Preparation Tests
# ============================================================================


class TestSkillBuilderVariables:
    """Tests for SkillBuilder variable handling."""

    def test_prepare_variables_with_defaults(
        self,
        builder: SkillBuilder,
    ) -> None:
        """Test preparing variables with defaults."""
        template = create_mock_template("test", ["name", "description"])

        variables = builder._prepare_variables(
            template,
            "MY_SKILL",
            {"description": "Custom description"},
        )

        assert variables["name"] == "MY_SKILL"
        assert variables["description"] == "Custom description"

    def test_prepare_variables_all_provided(
        self,
        builder: SkillBuilder,
    ) -> None:
        """Test preparing variables when all provided."""
        template = create_mock_template("test", ["name", "description"])

        variables = builder._prepare_variables(
            template,
            "MY_SKILL",
            {"name": "CUSTOM_NAME", "description": "Custom description"},
        )

        assert variables["name"] == "CUSTOM_NAME"
        assert variables["description"] == "Custom description"

    def test_prepare_variables_empty_user_vars(
        self,
        builder: SkillBuilder,
    ) -> None:
        """Test preparing variables with empty user dict."""
        template = create_mock_template("test", ["name", "description"])

        variables = builder._prepare_variables(template, "AUTO_SKILL", {})

        assert variables["name"] == "AUTO_SKILL"
        assert variables["description"] == "Custom test template skill"

    def test_get_default_for_variable_name(self, builder: SkillBuilder) -> None:
        """Test getting default for 'name' variable."""
        template = create_mock_template("test", ["name"])

        default = builder._get_default_for_variable("name", "MY_SKILL", template)

        assert default == "MY_SKILL"

    def test_get_default_for_variable_description(self, builder: SkillBuilder) -> None:
        """Test getting default for 'description' variable."""
        template = create_mock_template("test", ["description"])

        default = builder._get_default_for_variable("description", "MY_SKILL", template)

        assert "custom test template skill" in default.lower()

    def test_get_default_for_variable_unknown(self, builder: SkillBuilder) -> None:
        """Test getting default for unknown variable."""
        template = create_mock_template("test", ["unknown"])

        default = builder._get_default_for_variable("unknown", "MY_SKILL", template)

        assert default == ""


# ============================================================================
# SkillBuilder Template Info Tests
# ============================================================================


class TestSkillBuilderTemplateInfo:
    """Tests for SkillBuilder template info methods."""

    def test_list_available_templates(self, builder: SkillBuilder) -> None:
        """Test listing available templates."""
        templates = builder.list_available_templates()

        assert isinstance(templates, list)
        assert "implementer" in templates
        assert "planner" in templates
        assert "reviewer" in templates

    def test_get_template_info_existing(self, builder: SkillBuilder) -> None:
        """Test getting info for existing template."""
        info = builder.get_template_info("implementer")

        assert info is not None
        assert info["name"] == "implementer"
        assert info["display_name"] == "Implementer"
        assert "description" in info
        assert "category" in info
        assert "variables" in info
        assert isinstance(info["variables"], list)

    def test_get_template_info_not_found(self, builder: SkillBuilder) -> None:
        """Test getting info for non-existent template."""
        info = builder.get_template_info("nonexistent")

        assert info is None


# ============================================================================
# SkillBuilder Prompt History Tests
# ============================================================================


class TestSkillBuilderPromptHistory:
    """Tests for SkillBuilder prompt history tracking."""

    def test_prompt_history_empty_initially(self, builder: SkillBuilder) -> None:
        """Test that prompt history starts empty."""
        history = builder.get_prompt_history()

        assert history == []

    def test_prompt_history_returns_copy(self, builder: SkillBuilder) -> None:
        """Test that get_prompt_history returns a copy."""
        builder._prompts_history.append(("test", PromptResponse(value="test")))

        history = builder.get_prompt_history()
        history.append(("another", PromptResponse(value="another")))

        # Original should be unchanged
        assert len(builder._prompts_history) == 1


# ============================================================================
# SkillBuilder Interactive Method Tests
# ============================================================================


class TestSkillBuilderInteractive:
    """Tests for SkillBuilder.build_interactive method."""

    def test_build_interactive_full_flow(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test complete interactive build flow with mocked input."""
        with patch("builtins.input") as mock_input:
            # Mock user inputs
            mock_input.side_effect = [
                "INTERACTIVE_SKILL",  # Skill name
                "implementer",  # Template selection
                "",  # Use default for description
            ]

            skill_path = builder.build_interactive(output_dir=temp_output_dir)

            assert skill_path == temp_output_dir / "INTERACTIVE_SKILL"
            assert skill_path.exists()

            # Verify inputs were called
            assert mock_input.call_count == 3

    def test_build_interactive_invalid_name_then_valid(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test interactive build with invalid then valid name."""
        with patch("builtins.input") as mock_input:
            # Mock user inputs
            mock_input.side_effect = [
                "invalid",  # Invalid name
                "VALID_SKILL",  # Valid name
                "planner",  # Template
                "",  # Default description
            ]

            skill_path = builder.build_interactive(output_dir=temp_output_dir)

            assert skill_path == temp_output_dir / "VALID_SKILL"
            assert skill_path.exists()

    def test_build_interactive_invalid_template_then_valid(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test interactive build with invalid then valid template."""
        with patch("builtins.input") as mock_input:
            mock_input.side_effect = [
                "TEST_SKILL",  # Valid name
                "nonexistent",  # Invalid template
                "reviewer",  # Valid template
                "",  # Default description
            ]

            skill_path = builder.build_interactive(output_dir=temp_output_dir)

            assert skill_path == temp_output_dir / "TEST_SKILL"
            assert skill_path.exists()

    def test_build_interactive_custom_description(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test interactive build with custom description."""
        with patch("builtins.input") as mock_input:
            mock_input.side_effect = [
                "CUSTOM_DESC_SKILL",
                "implementer",
                "My custom description",  # Custom description (not default)
            ]

            skill_path = builder.build_interactive(output_dir=temp_output_dir)

            content, metadata = read_skill_file(skill_path)
            assert "My custom description" in content

    def test_build_interactive_with_use_defaults(
        self,
        builder_with_config: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test interactive build with use_defaults enabled."""
        builder_with_config.config.use_defaults = True

        with patch("builtins.input") as mock_input:
            mock_input.side_effect = [
                "DEFAULTS_SKILL",
                "planner",
            ]

            skill_path = builder_with_config.build_interactive(output_dir=temp_output_dir)

            assert skill_path == temp_output_dir / "DEFAULTS_SKILL"
            # Should skip variable prompts when use_defaults=True
            assert mock_input.call_count == 2


# ============================================================================
# SkillBuilder Internal Prompt Methods Tests
# ============================================================================


class TestSkillBuilderInternalPrompts:
    """Tests for SkillBuilder internal prompt methods."""

    def test_prompt_skill_name_valid(self, builder: SkillBuilder) -> None:
        """Test _prompt_skill_name with valid input."""
        with patch("builtins.input", return_value="VALID_SKILL"):
            name = builder._prompt_skill_name()

            assert name == "VALID_SKILL"

    def test_prompt_skill_name_invalid_then_valid(self, builder: SkillBuilder) -> None:
        """Test _prompt_skill_name with invalid then valid input."""
        with patch("builtins.input") as mock_input:
            mock_input.side_effect = ["invalid", "", "VALID_SKILL"]

            name = builder._prompt_skill_name()

            assert name == "VALID_SKILL"
            assert mock_input.call_count == 3

    def test_prompt_template_selection_valid(self, builder: SkillBuilder) -> None:
        """Test _prompt_template_selection with valid input."""
        with patch("builtins.input", return_value="implementer"):
            template_name = builder._prompt_template_selection()

            assert template_name == "implementer"

    def test_collect_template_variables(
        self,
        builder: SkillBuilder,
    ) -> None:
        """Test _collect_template_variables with mocked input."""
        template = create_mock_template("test", ["var1", "var2"])

        with patch("builtins.input") as mock_input:
            mock_input.side_effect = ["value1", "value2"]

            variables = builder._collect_template_variables(template, "TEST_SKILL")

            assert variables["var1"] == "value1"
            assert variables["var2"] == "value2"

    def test_collect_template_variables_with_defaults(
        self,
        builder: SkillBuilder,
    ) -> None:
        """Test _collect_template_variables uses defaults."""
        template = create_mock_template("test", ["name", "description"])

        with patch("builtins.input") as mock_input:
            # Press enter to use defaults
            mock_input.side_effect = ["", ""]

            variables = builder._collect_template_variables(template, "AUTO_SKILL")

            assert variables["name"] == "AUTO_SKILL"
            assert "custom test template skill" in variables["description"].lower()


# ============================================================================
# create_builder Factory Function Tests
# ============================================================================


class TestCreateBuilder:
    """Tests for create_builder factory function."""

    def test_create_builder_default(self) -> None:
        """Test creating builder with defaults."""
        builder = create_builder()

        assert isinstance(builder, SkillBuilder)
        assert builder.config.output_dir == "skills"

    def test_create_builder_with_config(self) -> None:
        """Test creating builder with custom config."""
        config = BuilderConfig(output_dir="custom", overwrite=True)
        builder = create_builder(config=config)

        assert builder.config == config
        assert builder.config.output_dir == "custom"

    def test_create_builder_with_template_loader(self) -> None:
        """Test creating builder with custom template loader."""
        loader = TemplateLoader()
        builder = create_builder(template_loader=loader)

        assert builder.template_loader == loader


# ============================================================================
# CLI Command Tests
# ============================================================================


class TestSkillCreateCLI:
    """Tests for skill create CLI command."""

    def test_skill_create_non_interactive_basic(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create in non-interactive mode."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "TEST_SKILL",
                    "--template", "implementer",
                    "--output-dir", "skills",
                ],
            )

            assert result.exit_code == 0
            assert "Skill created successfully" in result.output
            assert "TEST_SKILL" in result.output

            # Verify skill file was created
            skill_path = tmp_path / "skills" / "TEST_SKILL" / "SKILL.md"
            assert skill_path.exists()

    def test_skill_create_non_interactive_with_variables(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create with template variables."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "VAR_SKILL",
                    "--template", "implementer",
                    "--variable", "description=My custom variable skill",
                    "--output-dir", "skills",
                ],
            )

            assert result.exit_code == 0
            assert "VAR_SKILL" in result.output

            # Verify content
            skill_path = tmp_path / "skills" / "VAR_SKILL" / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8")
            assert "My custom variable skill" in content

    def test_skill_create_non_interactive_missing_template(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create without template in non-interactive mode."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "TEST_SKILL",
                ],
            )

            assert result.exit_code == 1
            assert "--template is required" in result.output

    def test_skill_create_overwrite_flag(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create with overwrite flag."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create skill first time
            result1 = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "OVERWRITE_SKILL",
                    "--template", "planner",
                    "--output-dir", "skills",
                ],
            )
            assert result1.exit_code == 0

            # Try to create again without overwrite - should fail
            result2 = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "OVERWRITE_SKILL",
                    "--template", "implementer",
                    "--output-dir", "skills",
                ],
            )
            assert result2.exit_code == 1
            assert "already exists" in result2.output

            # Create again with overwrite - should succeed
            result3 = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "OVERWRITE_SKILL",
                    "--template", "implementer",
                    "--output-dir", "skills",
                    "--overwrite",
                ],
            )
            assert result3.exit_code == 0

    def test_skill_create_json_output(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create with JSON output."""
        from click.testing import CliRunner
        from autoflow.cli import skill
        import json

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "JSON_SKILL",
                    "--template", "reviewer",
                    "--output-dir", "skills",
                    "--json",
                ],
            )

            assert result.exit_code == 0

            # Parse JSON output
            output_data = json.loads(result.output)
            assert output_data["status"] == "created"
            assert output_data["name"] == "JSON_SKILL"
            assert "path" in output_data

    def test_skill_create_invalid_variable_format(
        self,
        tmp_path: Path,
    ) -> None:
        """Test skill create with invalid variable format."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(
                skill,
                [
                    "create",
                    "--name", "TEST_SKILL",
                    "--template", "implementer",
                    "--variable", "invalid_format_no_equals",
                ],
            )

            assert result.exit_code == 1
            assert "Invalid variable format" in result.output


class TestSkillTemplateListCLI:
    """Tests for skill template list CLI command."""

    def test_skill_template_list_all(self, tmp_path: Path) -> None:
        """Test listing all templates."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "list"],
        )

        assert result.exit_code == 0
        assert "Available Templates" in result.output
        assert "implementer" in result.output
        assert "planner" in result.output
        assert "reviewer" in result.output

    def test_skill_template_list_by_category(self, tmp_path: Path) -> None:
        """Test listing templates filtered by category."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "list", "--category", "workflow"],
        )

        assert result.exit_code == 0
        assert "WORKFLOW" in result.output or "workflow" in result.output.lower()

    def test_skill_template_list_json_output(self, tmp_path: Path) -> None:
        """Test template list with JSON output."""
        from click.testing import CliRunner
        from autoflow.cli import skill
        import json

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "list", "--json"],
        )

        assert result.exit_code == 0

        # Parse JSON output
        output_data = json.loads(result.output)
        assert "templates" in output_data
        assert "count" in output_data
        assert isinstance(output_data["templates"], list)
        assert len(output_data["templates"]) > 0

        # Verify template structure
        template = output_data["templates"][0]
        assert "name" in template
        assert "display_name" in template
        assert "description" in template
        assert "category" in template
        assert "variables" in template

    def test_skill_template_list_empty_category(self, tmp_path: Path) -> None:
        """Test listing templates with non-existent category."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        # Use an invalid category (this will fail Click's choice validation)
        result = runner.invoke(
            skill,
            ["template", "list", "--category", "nonexistent"],
        )

        # Should fail with Click validation error
        assert result.exit_code != 0


class TestSkillTemplateShowCLI:
    """Tests for skill template show CLI command."""

    def test_skill_template_show_existing(self, tmp_path: Path) -> None:
        """Test showing existing template details."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "show", "implementer"],
        )

        assert result.exit_code == 0
        assert "Implementer" in result.output
        assert "Name: implementer" in result.output
        assert "Description:" in result.output
        assert "Required Variables:" in result.output

    def test_skill_template_show_not_found(self, tmp_path: Path) -> None:
        """Test showing non-existent template."""
        from click.testing import CliRunner
        from autoflow.cli import skill

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "show", "nonexistent_template"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_skill_template_show_json_output(self, tmp_path: Path) -> None:
        """Test template show with JSON output."""
        from click.testing import CliRunner
        from autoflow.cli import skill
        import json

        runner = CliRunner()

        result = runner.invoke(
            skill,
            ["template", "show", "planner", "--json"],
        )

        assert result.exit_code == 0

        # Parse JSON output
        output_data = json.loads(result.output)
        assert output_data["name"] == "planner"
        assert "display_name" in output_data
        assert "description" in output_data
        assert "category" in output_data
        assert "variables" in output_data
        assert "content" in output_data
        assert "metadata_template" in output_data


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================


class TestSkillBuilderEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_build_with_missing_required_variable(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building with missing required variable."""
        # Template requires 'name' and 'description', but we only provide 'name'
        with pytest.raises(SkillBuilderError) as exc_info:
            builder.build(
                name="MISSING_VAR_SKILL",
                template="implementer",
                variables={"name": "MISSING_VAR_SKILL"},
                output_dir=temp_output_dir,
            )

        assert "rendering failed" in str(exc_info.value).lower()

    def test_build_empty_template_variables(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building template with no variables."""
        # Create a minimal template with no variables
        mock_template = create_mock_template("minimal", [])
        mock_template.get_required_variables.return_value = []
        mock_template.content = "Static content"

        with patch.object(
            builder.template_loader,
            "get_template",
            return_value=mock_template,
        ):
            skill_path = builder.build(
                name="STATIC_SKILL",
                template="minimal",
                variables={},
                output_dir=temp_output_dir,
            )

            assert skill_path.exists()

    def test_create_skill_file_permission_error(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test handling file creation errors."""
        readonly_dir = temp_output_dir / "readonly"
        readonly_dir.mkdir()

        # Make directory read-only
        import stat

        readonly_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

        try:
            with pytest.raises(SkillBuilderError) as exc_info:
                builder.create_skill_file(
                    output_dir=readonly_dir,
                    name="PERMISSION_SKILL",
                    content="Content",
                )

            assert "Failed to create skill file" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(stat.S_IRWXU)

    def test_multiple_builds_independent_histories(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that multiple builds have independent histories."""
        # Build first skill
        with patch("builtins.input", side_effect=["SKILL_1", "implementer", ""]):
            builder.build_interactive(output_dir=temp_output_dir)

        history1 = builder.get_prompt_history()

        # Build second skill
        with patch("builtins.input", side_effect=["SKILL_2", "planner", ""]):
            builder.build_interactive(output_dir=temp_output_dir)

        history2 = builder.get_prompt_history()

        # Histories should accumulate
        assert len(history2) > len(history1)

    def test_build_with_unicode_content(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building skill with Unicode content."""
        skill_path = builder.build(
            name="UNICODE_SKILL",
            template="planner",
            variables={
                "name": "UNICODE_SKILL",
                "description": "Skill with emoji 🚀 and 中文",
            },
            output_dir=temp_output_dir,
        )

        content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        assert "🚀" in content
        assert "中文" in content

    def test_build_very_long_description(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test building skill with very long description."""
        long_desc = "A" * 10000  # 10k characters

        skill_path = builder.build(
            name="LONG_DESC_SKILL",
            template="reviewer",
            variables={
                "name": "LONG_DESC_SKILL",
                "description": long_desc,
            },
            output_dir=temp_output_dir,
        )

        content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        assert len(content) > 10000

    def test_config_immutability_per_build(
        self,
        builder: SkillBuilder,
        temp_output_dir: Path,
    ) -> None:
        """Test that config doesn't change between builds."""
        original_output = builder.config.output_dir

        builder.build(
            name="CONFIG_TEST_1",
            template="implementer",
            variables={"name": "CONFIG_TEST_1", "description": "Test"},
            output_dir=temp_output_dir,
        )

        assert builder.config.output_dir == original_output

        builder.build(
            name="CONFIG_TEST_2",
            template="planner",
            variables={"name": "CONFIG_TEST_2", "description": "Test"},
            output_dir=temp_output_dir,
        )

        assert builder.config.output_dir == original_output
