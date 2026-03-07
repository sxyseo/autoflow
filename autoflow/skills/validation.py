"""
Autoflow Skill Validation Module

Provides comprehensive validation for skill content structure,
required sections, and markdown formatting.

Usage:
    from autoflow.skills.validation import SkillValidator, ValidationResult

    validator = SkillValidator()
    result = validator.validate_content(skill_content)

    if result.is_valid:
        print("Skill is valid!")
    else:
        for error in result.errors:
            print(f"Error: {error}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationError:
    """
    Represents a single validation error or warning.

    Attributes:
        message: Human-readable error description
        severity: Error severity level
        line_number: Optional line number where error occurred
        section: Optional section name where error occurred
    """

    def __init__(
        self,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        line_number: Optional[int] = None,
        section: Optional[str] = None,
    ):
        self.message = message
        self.severity = severity
        self.line_number = line_number
        self.section = section

    def __str__(self) -> str:
        """Return string representation."""
        parts = [f"[{self.severity.value.upper()}]"]
        if self.section:
            parts.append(f"section '{self.section}'")
        if self.line_number:
            parts.append(f"line {self.line_number}")
        parts.append(self.message)
        return ": ".join(parts)

    def __repr__(self) -> str:
        """Return detailed representation."""
        return (
            f"ValidationError(message={self.message!r}, "
            f"severity={self.severity.value}, "
            f"line={self.line_number}, section={self.section!r})"
        )


@dataclass
class ValidationResult:
    """
    Result of skill validation.

    Contains all validation errors, warnings, and overall status.

    Attributes:
        is_valid: Whether the skill passes all required validations
        errors: List of validation errors
        warnings: List of validation warnings
        missing_sections: List of required section names that are missing
        present_sections: List of section names found in the skill
    """

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    present_sections: list[str] = field(default_factory=list)

    def add_error(
        self,
        message: str,
        line_number: Optional[int] = None,
        section: Optional[str] = None,
    ) -> None:
        """Add an error to the result."""
        error = ValidationError(
            message=message,
            severity=ValidationSeverity.ERROR,
            line_number=line_number,
            section=section,
        )
        self.errors.append(error)
        self.is_valid = False

    def add_warning(
        self,
        message: str,
        line_number: Optional[int] = None,
        section: Optional[str] = None,
    ) -> None:
        """Add a warning to the result."""
        warning = ValidationError(
            message=message,
            severity=ValidationSeverity.WARNING,
            line_number=line_number,
            section=section,
        )
        self.warnings.append(warning)

    def get_all_issues(self) -> list[ValidationError]:
        """Get all validation issues (errors and warnings)."""
        return self.errors + self.warnings

    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"ValidationResult(is_valid={self.is_valid}, "
            f"errors={len(self.errors)}, warnings={len(self.warnings)}, "
            f"sections={len(self.present_sections)}/{len(self.missing_sections) + len(self.present_sections)})"
        )


class SkillValidator:
    """
    Validator for skill content and structure.

    The SkillValidator checks skill definitions for:
    - Required sections (Role/Title, Workflow)
    - Proper markdown formatting
    - Section structure and organization
    - Content completeness

    Example:
        >>> validator = SkillValidator()
        >>> result = validator.validate_content(skill_content)
        >>> if result.is_valid:
        ...     print("Skill is valid!")
        ... else:
        ...     for error in result.errors:
        ...         print(error)

    Attributes:
        required_sections: Set of section names that must be present
        optional_sections: Set of recognized optional section names
    """

    # Default required sections
    DEFAULT_REQUIRED_SECTIONS = {"## Workflow"}

    # Recognized optional sections
    OPTIONAL_SECTIONS = {
        "## Role",
        "## Description",
        "## Rules",
        "## Examples",
        "## Triggers",
        "## Inputs",
        "## Outputs",
        "## Notes",
        "## Configuration",
        "## Dependencies",
    }

    # Pattern to match markdown headers (## Section Name)
    HEADER_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)

    def __init__(
        self,
        required_sections: Optional[set[str]] = None,
        optional_sections: Optional[set[str]] = None,
    ):
        """
        Initialize the skill validator.

        Args:
            required_sections: Set of section names that must be present
                              (defaults to ## Workflow)
            optional_sections: Set of recognized optional section names
                              (defaults to standard sections)
        """
        self.required_sections = required_sections or self.DEFAULT_REQUIRED_SECTIONS.copy()
        self.optional_sections = optional_sections or self.OPTIONAL_SECTIONS.copy()

    def validate_content(self, content: str) -> ValidationResult:
        """
        Validate skill content for structure and required sections.

        Args:
            content: Skill markdown content to validate

        Returns:
            ValidationResult with validation status and any issues found
        """
        result = ValidationResult(is_valid=True)

        # Check if content is empty
        if not content or not content.strip():
            result.add_error("Skill content is empty")
            return result

        # Extract all sections
        sections = self._extract_sections(content)
        result.present_sections = list(sections.keys())

        # Check for required sections
        missing = self.required_sections - set(sections.keys())
        result.missing_sections = list(missing)

        if missing:
            for section in missing:
                result.add_error(
                    f"Required section '{section}' is missing",
                    section=section
                )

        # Validate section structure
        for section_name, section_content in sections.items():
            self._validate_section(section_name, section_content, result)

        # Check for unknown sections (warning only)
        for section_name in sections.keys():
            normalized = section_name
            if normalized not in self.required_sections and normalized not in self.optional_sections:
                result.add_warning(
                    f"Unknown section '{section_name}' - may be a typo",
                    section=section_name
                )

        return result

    def validate_structure(
        self,
        content: str,
        require_title: bool = False,
    ) -> ValidationResult:
        """
        Validate skill markdown structure (headers and formatting).

        Args:
            content: Skill markdown content to validate
            require_title: Whether a top-level title (#) is required

        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult(is_valid=True)

        if not content or not content.strip():
            result.add_error("Content is empty")
            return result

        lines = content.split("\n")
        found_sections = []

        # Check for top-level title
        if require_title:
            has_title = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("##"):
                    has_title = True
                    break
            if not has_title:
                result.add_error("Skill must have a top-level title (# Title)")

        # Validate section headers and extract sections
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Check for h3 headers (### Subsection) first, before h2
            if stripped.startswith("###"):
                if not re.match(r"^###\s+\S", stripped):
                    result.add_error(
                        "Invalid subsection header format (use '### Subsection Name')",
                        line_number=i,
                    )

            # Check for h2 headers (## Section Name)
            elif stripped.startswith("##"):
                # Check header format - must have space after ##
                if not re.match(r"^##\s+\S", stripped):
                    result.add_error(
                        "Invalid section header format (use '## Section Name')",
                        line_number=i,
                    )
                else:
                    # Extract section name
                    section_name = stripped[2:].strip()
                    found_sections.append((i, section_name))

        # Check for duplicate sections
        section_names = [name for _, name in found_sections]
        seen = set()
        for line_num, section_name in found_sections:
            if section_name in seen:
                result.add_error(
                    f"Duplicate section '{section_name}' found",
                    line_number=line_num,
                    section=f"## {section_name}",
                )
            seen.add(section_name)

        # Check that content has at least one section
        if not found_sections:
            result.add_warning(
                "No sections found - skill should have at least one ## section"
            )

        return result

    def validate_workflow(self, workflow_content: str) -> ValidationResult:
        """
        Validate workflow section for proper numbered list format.

        Args:
            workflow_content: Content of the workflow section

        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult(is_valid=True)

        if not workflow_content or not workflow_content.strip():
            result.add_error("Workflow section is empty", section="## Workflow")
            return result

        lines = workflow_content.strip().split("\n")

        # Check for numbered list
        has_numbered_list = False
        expected_number = 1

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for numbered list item
            match = re.match(r"^(\d+)\.\s+", stripped)
            if match:
                has_numbered_list = True
                number = int(match.group(1))
                if number != expected_number:
                    result.add_warning(
                        f"Workflow step numbers should be sequential (expected {expected_number}, found {number})",
                        section="## Workflow"
                    )
                expected_number = number + 1

        if not has_numbered_list:
            result.add_warning(
                "Workflow should use numbered list format (1. Step, 2. Step, ...)",
                section="## Workflow"
            )

        return result

    def _extract_sections(self, content: str) -> dict[str, str]:
        """
        Extract all sections from markdown content.

        Args:
            content: Markdown content

        Returns:
            Dictionary mapping section names to their content
        """
        sections: dict[str, str] = {}

        # Find all headers
        matches = list(self.HEADER_PATTERN.finditer(content))

        for i, match in enumerate(matches):
            section_name = f"## {match.group(1).strip()}"
            start_pos = match.end()

            # Find end position (next header or end of content)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(content)

            # Extract section content
            section_content = content[start_pos:end_pos].strip()
            sections[section_name] = section_content

        return sections

    def _validate_section(
        self,
        section_name: str,
        section_content: str,
        result: ValidationResult,
    ) -> None:
        """
        Validate a single section's content.

        Args:
            section_name: Name of the section
            section_content: Content of the section
            result: ValidationResult to add errors to
        """
        # Check if section is empty
        if not section_content or not section_content.strip():
            # Workflow section shouldn't be empty
            if section_name in self.required_sections:
                result.add_error(
                    f"Section '{section_name}' is empty",
                    section=section_name
                )
            else:
                result.add_warning(
                    f"Section '{section_name}' is empty",
                    section=section_name
                )

        # Section-specific validation
        if section_name == "## Workflow":
            workflow_result = self.validate_workflow(section_content)
            if workflow_result.has_errors():
                result.errors.extend(workflow_result.errors)
                result.is_valid = False
            if workflow_result.has_warnings():
                result.warnings.extend(workflow_result.warnings)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"SkillValidator(required={len(self.required_sections)}, "
            f"optional={len(self.optional_sections)})"
        )


def create_validator(
    required_sections: Optional[list[str]] = None,
    optional_sections: Optional[list[str]] = None,
) -> SkillValidator:
    """
    Factory function to create a configured skill validator.

    Args:
        required_sections: List of required section names
        optional_sections: List of optional section names

    Returns:
        Configured SkillValidator instance

    Example:
        >>> validator = create_validator(
        ...     required_sections=["## Workflow", "## Role"],
        ...     optional_sections=["## Rules", "## Examples"]
        ... )
        >>> result = validator.validate_content(content)
    """
    return SkillValidator(
        required_sections=set(required_sections) if required_sections else None,
        optional_sections=set(optional_sections) if optional_sections else None,
    )
