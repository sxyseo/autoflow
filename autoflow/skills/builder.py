"""
Autoflow Skill Builder Module

Provides interactive skill builder for creating custom skills from templates.
Collects user input through prompts and generates skill definitions.

Usage:
    from autoflow.skills.builder import SkillBuilder, BuilderConfig

    config = BuilderConfig()
    builder = SkillBuilder(config)

    # Interactive building
    skill_path = builder.build_interactive()

    # Or with parameters
    skill_path = builder.build(
        name="MY_CUSTOM_SKILL",
        template="implementer",
        variables={"description": "My custom skill"}
    )
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator

from autoflow.skills.templates import (
    BUILTIN_TEMPLATES,
    TemplateCategory,
    TemplateLoader,
    TemplateRenderer,
)


class BuilderConfig(BaseModel):
    """
    Configuration for the skill builder.

    Attributes:
        output_dir: Default directory for created skills
        overwrite: Whether to overwrite existing skills
        use_defaults: Use default values for prompts
        validate_before_write: Validate skill content before writing
        create_metadata: Include YAML frontmatter in SKILL.md
    """

    output_dir: str = "skills"
    overwrite: bool = False
    use_defaults: bool = False
    validate_before_write: bool = True
    create_metadata: bool = True

    @field_validator("output_dir", mode="before")
    @classmethod
    def expand_output_dir(cls, v: str) -> str:
        """Expand environment variables and user home in output_dir."""
        return os.path.expandvars(os.path.expanduser(v))


class PromptResponse(BaseModel):
    """
    Response from a user prompt.

    Attributes:
        value: The user's input value
        skipped: Whether the user skipped this prompt
        default_used: Whether the default value was used
    """

    value: str
    skipped: bool = False
    default_used: bool = False


class SkillBuilderError(Exception):
    """Exception raised for skill building errors."""

    pass


class SkillBuilder:
    """
    Interactive skill builder for creating custom skills.

    Provides a user-friendly interface for creating new skills from templates.
    Collects required variables through prompts and generates complete skill
    definitions with proper structure and validation.

    Example:
        >>> builder = SkillBuilder()
        >>> skill_path = builder.build_interactive()
        Created skill at: skills/MY_CUSTOM_SKILL/SKILL.md

        >>> # Or with explicit parameters
        >>> skill_path = builder.build(
        ...     name="CODE_REVIEWER",
        ...     template="reviewer",
        ...     variables={"description": "Reviews code changes"}
        ... )
    """

    def __init__(
        self,
        config: Optional[BuilderConfig] = None,
        template_loader: Optional[TemplateLoader] = None,
    ):
        """
        Initialize the skill builder.

        Args:
            config: Optional builder configuration
            template_loader: Optional template loader instance
        """
        self.config = config or BuilderConfig()
        self.template_loader = template_loader or TemplateLoader()
        self.renderer = TemplateRenderer()
        self._prompts_history: list[tuple[str, PromptResponse]] = []

    def build_interactive(
        self,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Interactively build a new skill.

        Prompts the user for all required information:
        1. Skill name (validated format)
        2. Template selection
        3. Template variables

        Args:
            output_dir: Optional output directory (overrides config)

        Returns:
            Path to the created skill directory

        Raises:
            SkillBuilderError: If building fails
        """
        print("\n" + "=" * 60)
        print("Autoflow Custom Skill Builder")
        print("=" * 60 + "\n")

        # Step 1: Get skill name
        name = self._prompt_skill_name()

        # Step 2: Select template
        template_name = self._prompt_template_selection()
        template = self.template_loader.get_template(template_name)

        if not template:
            raise SkillBuilderError(f"Template '{template_name}' not found")

        # Step 3: Collect variables
        variables = self._collect_template_variables(template, name)

        # Step 4: Build skill
        output_path = self.build(
            name=name,
            template=template_name,
            variables=variables,
            output_dir=output_dir,
        )

        print(f"\n✓ Skill created at: {output_path}")
        return output_path

    def build(
        self,
        name: str,
        template: str,
        variables: dict[str, Any],
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        """
        Build a skill with explicit parameters.

        Args:
            name: Skill name (UPPER_SNAKE_CASE)
            template: Template name to use
            variables: Template variables
            output_dir: Optional output directory (overrides config)

        Returns:
            Path to the created skill directory

        Raises:
            SkillBuilderError: If building fails
        """
        # Validate skill name
        try:
            self._validate_skill_name(name)
        except ValueError as e:
            raise SkillBuilderError(str(e)) from e

        # Get template
        template_obj = self.template_loader.get_template(template)
        if not template_obj:
            raise SkillBuilderError(f"Template '{template}' not found")

        # Prepare variables
        prepared_vars = self._prepare_variables(template_obj, name, variables)

        # Render template
        try:
            rendered = self.renderer.render_template(template_obj, prepared_vars)
        except ValueError as e:
            raise SkillBuilderError(f"Template rendering failed: {e}") from e

        # Determine output directory
        if output_dir is None:
            output_dir = self.config.output_dir

        output_path = Path(output_dir) / name

        # Check if skill already exists
        if output_path.exists() and not self.config.overwrite:
            raise SkillBuilderError(
                f"Skill directory already exists: {output_path}. "
                f"Use overwrite=True to replace it."
            )

        # Create skill file
        self.create_skill_file(
            output_dir=str(output_path.parent),
            name=name,
            content=rendered.content,
            metadata=rendered.metadata,
        )

        # Return absolute path
        return output_path.resolve()

    def create_skill_file(
        self,
        output_dir: Union[str, Path],
        name: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Path:
        """
        Create a skill file with content and optional metadata.

        Args:
            output_dir: Directory to create skill in
            name: Skill name
            content: Skill content (markdown)
            metadata: Optional YAML frontmatter metadata

        Returns:
            Path to the created skill directory

        Raises:
            SkillBuilderError: If file creation fails
        """
        output_path = Path(output_dir) / name

        try:
            # Create directory
            output_path.mkdir(parents=True, exist_ok=True)

            # Create SKILL.md
            skill_file = output_path / "SKILL.md"

            with open(skill_file, "w", encoding="utf-8") as f:
                # Write metadata frontmatter if enabled
                if self.config.create_metadata and metadata:
                    f.write("---\n")
                    import yaml

                    yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
                    f.write("---\n\n")

                # Write content
                f.write(content)

            return output_path

        except OSError as e:
            raise SkillBuilderError(f"Failed to create skill file: {e}") from e

    def _prompt_skill_name(self) -> str:
        """
        Prompt user for skill name with validation.

        Returns:
            Validated skill name in UPPER_SNAKE_CASE
        """
        while True:
            name = input(
                "\nSkill name (UPPER_SNAKE_CASE, e.g., MY_CUSTOM_SKILL): "
            ).strip()

            if not name:
                print("❌ Name cannot be empty")
                continue

            try:
                self._validate_skill_name(name)
                return name.upper()
            except ValueError as e:
                print(f"❌ {e}")

    def _prompt_template_selection(self) -> str:
        """
        Prompt user to select a template.

        Returns:
            Selected template name
        """
        templates = self.template_loader.list_templates()

        print("\nAvailable templates:\n")

        categories = {}
        for template in templates:
            if template.category not in categories:
                categories[template.category] = []
            categories[template.category].append(template)

        for category, cat_templates in categories.items():
            print(f"  {category.value.upper()}")
            for template in cat_templates:
                print(f"    {template.name:12} - {template.display_name}")
            print()

        while True:
            choice = input("Select template: ").strip().lower()

            if not choice:
                print("❌ Please select a template")
                continue

            if self.template_loader.has_template(choice):
                return choice

            print(f"❌ Unknown template '{choice}'")

    def _collect_template_variables(
        self,
        template,
        skill_name: str,
    ) -> dict[str, Any]:
        """
        Collect variable values from user for template.

        Args:
            template: Template to collect variables for
            skill_name: Skill name (used for defaults)

        Returns:
            Dictionary of variable values
        """
        variables = {}
        required = template.get_required_variables()

        if not required:
            return variables

        print(f"\nTemplate variables for '{template.display_name}':\n")

        for var_name in required:
            # Provide sensible defaults
            default = self._get_default_for_variable(var_name, skill_name, template)

            if self.config.use_defaults:
                value = default
                default_used = True
            else:
                prompt_text = f"  {var_name}"
                if default:
                    prompt_text += f" [{default}]"

                user_input = input(prompt_text + ": ").strip()

                if user_input:
                    value = user_input
                    default_used = False
                else:
                    value = default
                    default_used = True

            variables[var_name] = value

            # Record response
            response = PromptResponse(value=value, default_used=default_used)
            self._prompts_history.append((var_name, response))

        return variables

    def _get_default_for_variable(
        self,
        var_name: str,
        skill_name: str,
        template,
    ) -> str:
        """
        Get default value for a template variable.

        Args:
            var_name: Variable name
            skill_name: Skill name
            template: Template being used

        Returns:
            Default value for the variable
        """
        # Common variable defaults
        # For single-word display names like "Test", use "Test Template"
        display_name = template.display_name
        if len(display_name.split()) == 1:
            display_name = f"{display_name} Template"

        defaults = {
            "name": skill_name,
            "description": f"Custom {display_name.lower()} skill",
        }

        return defaults.get(var_name, "")

    def _prepare_variables(
        self,
        template,
        skill_name: str,
        user_variables: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Prepare complete variable set for template rendering.

        Merges user variables with smart defaults.

        Args:
            template: Template being used
            skill_name: Skill name
            user_variables: Variables provided by user

        Returns:
            Complete variable dictionary
        """
        required = template.get_required_variables()
        variables = {}

        for var_name in required:
            if var_name in user_variables:
                variables[var_name] = user_variables[var_name]
            else:
                # Use default value
                variables[var_name] = self._get_default_for_variable(
                    var_name, skill_name, template
                )

        return variables

    def _validate_skill_name(self, name: str) -> None:
        """
        Validate skill name format.

        Args:
            name: Skill name to validate

        Raises:
            ValueError: If name is invalid
        """
        if not name:
            raise ValueError("Skill name cannot be empty")

        if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
            raise ValueError(
                f"Skill name must be UPPER_SNAKE_CASE (e.g., MY_CUSTOM_SKILL): {name}"
            )

    def get_prompt_history(self) -> list[tuple[str, PromptResponse]]:
        """
        Get history of prompts and responses from the session.

        Returns:
            List of (variable_name, response) tuples
        """
        return self._prompts_history.copy()

    def list_available_templates(self) -> list[str]:
        """
        List all available template names.

        Returns:
            List of template names
        """
        return [t.name for t in self.template_loader.list_templates()]

    def get_template_info(self, template_name: str) -> Optional[dict[str, Any]]:
        """
        Get information about a template.

        Args:
            template_name: Name of the template

        Returns:
            Dictionary with template info or None if not found
        """
        template = self.template_loader.get_template(template_name)

        if not template:
            return None

        return {
            "name": template.name,
            "display_name": template.display_name,
            "description": template.description,
            "category": template.category.value,
            "variables": template.get_required_variables(),
        }


def create_builder(
    config: Optional[BuilderConfig] = None,
    template_loader: Optional[TemplateLoader] = None,
) -> SkillBuilder:
    """
    Factory function to create a skill builder.

    Args:
        config: Optional builder configuration
        template_loader: Optional template loader instance

    Returns:
        Configured SkillBuilder instance

    Example:
        >>> builder = create_builder()
        >>> skill_path = builder.build_interactive()
    """
    return SkillBuilder(config=config, template_loader=template_loader)
