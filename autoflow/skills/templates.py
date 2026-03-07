"""
Autoflow Skill Templates Module

Provides template system for creating new skills with consistent structure
and patterns. Templates support variable substitution for customization.

Usage:
    from autoflow.skills.templates import (
        TemplateLoader,
        TemplateRenderer,
        BUILTIN_TEMPLATES,
    )

    loader = TemplateLoader()
    template = loader.get_template("implementer")

    renderer = TemplateRenderer()
    content = renderer.render(template.content, {"name": "MY_SKILL"})
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator

import string


class TemplateCategory(str, Enum):
    """Category of skill template."""

    WORKFLOW = "workflow"
    REVIEW = "review"
    PLANNING = "planning"
    VALIDATION = "validation"
    CUSTOM = "custom"


class SkillTemplate(BaseModel):
    """
    Template for creating new skills.

    Defines the structure and content of a skill template with
    placeholders for variable substitution.

    Attributes:
        name: Unique template identifier (e.g., "implementer")
        display_name: Human-readable template name
        description: What this template is for
        category: Category of the template
        variables: Required variables for substitution
        content: Template content with placeholders
        metadata_template: Template for YAML frontmatter
    """

    name: str
    display_name: str
    description: str
    category: TemplateCategory = TemplateCategory.CUSTOM
    variables: list[str] = Field(default_factory=list)
    content: str = ""
    metadata_template: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate template name format."""
        if not v:
            raise ValueError("Template name cannot be empty")
        if not re.match(r"^[a-z][a-z0-9_-]*$", v):
            raise ValueError(
                f"Template name must be lowercase with hyphens/underscores: {v}"
            )
        return v

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, v: list[str]) -> list[str]:
        """Validate variable names."""
        for var in v:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", var):
                raise ValueError(
                    f"Invalid variable name '{var}'. "
                    "Must be a valid Python identifier."
                )
        return v

    def get_required_variables(self) -> list[str]:
        """
        Extract all required variables from template content.

        Returns:
            List of variable names used in templates
        """
        # Find all {{ variable }} patterns
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
        content_vars = set(re.findall(pattern, self.content))

        # Also check metadata template
        metadata_str = str(self.metadata_template)
        metadata_vars = set(re.findall(pattern, metadata_str))

        return sorted(content_vars.union(metadata_vars))

    def render(self, variables: dict[str, Any]) -> str:
        """
        Render template with variable substitution.

        Args:
            variables: Dictionary of variable values

        Returns:
            Rendered content

        Raises:
            ValueError: If required variables are missing
        """
        renderer = TemplateRenderer()
        return renderer.render(self.content, variables)


@dataclass
class RenderedTemplate:
    """
    Result of rendering a template with variables.

    Attributes:
        content: Rendered markdown content
        metadata: Rendered metadata dictionary
        variables: Variables used in rendering
        template: Original template used
    """

    content: str
    metadata: dict[str, Any]
    variables: dict[str, Any]
    template: SkillTemplate


class TemplateRenderer:
    """
    Renders templates with variable substitution.

    Supports Jinja2-style variable placeholders ({{ variable }}).

    Example:
        >>> renderer = TemplateRenderer()
        >>> result = renderer.render("Hello {{ name }}", {"name": "World"})
        >>> print(result)
        'Hello World'
    """

    # Pattern for {{ variable }} placeholders
    VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

    def render(self, template: str, variables: dict[str, Any]) -> str:
        """
        Render a template string with variable substitution.

        Args:
            template: Template string with {{ variable }} placeholders
            variables: Dictionary of variable values

        Returns:
            Rendered string with variables substituted

        Raises:
            ValueError: If a required variable is missing
        """
        # Find all required variables
        required_vars = set(self.VARIABLE_PATTERN.findall(template))
        missing_vars = required_vars - set(variables.keys())

        if missing_vars:
            raise ValueError(
                f"Missing required template variables: {sorted(missing_vars)}"
            )

        # Substitute variables
        result = template

        for var_name, var_value in variables.items():
            placeholder = f"{{{{ {var_name} }}}}"
            result = result.replace(placeholder, str(var_value))

        return result

    def render_dict(
        self, template_dict: dict[str, Any], variables: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Render a dictionary with variable substitution in all string values.

        Args:
            template_dict: Dictionary with template strings
            variables: Dictionary of variable values

        Returns:
            Dictionary with rendered string values
        """
        result = {}

        for key, value in template_dict.items():
            if isinstance(value, str):
                result[key] = self.render(value, variables)
            elif isinstance(value, dict):
                result[key] = self.render_dict(value, variables)
            elif isinstance(value, list):
                result[key] = [
                    self.render(item, variables) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                result[key] = value

        return result

    def render_template(
        self, template: SkillTemplate, variables: dict[str, Any]
    ) -> RenderedTemplate:
        """
        Render a complete SkillTemplate with variables.

        Args:
            template: Template to render
            variables: Dictionary of variable values

        Returns:
            RenderedTemplate with content and metadata

        Raises:
            ValueError: If required variables are missing
        """
        rendered_content = self.render(template.content, variables)
        rendered_metadata = self.render_dict(template.metadata_template, variables)

        return RenderedTemplate(
            content=rendered_content,
            metadata=rendered_metadata,
            variables=variables,
            template=template,
        )


class TemplateLoaderError(Exception):
    """Exception raised for template loading errors."""

    pass


class TemplateLoader:
    """
    Loader for skill templates.

    Manages built-in and custom skill templates, providing access
    to templates by name or category.

    Example:
        >>> loader = TemplateLoader()
        >>> template = loader.get_template("implementer")
        >>> print(template.display_name)
        'Implementer'
    """

    def __init__(self, custom_templates_dir: Optional[Union[str, Path]] = None):
        """
        Initialize the template loader.

        Args:
            custom_templates_dir: Optional directory for custom templates
        """
        self._templates: dict[str, SkillTemplate] = {}
        self._custom_dir = (
            Path(custom_templates_dir).resolve() if custom_templates_dir else None
        )
        self._load_builtin_templates()

        if self._custom_dir and self._custom_dir.exists():
            self._load_custom_templates()

    def _load_builtin_templates(self) -> None:
        """Load built-in templates."""
        for template in BUILTIN_TEMPLATES.values():
            self._templates[template.name] = template

    def _load_custom_templates(self) -> None:
        """Load custom templates from directory."""
        if not self._custom_dir or not self._custom_dir.exists():
            return

        # TODO: Implement custom template loading from YAML/JSON files
        # For now, this is a placeholder for future functionality
        pass

    def get_template(self, name: str) -> Optional[SkillTemplate]:
        """
        Get a template by name.

        Args:
            name: Template name

        Returns:
            SkillTemplate if found, None otherwise
        """
        return self._templates.get(name)

    def list_templates(
        self, category: Optional[TemplateCategory] = None
    ) -> list[SkillTemplate]:
        """
        List all templates, optionally filtered by category.

        Args:
            category: Optional category to filter by

        Returns:
            List of templates
        """
        templates = list(self._templates.values())

        if category:
            templates = [t for t in templates if t.category == category]

        return sorted(templates, key=lambda t: t.name)

    def get_categories(self) -> list[TemplateCategory]:
        """
        Get all template categories in use.

        Returns:
            List of categories
        """
        categories = {t.category for t in self._templates.values()}
        return sorted(categories)

    def add_template(self, template: SkillTemplate) -> None:
        """
        Add a custom template.

        Args:
            template: Template to add

        Raises:
            TemplateLoaderError: If template already exists
        """
        if template.name in self._templates:
            raise TemplateLoaderError(
                f"Template '{template.name}' already exists"
            )

        self._templates[template.name] = template

    def remove_template(self, name: str) -> bool:
        """
        Remove a template.

        Args:
            name: Template name to remove

        Returns:
            True if removed, False if not found
        """
        if name in self._templates:
            del self._templates[name]
            return True
        return False

    def has_template(self, name: str) -> bool:
        """
        Check if a template exists.

        Args:
            name: Template name

        Returns:
            True if template exists
        """
        return name in self._templates

    def __len__(self) -> int:
        """Return number of templates."""
        return len(self._templates)

    def __contains__(self, name: str) -> bool:
        """Check if template exists."""
        return name in self._templates

    def __repr__(self) -> str:
        """Return string representation."""
        return f"TemplateLoader(templates={len(self._templates)})"


# Built-in templates
BUILTIN_TEMPLATES: dict[str, SkillTemplate] = {
    "planner": SkillTemplate(
        name="planner",
        display_name="Planner",
        description="Creates planning and design skills with structured workflow",
        category=TemplateCategory.PLANNING,
        variables=["name", "description"],
        metadata_template={
            "name": "{{ name }}",
            "description": "{{ description }}",
            "version": "1.0.0",
            "triggers": ["task.start"],
            "inputs": ["spec", "task"],
            "outputs": ["plan", "design"],
            "agents": ["claude-code"],
            "enabled": True,
        },
        content="""# {{ name }}

{{ description }}

## Workflow

1. Read and understand the task requirements and specifications
2. Analyze the current codebase structure and patterns
3. Create a detailed implementation plan
4. Identify potential risks and dependencies
5. Design the solution architecture
6. Document expected outputs and success criteria

## Rules

- Follow existing code patterns and conventions
- Consider edge cases and error handling
- Plan for testing and validation
- Document assumptions and constraints
- Break down complex tasks into manageable steps
""",
    ),
    "implementer": SkillTemplate(
        name="implementer",
        display_name="Implementer",
        description="Creates code implementation skills with workflow and rules",
        category=TemplateCategory.WORKFLOW,
        variables=["name", "description"],
        metadata_template={
            "name": "{{ name }}",
            "description": "{{ description }}",
            "version": "1.0.0",
            "triggers": ["implement"],
            "inputs": ["task", "spec"],
            "outputs": ["code", "summary"],
            "agents": ["claude-code"],
            "enabled": True,
        },
        content="""# {{ name }}

{{ description }}

## Workflow

1. Read the task specification and acceptance criteria
2. Analyze the existing codebase structure
3. Implement changes following the task scope
4. Write or update tests as needed
5. Run verification tests locally
6. Document changes and potential issues
7. Create a summary of implementation

## Rules

- Work only within the defined task scope
- Follow existing code patterns and style
- Add tests for new functionality
- Update documentation if applicable
- Handle errors gracefully
- Leave code in a working state
- Ask for clarification if requirements are unclear
""",
    ),
    "reviewer": SkillTemplate(
        name="reviewer",
        display_name="Reviewer",
        description="Creates code review skills with validation checks",
        category=TemplateCategory.REVIEW,
        variables=["name", "description"],
        metadata_template={
            "name": "{{ name }}",
            "description": "{{ description }}",
            "version": "1.0.0",
            "triggers": ["review"],
            "inputs": ["task", "changes"],
            "outputs": ["feedback", "status"],
            "agents": ["claude-code"],
            "enabled": True,
        },
        content="""# {{ name }}

{{ description }}

## Workflow

1. Read the task requirements and acceptance criteria
2. Review all code changes thoroughly
3. Check for:
   - Correctness and logic errors
   - Security vulnerabilities
   - Performance issues
   - Code style and consistency
   - Missing tests or test coverage gaps
   - Documentation completeness
4. Verify all acceptance criteria are met
5. Test the changes if applicable
6. Provide clear, actionable feedback
7. Mark status as approved or needs changes

## Rules

- Be thorough but constructive
- Explain issues clearly with examples
- Suggest improvements when applicable
- Verify test coverage is adequate
- Check for edge cases
- Ensure documentation is updated
- Follow project coding standards
""",
    ),
}


def create_loader(
    custom_templates_dir: Optional[Union[str, Path]] = None,
) -> TemplateLoader:
    """
    Factory function to create a template loader.

    Args:
        custom_templates_dir: Optional directory for custom templates

    Returns:
        Configured TemplateLoader instance

    Example:
        >>> loader = create_loader()
        >>> template = loader.get_template("implementer")
        >>> print(template.display_name)
        'Implementer'
    """
    return TemplateLoader(custom_templates_dir=custom_templates_dir)


def create_renderer() -> TemplateRenderer:
    """
    Factory function to create a template renderer.

    Returns:
        New TemplateRenderer instance

    Example:
        >>> renderer = create_renderer()
        >>> result = renderer.render("Hello {{ name }}", {"name": "World"})
    """
    return TemplateRenderer()
