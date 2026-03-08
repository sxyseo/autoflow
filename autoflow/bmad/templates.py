"""BMAD Template Loader module.

This module provides functionality for loading BMAD templates and schema validation.
It supports loading role-based markdown templates and JSON schema definitions for
BMAD checkpoint configurations.

Example:
    from autoflow.bmad.templates import load_bmad_template, load_bmad_schema

    # Load a role template
    template = load_bmad_template("reviewer")

    # Load the schema
    schema = load_bmad_schema()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Default paths (can be overridden by root parameter)
def get_default_root() -> Path:
    """Get the default project root directory."""
    # Start from current file and navigate to project root
    # File is at: <project_root>/autoflow/bmad/templates.py
    # Go up 3 levels: bmad/ -> autoflow/ -> project_root
    current_file = Path(__file__).resolve()
    return current_file.parent.parent.parent


def get_bmad_templates_dir(root: Path | str | None = None) -> Path:
    """Get the BMAD templates directory.

    Args:
        root: Optional project root directory. If None, uses default.

    Returns:
        Path to the BMAD templates directory.
    """
    if root is None:
        root = get_default_root()
    elif isinstance(root, str):
        root = Path(root)

    return root / "templates" / "bmad"


def get_schema_path(root: Path | str | None = None) -> Path:
    """Get the BMAD schema file path.

    Args:
        root: Optional project root directory. If None, uses default.

    Returns:
        Path to the schema.json file.
    """
    templates_dir = get_bmad_templates_dir(root)
    return templates_dir / "schema.json"


def get_project_bmad_dir(root: Path | str | None = None) -> Path | None:
    """Get the project-level BMAD override directory.

    Checks for a .autoflow/bmad/ directory in the project root for
    project-specific template overrides.

    Args:
        root: Optional project root directory. If None, uses default.

    Returns:
        Path to the project BMAD directory if it exists, None otherwise.
    """
    if root is None:
        root = get_default_root()
    elif isinstance(root, str):
        root = Path(root)

    project_bmad_dir = root / ".autoflow" / "bmad"
    return project_bmad_dir if project_bmad_dir.exists() else None


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file and return its contents.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON data as a dictionary.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def load_bmad_template(role: str, root: Path | str | None = None) -> str:
    """Load a BMAD template for a specific role.

    BMAD templates are markdown files that define role-specific instructions
    for agents in the Breakdown, Make, and Debug framework.

    This function supports project-level template overrides. If a project-specific
    template exists in .autoflow/bmad/{role}.md, it will be used instead of the
    default template.

    Args:
        role: The role name (e.g., "reviewer", "writer", "maintainer").
        root: Optional project root directory. If None, uses default.

    Returns:
        The template content as a string.

    Raises:
        FileNotFoundError: If the template file doesn't exist in either location.

    Example:
        >>> template = load_bmad_template("reviewer")
        >>> print(template)
        # BMAD Frame: Reviewer
        ...

        >>> # Use project-specific templates
        >>> template = load_bmad_template("writer", root=".")
        >>> print(template)
    """
    # First check for project-level override
    project_bmad_dir = get_project_bmad_dir(root)
    if project_bmad_dir is not None:
        project_template_path = project_bmad_dir / f"{role}.md"
        if project_template_path.exists():
            return project_template_path.read_text(encoding="utf-8")

    # Fall back to default templates
    templates_dir = get_bmad_templates_dir(root)
    template_path = templates_dir / f"{role}.md"

    if not template_path.exists():
        raise FileNotFoundError(
            f"BMAD template not found for role '{role}' at {template_path}"
        )

    return template_path.read_text(encoding="utf-8")


def load_bmad_schema(root: Path | str | None = None) -> dict[str, Any]:
    """Load the BMAD schema definition.

    The schema defines the structure for BMAD checkpoint configuration files,
    including required fields, artifact specifications, and validation rules.

    Args:
        root: Optional project root directory. If None, uses default.

    Returns:
        The schema as a dictionary.

    Raises:
        FileNotFoundError: If the schema file doesn't exist.
        json.JSONDecodeError: If the schema file contains invalid JSON.

    Example:
        >>> schema = load_bmad_schema()
        >>> print(schema["title"])
        BMAD Checkpoint Configuration
    """
    schema_path = get_schema_path(root)

    if not schema_path.exists():
        raise FileNotFoundError(
            f"BMAD schema not found at {schema_path}"
        )

    return read_json(schema_path)


def list_bmad_templates(root: Path | str | None = None) -> list[str]:
    """List all available BMAD templates.

    Args:
        root: Optional project root directory. If None, uses default.

    Returns:
        List of role names that have templates available.

    Example:
        >>> templates = list_bmad_templates()
        >>> print(templates)
        ['implementation-runner', 'maintainer', 'reviewer', 'spec-writer', 'task-graph-manager']
    """
    templates_dir = get_bmad_templates_dir(root)

    if not templates_dir.exists():
        return []

    return [
        path.stem
        for path in templates_dir.glob("*.md")
        if path.is_file()
    ]


def validate_bmad_config(
    config: dict[str, Any],
    schema: dict[str, Any] | None = None,
    root: Path | str | None = None,
) -> list[str]:
    """Validate a BMAD configuration against the schema.

    Performs basic schema validation to ensure the configuration follows
    the expected structure for BMAD checkpoint definitions.

    Args:
        config: The configuration dictionary to validate.
        schema: Optional schema to validate against. If None, loads default schema.
        root: Optional project root directory. If None, uses default.

    Returns:
        List of validation error messages. Empty list if validation passes.

    Example:
        >>> config = {
        ...     "checkpoints": [
        ...         {
        ...             "from_role": "writer",
        ...             "to_role": "reviewer",
        ...             "artifacts": []
        ...         }
        ...     ]
        ... }
        >>> errors = validate_bmad_config(config)
        >>> print(errors)
        []
    """
    errors: list[str] = []

    # Load schema if not provided
    if schema is None:
        try:
            schema = load_bmad_schema(root)
        except FileNotFoundError:
            errors.append("BMAD schema file not found")
            return errors

    # Basic structure validation
    if not isinstance(config, dict):
        errors.append("Configuration must be a dictionary")
        return errors

    # Check for required top-level fields
    if "checkpoints" not in config:
        errors.append("Missing required field: 'checkpoints'")
        return errors

    checkpoints = config["checkpoints"]

    # Validate checkpoints is a list
    if not isinstance(checkpoints, list):
        errors.append("'checkpoints' must be a list")
        return errors

    # Validate each checkpoint
    for idx, checkpoint in enumerate(checkpoints):
        if not isinstance(checkpoint, dict):
            errors.append(f"Checkpoint {idx}: must be a dictionary")
            continue

        # Check required fields for checkpoint
        if "from_role" not in checkpoint:
            errors.append(f"Checkpoint {idx}: missing required field 'from_role'")
        if "to_role" not in checkpoint:
            errors.append(f"Checkpoint {idx}: missing required field 'to_role'")

        # Validate artifacts if present
        if "artifacts" in checkpoint:
            artifacts = checkpoint["artifacts"]
            if not isinstance(artifacts, list):
                errors.append(f"Checkpoint {idx}: 'artifacts' must be a list")
            else:
                for artifact_idx, artifact in enumerate(artifacts):
                    if not isinstance(artifact, dict):
                        errors.append(
                            f"Checkpoint {idx}, artifact {artifact_idx}: must be a dictionary"
                        )
                        continue

                    # Check required artifact fields
                    if "name" not in artifact:
                        errors.append(
                            f"Checkpoint {idx}, artifact {artifact_idx}: missing required field 'name'"
                        )
                    if "type" not in artifact:
                        errors.append(
                            f"Checkpoint {idx}, artifact {artifact_idx}: missing required field 'type'"
                        )
                    if "path" not in artifact:
                        errors.append(
                            f"Checkpoint {idx}, artifact {artifact_idx}: missing required field 'path'"
                        )

                    # Validate artifact type enum
                    if "type" in artifact:
                        valid_types = {
                            "file",
                            "directory",
                            "documentation",
                            "test",
                            "config",
                            "custom",
                        }
                        if artifact["type"] not in valid_types:
                            errors.append(
                                f"Checkpoint {idx}, artifact {artifact_idx}: invalid type '{artifact['type']}'"
                            )

                    # Validate content_check enum if present
                    if "content_check" in artifact:
                        valid_checks = {"not_empty", "valid_json", "valid_yaml"}
                        if artifact["content_check"] not in valid_checks:
                            errors.append(
                                f"Checkpoint {idx}, artifact {artifact_idx}: invalid content_check '{artifact['content_check']}'"
                            )

    return errors


def get_template_metadata(
    role: str,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Extract metadata from a BMAD template.

    Parses the template file and extracts metadata such as title,
    description, and role-specific instructions.

    Args:
        role: The role name.
        root: Optional project root directory. If None, uses default.

    Returns:
        Dictionary containing template metadata.

    Example:
        >>> metadata = get_template_metadata("reviewer")
        >>> print(metadata["role"])
        reviewer
    """
    try:
        template = load_bmad_template(role, root)
    except FileNotFoundError:
        return {
            "role": role,
            "exists": False,
            "error": "Template not found",
        }

    lines = template.split("\n")

    # Extract title (first heading)
    title = ""
    for line in lines:
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break

    # Extract description (first non-empty, non-heading line after title)
    description = ""
    found_title = False
    for line in lines:
        if line.startswith("#"):
            found_title = True
            continue
        if found_title and line.strip():
            description = line.strip()
            break

    return {
        "role": role,
        "exists": True,
        "title": title,
        "description": description,
        "line_count": len(lines),
    }
