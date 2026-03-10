"""
Unit Tests for Skill Templates

Tests the SkillTemplate, TemplateRenderer, and TemplateLoader classes
for creating, managing, and rendering skill templates.

These tests cover template validation, variable substitution,
template loading, and rendering functionality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from autoflow.skills.templates import (
    BUILTIN_TEMPLATES,
    RenderedTemplate,
    SkillTemplate,
    TemplateCategory,
    TemplateLoader,
    TemplateLoaderError,
    TemplateRenderer,
    create_loader,
    create_renderer,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def basic_template() -> SkillTemplate:
    """Return a basic skill template for testing."""
    return SkillTemplate(
        name="test_template",
        display_name="Test Template",
        description="A template for testing",
        category=TemplateCategory.WORKFLOW,
        variables=["name", "description"],
        content="# {{ name }}\n\n{{ description }}",
    )


@pytest.fixture
def complex_template() -> SkillTemplate:
    """Return a complex template with nested variables."""
    return SkillTemplate(
        name="complex_template",
        display_name="Complex Template",
        description="A complex template with metadata",
        category=TemplateCategory.CUSTOM,
        variables=["name", "description", "author"],
        metadata_template={
            "name": "{{ name }}",
            "description": "{{ description }}",
            "author": "{{ author }}",
        },
        content="""# {{ name }}

{{ description }}

Author: {{ author }}

## Workflow

1. Step one
2. Step two
""",
    )


@pytest.fixture
def template_with_lists() -> SkillTemplate:
    """Return a template with list variables in metadata."""
    return SkillTemplate(
        name="list_template",
        display_name="List Template",
        description="Template with lists",
        metadata_template={
            "name": "{{ name }}",
            "triggers": ["{{ trigger1 }}", "{{ trigger2 }}"],
            "inputs": ["{{ input1 }}", "{{ input2 }}"],
        },
        content="# {{ name }}",
    )


@pytest.fixture
def renderer() -> TemplateRenderer:
    """Create a basic TemplateRenderer instance for testing."""
    return TemplateRenderer()


@pytest.fixture
def loader() -> TemplateLoader:
    """Create a basic TemplateLoader instance for testing."""
    return TemplateLoader()


# ============================================================================
# TemplateCategory Tests
# ============================================================================


class TestTemplateCategory:
    """Tests for TemplateCategory enum."""

    def test_category_values(self) -> None:
        """Test category enum values."""
        assert TemplateCategory.WORKFLOW == "workflow"
        assert TemplateCategory.REVIEW == "review"
        assert TemplateCategory.PLANNING == "planning"
        assert TemplateCategory.VALIDATION == "validation"
        assert TemplateCategory.CUSTOM == "custom"

    def test_category_iteration(self) -> None:
        """Test iterating over categories."""
        categories = list(TemplateCategory)
        assert len(categories) == 5
        assert TemplateCategory.WORKFLOW in categories


# ============================================================================
# SkillTemplate Tests
# ============================================================================


class TestSkillTemplate:
    """Tests for SkillTemplate model."""

    def test_template_init_minimal(self) -> None:
        """Test template initialization with minimal fields."""
        template = SkillTemplate(
            name="minimal",
            display_name="Minimal Template",
            description="Minimal description",
        )

        assert template.name == "minimal"
        assert template.display_name == "Minimal Template"
        assert template.description == "Minimal description"
        assert template.category == TemplateCategory.CUSTOM
        assert template.variables == []
        assert template.content == ""
        assert template.metadata_template == {}

    def test_template_init_full(self, basic_template: SkillTemplate) -> None:
        """Test template initialization with all fields."""
        assert basic_template.name == "test_template"
        assert basic_template.display_name == "Test Template"
        assert basic_template.category == TemplateCategory.WORKFLOW
        assert basic_template.variables == ["name", "description"]
        assert basic_template.content == "# {{ name }}\n\n{{ description }}"

    def test_template_validate_name_empty(self) -> None:
        """Test that empty name raises validation error."""
        with pytest.raises(ValueError) as exc_info:
            SkillTemplate(
                name="",
                display_name="Empty",
                description="Empty name template",
            )

        assert "cannot be empty" in str(exc_info.value)

    def test_template_validate_name_uppercase(self) -> None:
        """Test that uppercase name raises validation error."""
        with pytest.raises(ValueError) as exc_info:
            SkillTemplate(
                name="InvalidName",
                display_name="Invalid",
                description="Invalid name template",
            )

        assert "lowercase" in str(exc_info.value)

    def test_template_validate_name_special_chars(self) -> None:
        """Test that special characters in name raise validation error."""
        with pytest.raises(ValueError):
            SkillTemplate(
                name="invalid-name!",
                display_name="Invalid",
                description="Invalid name template",
            )

    def test_template_validate_name_valid_formats(self) -> None:
        """Test valid name formats."""
        valid_names = [
            "test",
            "test_template",
            "test-template",
            "test_123",
            "t",
            "my_awesome_template",
        ]

        for name in valid_names:
            template = SkillTemplate(
                name=name,
                display_name=name.title(),
                description=f"Template {name}",
            )
            assert template.name == name

    def test_template_validate_variables_invalid(self) -> None:
        """Test that invalid variable names raise validation error."""
        with pytest.raises(ValueError) as exc_info:
            SkillTemplate(
                name="test",
                display_name="Test",
                description="Test",
                variables=["valid_var", "123invalid"],
            )

        assert "Invalid variable name" in str(exc_info.value)

    def test_template_validate_variables_valid(self) -> None:
        """Test valid variable names."""
        valid_vars = [
            ["name", "description"],
            ["_private", "var123", "CamelCase"],
            ["input1", "input2", "input_3"],
        ]

        for variables in valid_vars:
            template = SkillTemplate(
                name="test",
                display_name="Test",
                description="Test",
                variables=variables,
            )
            assert template.variables == variables

    def test_get_required_variables_from_content(self) -> None:
        """Test extracting variables from content."""
        template = SkillTemplate(
            name="test",
            display_name="Test",
            description="Test",
            content="# {{ name }}\n\n{{ description }}\n\nAuthor: {{ author }}",
        )

        required = template.get_required_variables()
        assert set(required) == {"author", "description", "name"}

    def test_get_required_variables_from_metadata(self) -> None:
        """Test extracting variables from metadata template."""
        template = SkillTemplate(
            name="test",
            display_name="Test",
            description="Test",
            metadata_template={
                "name": "{{ name }}",
                "version": "{{ version }}",
            },
        )

        required = template.get_required_variables()
        assert set(required) == {"name", "version"}

    def test_get_required_variables_combined(self, complex_template: SkillTemplate) -> None:
        """Test extracting variables from both content and metadata."""
        required = complex_template.get_required_variables()
        assert set(required) == {"author", "description", "name"}

    def test_render_with_variables(self, basic_template: SkillTemplate) -> None:
        """Test rendering template with variables."""
        result = basic_template.render({"name": "MY_SKILL", "description": "My skill description"})

        assert result == "# MY_SKILL\n\nMy skill description"

    def test_render_missing_variables(self, basic_template: SkillTemplate) -> None:
        """Test rendering with missing variables raises error."""
        with pytest.raises(ValueError) as exc_info:
            basic_template.render({"name": "MY_SKILL"})

        assert "Missing required template variables" in str(exc_info.value)
        assert "description" in str(exc_info.value)


# ============================================================================
# RenderedTemplate Tests
# ============================================================================


class TestRenderedTemplate:
    """Tests for RenderedTemplate dataclass."""

    def test_rendered_template_init(self) -> None:
        """Test RenderedTemplate initialization."""
        template = SkillTemplate(
            name="test",
            display_name="Test",
            description="Test",
        )

        rendered = RenderedTemplate(
            content="# RENDERED",
            metadata={"name": "RENDERED"},
            variables={"name": "RENDERED"},
            template=template,
        )

        assert rendered.content == "# RENDERED"
        assert rendered.metadata == {"name": "RENDERED"}
        assert rendered.variables == {"name": "RENDERED"}
        assert rendered.template == template


# ============================================================================
# TemplateRenderer Tests
# ============================================================================


class TestTemplateRenderer:
    """Tests for TemplateRenderer class."""

    def test_renderer_init(self, renderer: TemplateRenderer) -> None:
        """Test renderer initialization."""
        assert renderer is not None
        assert renderer.VARIABLE_PATTERN is not None

    def test_render_simple_string(self, renderer: TemplateRenderer) -> None:
        """Test rendering a simple template string."""
        result = renderer.render("Hello {{ name }}", {"name": "World"})

        assert result == "Hello World"

    def test_render_multiple_variables(self, renderer: TemplateRenderer) -> None:
        """Test rendering with multiple variables."""
        template = "# {{ name }}\n\n{{ description }}\n\nAuthor: {{ author }}"
        variables = {
            "name": "MY_SKILL",
            "description": "My description",
            "author": "John Doe",
        }

        result = renderer.render(template, variables)

        assert result == "# MY_SKILL\n\nMy description\n\nAuthor: John Doe"

    def test_render_with_whitespace(self, renderer: TemplateRenderer) -> None:
        """Test rendering with varying whitespace."""
        template = "Hello {{name}} and {{ name }} and {{  name  }}"
        result = renderer.render(template, {"name": "World"})

        assert result == "Hello World and World and World"

    def test_render_missing_variable(self, renderer: TemplateRenderer) -> None:
        """Test rendering with missing variable raises error."""
        with pytest.raises(ValueError) as exc_info:
            renderer.render("Hello {{ name }} {{ age }}", {"name": "World"})

        assert "Missing required template variables" in str(exc_info.value)
        assert "age" in str(exc_info.value)

    def test_render_no_variables(self, renderer: TemplateRenderer) -> None:
        """Test rendering string without variables."""
        result = renderer.render("Just plain text", {})

        assert result == "Just plain text"

    def test_render_dict_string_values(self, renderer: TemplateRenderer) -> None:
        """Test rendering dictionary with string values."""
        template_dict = {
            "name": "{{ name }}",
            "description": "{{ description }}",
        }
        variables = {"name": "TEST", "description": "Test description"}

        result = renderer.render_dict(template_dict, variables)

        assert result == {
            "name": "TEST",
            "description": "Test description",
        }

    def test_render_dict_nested_dict(self, renderer: TemplateRenderer) -> None:
        """Test rendering dictionary with nested dictionaries."""
        template_dict = {
            "metadata": {
                "name": "{{ name }}",
                "version": "{{ version }}",
            },
        }
        variables = {"name": "SKILL", "version": "1.0.0"}

        result = renderer.render_dict(template_dict, variables)

        assert result == {
            "metadata": {
                "name": "SKILL",
                "version": "1.0.0",
            },
        }

    def test_render_dict_list_values(self, renderer: TemplateRenderer) -> None:
        """Test rendering dictionary with list values."""
        template_dict = {
            "triggers": ["{{ trigger1 }}", "{{ trigger2 }}"],
            "inputs": ["{{ input1 }}", "static_value"],
        }
        variables = {
            "trigger1": "test_trigger",
            "trigger2": "another_trigger",
            "input1": "user_input",
        }

        result = renderer.render_dict(template_dict, variables)

        assert result == {
            "triggers": ["test_trigger", "another_trigger"],
            "inputs": ["user_input", "static_value"],
        }

    def test_render_dict_non_string_values(self, renderer: TemplateRenderer) -> None:
        """Test rendering dictionary preserves non-string values."""
        template_dict = {
            "name": "{{ name }}",
            "enabled": True,
            "count": 42,
            "tags": ["tag1", "tag2"],
        }

        result = renderer.render_dict(template_dict, {"name": "TEST"})

        assert result == {
            "name": "TEST",
            "enabled": True,
            "count": 42,
            "tags": ["tag1", "tag2"],
        }

    def test_render_template_simple(self, renderer: TemplateRenderer) -> None:
        """Test rendering a complete SkillTemplate."""
        template = SkillTemplate(
            name="test",
            display_name="Test",
            description="Test template",
            variables=["name", "description"],
            content="# {{ name }}\n\n{{ description }}",
            metadata_template={
                "name": "{{ name }}",
                "description": "{{ description }}",
            },
        )

        result = renderer.render_template(template, {"name": "MY_SKILL", "description": "My skill"})

        assert isinstance(result, RenderedTemplate)
        assert result.content == "# MY_SKILL\n\nMy skill"
        assert result.metadata == {"name": "MY_SKILL", "description": "My skill"}
        assert result.template == template

    def test_render_template_complex(self, renderer: TemplateRenderer, complex_template: SkillTemplate) -> None:
        """Test rendering complex template with metadata."""
        variables = {
            "name": "COMPLEX_SKILL",
            "description": "A complex skill",
            "author": "Jane Doe",
        }

        result = renderer.render_template(complex_template, variables)

        assert result.content == "# COMPLEX_SKILL\n\nA complex skill\n\nAuthor: Jane Doe\n\n## Workflow\n\n1. Step one\n2. Step two\n"
        assert result.metadata == {
            "name": "COMPLEX_SKILL",
            "description": "A complex skill",
            "author": "Jane Doe",
        }

    def test_render_template_missing_variables(self, renderer: TemplateRenderer, basic_template: SkillTemplate) -> None:
        """Test rendering template with missing variables raises error."""
        with pytest.raises(ValueError) as exc_info:
            renderer.render_template(basic_template, {"name": "TEST"})

        assert "Missing required template variables" in str(exc_info.value)


# ============================================================================
# TemplateLoader Tests
# ============================================================================


class TestTemplateLoaderInit:
    """Tests for TemplateLoader initialization."""

    def test_init_empty(self, loader: TemplateLoader) -> None:
        """Test empty loader initialization."""
        assert len(loader) == 3  # Three builtin templates
        assert loader.has_template("planner")
        assert loader.has_template("implementer")
        assert loader.has_template("reviewer")

    def test_init_with_custom_dir(self, tmp_path: Path) -> None:
        """Test initialization with custom templates directory."""
        custom_dir = tmp_path / "custom_templates"
        custom_dir.mkdir()

        loader = TemplateLoader(custom_templates_dir=custom_dir)

        assert len(loader) == 3  # Still has builtin templates
        assert loader._custom_dir == custom_dir

    def test_init_with_nonexistent_dir(self, tmp_path: Path) -> None:
        """Test initialization with non-existent custom directory."""
        nonexistent_dir = tmp_path / "nonexistent"

        loader = TemplateLoader(custom_templates_dir=nonexistent_dir)

        assert len(loader) == 3  # Has builtin templates
        assert loader._custom_dir is not None


class TestTemplateLoaderGetTemplate:
    """Tests for TemplateLoader.get_template method."""

    def test_get_template_existing(self, loader: TemplateLoader) -> None:
        """Test getting an existing template."""
        template = loader.get_template("implementer")

        assert template is not None
        assert template.name == "implementer"
        assert template.display_name == "Implementer"

    def test_get_template_not_found(self, loader: TemplateLoader) -> None:
        """Test getting a non-existent template."""
        template = loader.get_template("nonexistent")

        assert template is None

    def test_get_template_all_builtins(self, loader: TemplateLoader) -> None:
        """Test getting all built-in templates."""
        planner = loader.get_template("planner")
        implementer = loader.get_template("implementer")
        reviewer = loader.get_template("reviewer")

        assert planner is not None
        assert implementer is not None
        assert reviewer is not None


class TestTemplateLoaderListTemplates:
    """Tests for TemplateLoader.list_templates method."""

    def test_list_templates_all(self, loader: TemplateLoader) -> None:
        """Test listing all templates."""
        templates = loader.list_templates()

        assert len(templates) == 3
        names = [t.name for t in templates]
        assert "implementer" in names
        assert "planner" in names
        assert "reviewer" in names

    def test_list_templates_by_category(self, loader: TemplateLoader) -> None:
        """Test listing templates filtered by category."""
        workflow_templates = loader.list_templates(category=TemplateCategory.WORKFLOW)
        planning_templates = loader.list_templates(category=TemplateCategory.PLANNING)
        review_templates = loader.list_templates(category=TemplateCategory.REVIEW)

        assert len(workflow_templates) == 1
        assert workflow_templates[0].name == "implementer"

        assert len(planning_templates) == 1
        assert planning_templates[0].name == "planner"

        assert len(review_templates) == 1
        assert review_templates[0].name == "reviewer"

    def test_list_templates_empty_category(self, loader: TemplateLoader) -> None:
        """Test listing templates with category that has no templates."""
        templates = loader.list_templates(category=TemplateCategory.VALIDATION)

        assert len(templates) == 0

    def test_list_templates_sorted(self, loader: TemplateLoader) -> None:
        """Test that templates are sorted by name."""
        templates = loader.list_templates()
        names = [t.name for t in templates]

        # Check if sorted
        assert names == sorted(names)


class TestTemplateLoaderGetCategories:
    """Tests for TemplateLoader.get_categories method."""

    def test_get_categories_all(self, loader: TemplateLoader) -> None:
        """Test getting all categories."""
        categories = loader.get_categories()

        assert len(categories) == 3
        assert TemplateCategory.WORKFLOW in categories
        assert TemplateCategory.PLANNING in categories
        assert TemplateCategory.REVIEW in categories


class TestTemplateLoaderAddTemplate:
    """Tests for TemplateLoader.add_template method."""

    def test_add_template_new(self, loader: TemplateLoader) -> None:
        """Test adding a new template."""
        new_template = SkillTemplate(
            name="custom",
            display_name="Custom",
            description="Custom template",
            category=TemplateCategory.CUSTOM,
        )

        loader.add_template(new_template)

        assert loader.has_template("custom")
        assert len(loader) == 4

    def test_add_template_duplicate(self, loader: TemplateLoader) -> None:
        """Test adding duplicate template raises error."""
        template = SkillTemplate(
            name="implementer",  # Already exists
            display_name="Duplicate",
            description="Duplicate template",
        )

        with pytest.raises(TemplateLoaderError) as exc_info:
            loader.add_template(template)

        assert "already exists" in str(exc_info.value)

    def test_add_template_override_builtins(self, loader: TemplateLoader) -> None:
        """Test that custom templates can override builtins (if removed first)."""
        # Remove builtin first
        loader.remove_template("implementer")

        # Add custom with same name
        custom_template = SkillTemplate(
            name="implementer",
            display_name="Custom Implementer",
            description="Custom implementation",
        )

        loader.add_template(custom_template)

        template = loader.get_template("implementer")
        assert template is not None
        assert template.display_name == "Custom Implementer"


class TestTemplateLoaderRemoveTemplate:
    """Tests for TemplateLoader.remove_template method."""

    def test_remove_template_existing(self, loader: TemplateLoader) -> None:
        """Test removing an existing template."""
        result = loader.remove_template("implementer")

        assert result is True
        assert not loader.has_template("implementer")
        assert len(loader) == 2

    def test_remove_template_not_found(self, loader: TemplateLoader) -> None:
        """Test removing a non-existent template."""
        result = loader.remove_template("nonexistent")

        assert result is False

    def test_remove_template_can_add_again(self, loader: TemplateLoader) -> None:
        """Test that removed template can be added again."""
        # Remove builtin
        loader.remove_template("implementer")
        assert not loader.has_template("implementer")

        # Add new template with same name
        new_template = SkillTemplate(
            name="implementer",
            display_name="New Implementer",
            description="New implementation",
        )

        loader.add_template(new_template)
        assert loader.has_template("implementer")


class TestTemplateLoaderHasTemplate:
    """Tests for TemplateLoader.has_template method."""

    def test_has_template_true(self, loader: TemplateLoader) -> None:
        """Test has_template returns True for existing template."""
        assert loader.has_template("planner") is True

    def test_has_template_false(self, loader: TemplateLoader) -> None:
        """Test has_template returns False for missing template."""
        assert loader.has_template("nonexistent") is False

    def test_has_template_after_removal(self, loader: TemplateLoader) -> None:
        """Test has_template after removing template."""
        loader.remove_template("reviewer")
        assert loader.has_template("reviewer") is False


class TestTemplateLoaderMagicMethods:
    """Tests for TemplateLoader magic methods."""

    def test_len(self, loader: TemplateLoader) -> None:
        """Test __len__ method."""
        assert len(loader) == 3

        loader.add_template(
            SkillTemplate(
                name="test",
                display_name="Test",
                description="Test",
            )
        )
        assert len(loader) == 4

    def test_contains(self, loader: TemplateLoader) -> None:
        """Test __contains__ method."""
        assert "planner" in loader
        assert "implementer" in loader
        assert "reviewer" in loader
        assert "nonexistent" not in loader

    def test_repr(self, loader: TemplateLoader) -> None:
        """Test __repr__ method."""
        repr_str = repr(loader)

        assert "TemplateLoader" in repr_str
        assert "templates=3" in repr_str


# ============================================================================
# BUILTIN_TEMPLATES Tests
# ============================================================================


class TestBuiltinTemplates:
    """Tests for built-in templates."""

    def test_builtin_templates_exist(self) -> None:
        """Test that all built-in templates exist."""
        assert "planner" in BUILTIN_TEMPLATES
        assert "implementer" in BUILTIN_TEMPLATES
        assert "reviewer" in BUILTIN_TEMPLATES

    def test_builtin_planner_template(self) -> None:
        """Test planner template structure."""
        template = BUILTIN_TEMPLATES["planner"]

        assert template.name == "planner"
        assert template.display_name == "Planner"
        assert template.category == TemplateCategory.PLANNING
        assert "name" in template.variables
        assert "description" in template.variables
        assert "{{ name }}" in template.content
        assert "{{ description }}" in template.content

    def test_builtin_implementer_template(self) -> None:
        """Test implementer template structure."""
        template = BUILTIN_TEMPLATES["implementer"]

        assert template.name == "implementer"
        assert template.display_name == "Implementer"
        assert template.category == TemplateCategory.WORKFLOW
        assert "name" in template.variables
        assert "description" in template.variables

    def test_builtin_reviewer_template(self) -> None:
        """Test reviewer template structure."""
        template = BUILTIN_TEMPLATES["reviewer"]

        assert template.name == "reviewer"
        assert template.display_name == "Reviewer"
        assert template.category == TemplateCategory.REVIEW
        assert "name" in template.variables
        assert "description" in template.variables

    def test_builtin_templates_valid(self) -> None:
        """Test that all built-in templates are valid SkillTemplate instances."""
        for name, template in BUILTIN_TEMPLATES.items():
            assert isinstance(template, SkillTemplate)
            assert template.name == name
            # Should be able to get required variables without error
            template.get_required_variables()


# ============================================================================
# Factory Functions Tests
# ============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_loader(self) -> None:
        """Test create_loader factory function."""
        loader = create_loader()

        assert isinstance(loader, TemplateLoader)
        assert len(loader) == 3

    def test_create_loader_with_custom_dir(self, tmp_path: Path) -> None:
        """Test create_loader with custom directory."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        loader = create_loader(custom_templates_dir=custom_dir)

        assert isinstance(loader, TemplateLoader)
        assert loader._custom_dir == custom_dir

    def test_create_renderer(self) -> None:
        """Test create_renderer factory function."""
        renderer = create_renderer()

        assert isinstance(renderer, TemplateRenderer)


# ============================================================================
# Integration Tests
# ============================================================================


class TestTemplateIntegration:
    """Integration tests for template system."""

    def test_full_template_workflow(self) -> None:
        """Test complete workflow from load to render."""
        # Load template
        loader = create_loader()
        template = loader.get_template("implementer")
        assert template is not None

        # Render template
        renderer = create_renderer()
        variables = {
            "name": "MY_IMPLEMENTER",
            "description": "A custom implementer skill",
        }

        result = renderer.render_template(template, variables)

        # Verify result
        assert isinstance(result, RenderedTemplate)
        assert "MY_IMPLEMENTER" in result.content
        assert "custom implementer skill" in result.content
        assert result.metadata["name"] == "MY_IMPLEMENTER"
        assert result.metadata["description"] == "A custom implementer skill"

    def test_template_with_complex_rendering(self) -> None:
        """Test template with complex variable substitution."""
        template = SkillTemplate(
            name="complex",
            display_name="Complex",
            description="Complex template",
            variables=["name", "items"],
            metadata_template={
                "name": "{{ name }}",
                "items": ["{{ item1 }}", "{{ item2 }}", "{{ item3 }}"],
            },
            content="""# {{ name }}

Items:
- {{ item1 }}
- {{ item2 }}
- {{ item3 }}
""",
        )

        renderer = create_renderer()
        variables = {
            "name": "SHOPPING_LIST",
            "item1": "Milk",
            "item2": "Eggs",
            "item3": "Bread",
        }

        result = renderer.render_template(template, variables)

        assert "SHOPPING_LIST" in result.content
        assert "- Milk" in result.content
        assert "- Eggs" in result.content
        assert "- Bread" in result.content
        assert result.metadata["items"] == ["Milk", "Eggs", "Bread"]


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================


class TestTemplateEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_template_with_empty_variables_list(self, renderer: TemplateRenderer) -> None:
        """Test template with variables list but no actual variables."""
        result = renderer.render("No variables here", {})

        assert result == "No variables here"

    def test_template_with_repeated_variables(self, renderer: TemplateRenderer) -> None:
        """Test template with repeated variable usage."""
        template = "{{ name }}: {{ name }} is {{ name }}"
        result = renderer.render(template, {"name": "TEST"})

        assert result == "TEST: TEST is TEST"

    def test_template_with_special_characters_in_value(self, renderer: TemplateRenderer) -> None:
        """Test rendering with special characters in variable values."""
        template = "Value: {{ value }}"
        result = renderer.render(template, {"value": "Hello\nWorld\t!@#$%"})

        assert "Hello\nWorld\t!@#$%" in result

    def test_template_with_unicode(self, renderer: TemplateRenderer) -> None:
        """Test rendering with Unicode characters."""
        template = "Hello {{ name }} with {{ emoji }}"
        result = renderer.render(template, {"name": "世界", "emoji": "🚀"})

        assert "世界" in result
        assert "🚀" in result

    def test_template_with_very_long_content(self, renderer: TemplateRenderer) -> None:
        """Test rendering very long content."""
        long_content = "Item {{ i }}\n" * 1000
        template = "# List\n\n" + long_content

        variables = {f"i{i}": f"Item{i}" for i in range(1000)}
        variables["i"] = "SPECIAL"

        result = renderer.render(template, variables)

        assert "Item SPECIAL" in result
        assert len(result) > 10000

    def test_template_with_deeply_nested_metadata(self, renderer: TemplateRenderer) -> None:
        """Test rendering deeply nested metadata dictionary."""
        template_dict = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "{{ deep_value }}",
                    },
                },
            },
        }

        result = renderer.render_dict(template_dict, {"deep_value": "DEEP"})

        assert result["level1"]["level2"]["level3"]["value"] == "DEEP"

    def test_template_with_mixed_list_types(self, renderer: TemplateRenderer) -> None:
        """Test rendering list with mixed types."""
        template_dict = {
            "mixed": ["{{ str1 }}", 123, True, None, "{{ str2 }}"],
        }

        result = renderer.render_dict(template_dict, {"str1": "A", "str2": "B"})

        assert result["mixed"] == ["A", 123, True, None, "B"]

    def test_template_name_ending_with_underscore(self) -> None:
        """Test template name ending with underscore."""
        with pytest.raises(ValueError):
            SkillTemplate(
                name="test_",
                display_name="Test",
                description="Test",
            )

    def test_template_name_starting_with_number(self) -> None:
        """Test template name starting with number."""
        with pytest.raises(ValueError):
            SkillTemplate(
                name="123test",
                display_name="Test",
                description="Test",
            )

    def test_template_with_no_matching_pattern(self, renderer: TemplateRenderer) -> None:
        """Test rendering string with no variable patterns."""
        result = renderer.render(
            "This has {{ brackets }} but not variables",
            {},
        )

        # Should still work if all variables are provided
        result_with_vars = renderer.render(
            "This has {{ brackets }} but not variables",
            {"brackets": "matched"},
        )

        assert "matched" in result_with_vars
