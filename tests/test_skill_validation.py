"""
Unit Tests for Skill Validation

Tests the ValidationError, ValidationResult, and SkillValidator classes
for validating skill content structure, required sections, and formatting.

These tests ensure the validation system properly detects issues and
provides helpful feedback for skill authors.
"""

from __future__ import annotations

import re

import pytest

from autoflow.skills.validation import (
    ValidationError,
    ValidationResult,
    ValidationSeverity,
    create_validator,
    SkillValidator,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def valid_skill_content() -> str:
    """Return valid skill content with all standard sections."""
    return """## Role

You are a helpful assistant.

## Workflow

1. First step
2. Second step
3. Third step

## Examples

Example input and output.
"""


@pytest.fixture
def minimal_skill_content() -> str:
    """Return minimal valid skill content."""
    return """## Workflow

1. Do something
2. Do something else
"""


@pytest.fixture
def empty_content() -> str:
    """Return empty content."""
    return ""


@pytest.fixture
def whitespace_only_content() -> str:
    """Return content with only whitespace."""
    return "   \n\n  \t  \n"


@pytest.fixture
def invalid_workflow_content() -> str:
    """Return skill with invalid workflow formatting."""
    return """## Workflow

- Bullet point instead of numbers
- Another bullet point
"""


@pytest.fixture
def missing_required_section_content() -> str:
    """Return skill without required workflow section."""
    return """## Role

This is a role description.

## Examples

Some examples here.
"""


@pytest.fixture
def duplicate_sections_content() -> str:
    """Return skill with duplicate sections."""
    return """## Role

First role section.

## Workflow

1. Step one

## Role

Duplicate role section.
"""


@pytest.fixture
def invalid_header_format_content() -> str:
    """Return skill with invalid header formats."""
    return """##Workflow

Missing space after hashes.

###No space here either

## Proper Header

This one is correct.
"""


@pytest.fixture
def empty_section_content() -> str:
    """Return skill with empty sections."""
    return """## Role

## Workflow

1. Step one

## Examples

"""


@pytest.fixture
def unknown_section_content() -> str:
    """Return skill with unknown/non-standard section."""
    return """## Workflow

1. Do the thing

## UnknownSection

This section is not in the standard list.
"""


@pytest.fixture
def non_sequential_workflow() -> str:
    """Return workflow with non-sequential numbering."""
    return """## Workflow

1. First step
2. Second step
5. Fifth step (skipped numbers)
3. Third step
"""


# ============================================================================
# ValidationError Tests
# ============================================================================


class TestValidationError:
    """Tests for ValidationError model."""

    def test_error_init_default(self) -> None:
        """Test error initialization with defaults."""
        error = ValidationError("Something went wrong")

        assert error.message == "Something went wrong"
        assert error.severity == ValidationSeverity.ERROR
        assert error.line_number is None
        assert error.section is None

    def test_error_init_full(self) -> None:
        """Test error initialization with all fields."""
        error = ValidationError(
            message="Invalid format",
            severity=ValidationSeverity.WARNING,
            line_number=42,
            section="## Workflow",
        )

        assert error.message == "Invalid format"
        assert error.severity == ValidationSeverity.WARNING
        assert error.line_number == 42
        assert error.section == "## Workflow"

    def test_error_str_error_only(self) -> None:
        """Test string representation with error only."""
        error = ValidationError("Test error")
        str_repr = str(error)

        assert "[ERROR]" in str_repr
        assert "Test error" in str_repr

    def test_error_str_with_section(self) -> None:
        """Test string representation with section."""
        error = ValidationError(
            message="Section is empty",
            section="## Role",
        )
        str_repr = str(error)

        assert "[ERROR]" in str_repr
        assert "section '## Role'" in str_repr
        assert "Section is empty" in str_repr

    def test_error_str_with_line_number(self) -> None:
        """Test string representation with line number."""
        error = ValidationError(
            message="Invalid header",
            line_number=15,
        )
        str_repr = str(error)

        assert "[ERROR]" in str_repr
        assert "line 15" in str_repr
        assert "Invalid header" in str_repr

    def test_error_str_with_all_fields(self) -> None:
        """Test string representation with all fields."""
        error = ValidationError(
            message="Multiple issues",
            severity=ValidationSeverity.WARNING,
            line_number=10,
            section="## Examples",
        )
        str_repr = str(error)

        assert "[WARNING]" in str_repr
        assert "section '## Examples'" in str_repr
        assert "line 10" in str_repr
        assert "Multiple issues" in str_repr

    def test_error_repr(self) -> None:
        """Test detailed representation."""
        error = ValidationError(
            message="Test message",
            severity=ValidationSeverity.INFO,
            line_number=5,
            section="Test Section",
        )
        repr_str = repr(error)

        assert "ValidationError" in repr_str
        assert "Test message" in repr_str
        assert "info" in repr_str
        assert "line=5" in repr_str

    def test_error_severity_enum(self) -> None:
        """Test ValidationSeverity enum values."""
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.INFO.value == "info"


# ============================================================================
# ValidationResult Tests
# ============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_result_init_valid(self) -> None:
        """Test result initialization for valid case."""
        result = ValidationResult(is_valid=True)

        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.missing_sections == []
        assert result.present_sections == []

    def test_result_init_invalid(self) -> None:
        """Test result initialization for invalid case."""
        result = ValidationResult(
            is_valid=False,
            errors=[ValidationError("Error 1")],
            warnings=[ValidationError("Warning 1", severity=ValidationSeverity.WARNING)],
            missing_sections=["## Workflow"],
            present_sections=["## Role"],
        )

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.missing_sections == ["## Workflow"]
        assert result.present_sections == ["## Role"]

    def test_add_error(self) -> None:
        """Test adding an error."""
        result = ValidationResult(is_valid=True)

        result.add_error("Critical error")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Critical error"
        assert result.errors[0].severity == ValidationSeverity.ERROR

    def test_add_error_with_details(self) -> None:
        """Test adding an error with line number and section."""
        result = ValidationResult(is_valid=True)

        result.add_error(
            message="Missing field",
            line_number=10,
            section="## Workflow",
        )

        assert len(result.errors) == 1
        error = result.errors[0]
        assert error.message == "Missing field"
        assert error.line_number == 10
        assert error.section == "## Workflow"

    def test_add_warning(self) -> None:
        """Test adding a warning."""
        result = ValidationResult(is_valid=True)

        result.add_warning("Just a warning")

        assert result.is_valid is True  # Warnings don't affect validity
        assert len(result.warnings) == 1
        assert result.warnings[0].message == "Just a warning"
        assert result.warnings[0].severity == ValidationSeverity.WARNING

    def test_add_warning_with_details(self) -> None:
        """Test adding a warning with details."""
        result = ValidationResult(is_valid=True)

        result.add_warning(
            message="Typo detected",
            line_number=5,
            section="## Role",
        )

        assert len(result.warnings) == 1
        warning = result.warnings[0]
        assert warning.message == "Typo detected"
        assert warning.line_number == 5
        assert warning.section == "## Role"

    def test_get_all_issues(self) -> None:
        """Test getting all issues (errors and warnings)."""
        result = ValidationResult(is_valid=True)

        result.add_error("Error 1")
        result.add_warning("Warning 1")
        result.add_error("Error 2")

        all_issues = result.get_all_issues()

        assert len(all_issues) == 3
        assert len([e for e in all_issues if e.severity == ValidationSeverity.ERROR]) == 2
        assert len([w for w in all_issues if w.severity == ValidationSeverity.WARNING]) == 1

    def test_has_errors_true(self) -> None:
        """Test has_errors returns True when errors exist."""
        result = ValidationResult(is_valid=True)
        result.add_error("Some error")

        assert result.has_errors() is True

    def test_has_errors_false(self) -> None:
        """Test has_errors returns False when no errors."""
        result = ValidationResult(is_valid=True)

        assert result.has_errors() is False

    def test_has_errors_with_warnings_only(self) -> None:
        """Test has_errors returns False with warnings only."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Warning only")

        assert result.has_errors() is False

    def test_has_warnings_true(self) -> None:
        """Test has_warnings returns True when warnings exist."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Warning")

        assert result.has_warnings() is True

    def test_has_warnings_false(self) -> None:
        """Test has_warnings returns False when no warnings."""
        result = ValidationResult(is_valid=True)

        assert result.has_warnings() is False

    def test_result_repr(self) -> None:
        """Test result string representation."""
        result = ValidationResult(
            is_valid=False,
            errors=[ValidationError("E1"), ValidationError("E2")],
            warnings=[ValidationError("W1", severity=ValidationSeverity.WARNING)],
            missing_sections=["## Workflow"],
            present_sections=["## Role", "## Examples"],
        )
        repr_str = repr(result)

        assert "ValidationResult" in repr_str
        assert "is_valid=False" in repr_str
        assert "errors=2" in repr_str
        assert "warnings=1" in repr_str
        assert "sections=2/3" in repr_str  # 2 present, 1 missing


# ============================================================================
# SkillValidator Init Tests
# ============================================================================


class TestSkillValidatorInit:
    """Tests for SkillValidator initialization."""

    def test_init_default(self) -> None:
        """Test validator initialization with defaults."""
        validator = SkillValidator()

        assert validator.required_sections == {"## Workflow"}
        assert "## Role" in validator.optional_sections
        assert "## Examples" in validator.optional_sections

    def test_init_custom_required(self) -> None:
        """Test validator with custom required sections."""
        validator = SkillValidator(
            required_sections={"## Role", "## Workflow", "## Examples"}
        )

        assert len(validator.required_sections) == 3
        assert "## Role" in validator.required_sections
        assert "## Workflow" in validator.required_sections
        assert "## Examples" in validator.required_sections

    def test_init_custom_optional(self) -> None:
        """Test validator with custom optional sections."""
        custom_optional = {"## Custom Section", "## Another Section"}
        validator = SkillValidator(optional_sections=custom_optional)

        assert validator.optional_sections == custom_optional

    def test_init_both_custom(self) -> None:
        """Test validator with both required and optional custom."""
        validator = SkillValidator(
            required_sections={"## Must Have"},
            optional_sections={"## Might Have"},
        )

        assert validator.required_sections == {"## Must Have"}
        assert validator.optional_sections == {"## Might Have"}

    def test_init_empty_required(self) -> None:
        """Test validator with no required sections."""
        validator = SkillValidator(required_sections=set())

        assert len(validator.required_sections) == 0

    def test_validator_repr(self) -> None:
        """Test validator string representation."""
        validator = SkillValidator(
            required_sections={"## Workflow", "## Role"},
            optional_sections={"## Examples", "## Rules"},
        )
        repr_str = repr(validator)

        assert "SkillValidator" in repr_str
        assert "required=2" in repr_str
        assert "optional=2" in repr_str


# ============================================================================
# SkillValidator validate_content Tests
# ============================================================================


class TestSkillValidatorValidateContent:
    """Tests for SkillValidator.validate_content method."""

    def test_validate_valid_content(self, valid_skill_content: str) -> None:
        """Test validation of valid skill content."""
        validator = SkillValidator()
        result = validator.validate_content(valid_skill_content)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.present_sections) == 3

    def test_validate_minimal_content(self, minimal_skill_content: str) -> None:
        """Test validation of minimal but valid content."""
        validator = SkillValidator()
        result = validator.validate_content(minimal_skill_content)

        assert result.is_valid is True
        assert "## Workflow" in result.present_sections

    def test_validate_empty_content(self, empty_content: str) -> None:
        """Test validation of empty content."""
        validator = SkillValidator()
        result = validator.validate_content(empty_content)

        assert result.is_valid is False
        assert result.has_errors()
        assert any("empty" in e.message.lower() for e in result.errors)

    def test_validate_whitespace_only(self, whitespace_only_content: str) -> None:
        """Test validation of whitespace-only content."""
        validator = SkillValidator()
        result = validator.validate_content(whitespace_only_content)

        assert result.is_valid is False
        assert result.has_errors()

    def test_validate_missing_required_section(
        self,
        missing_required_section_content: str,
    ) -> None:
        """Test validation when required section is missing."""
        validator = SkillValidator()
        result = validator.validate_content(missing_required_section_content)

        assert result.is_valid is False
        assert "## Workflow" in result.missing_sections
        assert any("Workflow" in e.message for e in result.errors)

    def test_validate_empty_sections(self, empty_section_content: str) -> None:
        """Test validation with empty sections."""
        validator = SkillValidator()
        result = validator.validate_content(empty_section_content)

        # Role is optional, so empty is warning
        assert any("Role" in w.message and "empty" in w.message.lower()
                   for w in result.warnings)

    def test_validate_unknown_sections(self, unknown_section_content: str) -> None:
        """Test validation with unknown section generates warning."""
        validator = SkillValidator()
        result = validator.validate_content(unknown_section_content)

        # Should have warning about unknown section
        assert any("UnknownSection" in w.message for w in result.warnings)

    def test_validate_extracts_sections(self, valid_skill_content: str) -> None:
        """Test that sections are properly extracted."""
        validator = SkillValidator()
        result = validator.validate_content(valid_skill_content)

        assert "## Role" in result.present_sections
        assert "## Workflow" in result.present_sections
        assert "## Examples" in result.present_sections

    def test_validate_workflow_validates_subsection(
        self,
        valid_skill_content: str,
    ) -> None:
        """Test that workflow section gets special validation."""
        validator = SkillValidator()
        result = validator.validate_content(valid_skill_content)

        # Valid workflow should not have workflow-specific errors
        assert not any("Workflow" in e.section for e in result.errors)


# ============================================================================
# SkillValidator validate_structure Tests
# ============================================================================


class TestSkillValidatorValidateStructure:
    """Tests for SkillValidator.validate_structure method."""

    def test_validate_structure_valid(self, valid_skill_content: str) -> None:
        """Test structure validation for valid content."""
        validator = SkillValidator()
        result = validator.validate_structure(valid_skill_content)

        assert result.is_valid is True

    def test_validate_structure_without_title(self, minimal_skill_content: str) -> None:
        """Test structure validation doesn't require title by default."""
        validator = SkillValidator()
        result = validator.validate_structure(minimal_skill_content)

        assert result.is_valid is True

    def test_validate_structure_requires_title_missing(
        self,
        minimal_skill_content: str,
    ) -> None:
        """Test structure validation with require_title=True when missing."""
        validator = SkillValidator()
        result = validator.validate_structure(
            minimal_skill_content,
            require_title=True,
        )

        assert result.is_valid is False
        assert any("title" in e.message.lower() for e in result.errors)

    def test_validate_structure_requires_title_present(self) -> None:
        """Test structure validation with require_title=True when present."""
        content = """# My Skill Title

## Workflow

1. Do something
"""
        validator = SkillValidator()
        result = validator.validate_structure(content, require_title=True)

        assert result.is_valid is True

    def test_validate_structure_invalid_h2_header(
        self,
        invalid_header_format_content: str,
    ) -> None:
        """Test detection of invalid h2 headers."""
        validator = SkillValidator()
        result = validator.validate_structure(invalid_header_format_content)

        assert result.is_valid is False
        assert any("Invalid section header" in e.message for e in result.errors)

    def test_validate_structure_duplicate_sections(
        self,
        duplicate_sections_content: str,
    ) -> None:
        """Test detection of duplicate sections."""
        validator = SkillValidator()
        result = validator.validate_structure(duplicate_sections_content)

        assert result.is_valid is False
        assert any("Duplicate section" in e.message for e in result.errors)

    def test_validate_structure_no_sections(self) -> None:
        """Test content with no sections generates warning."""
        content = "Just some text without any section headers."
        validator = SkillValidator()
        result = validator.validate_structure(content)

        assert result.has_warnings()
        assert any("No sections found" in w.message for w in result.warnings)

    def test_validate_structure_invalid_h3_header(self) -> None:
        """Test detection of invalid h3 headers."""
        content = """## Workflow

###Invalid header format

### Valid Header

1. Step
"""
        validator = SkillValidator()
        result = validator.validate_structure(content)

        assert result.is_valid is False
        assert any("Invalid subsection" in e.message for e in result.errors)


# ============================================================================
# SkillValidator validate_workflow Tests
# ============================================================================


class TestSkillValidatorValidateWorkflow:
    """Tests for SkillValidator.validate_workflow method."""

    def test_validate_workflow_valid(self) -> None:
        """Test validation of properly formatted workflow."""
        workflow = """1. First step
2. Second step
3. Third step
"""
        validator = SkillValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True

    def test_validate_workflow_empty(self) -> None:
        """Test validation of empty workflow."""
        validator = SkillValidator()
        result = validator.validate_workflow("")

        assert result.is_valid is False
        assert result.has_errors()
        assert any("empty" in e.message.lower() for e in result.errors)

    def test_validate_workflow_whitespace(self) -> None:
        """Test validation of whitespace-only workflow."""
        validator = SkillValidator()
        result = validator.validate_workflow("   \n  \t  ")

        assert result.is_valid is False
        assert result.has_errors()

    def test_validate_workflow_no_numbered_list(self) -> None:
        """Test validation of workflow without numbered list."""
        workflow = """- Bullet point one
- Bullet point two
- Bullet point three
"""
        validator = SkillValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True  # It's valid but has warning
        assert result.has_warnings()
        assert any("numbered list" in w.message for w in result.warnings)

    def test_validate_workflow_non_sequential(self, non_sequential_workflow: str) -> None:
        """Test validation of workflow with non-sequential numbering."""
        validator = SkillValidator()
        result = validator.validate_workflow(non_sequential_workflow)

        assert result.is_valid is True  # Valid but has warning
        assert result.has_warnings()
        assert any("sequential" in w.message for w in result.warnings)

    def test_validate_workflow_with_explanatory_text(self) -> None:
        """Test workflow with explanatory text between steps."""
        workflow = """1. First step

Some explanation here.

2. Second step

More explanation.

3. Third step
"""
        validator = SkillValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_workflow_single_step(self) -> None:
        """Test workflow with single step."""
        workflow = "1. Only step"
        validator = SkillValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True


# ============================================================================
# SkillValidator Private Methods Tests
# ============================================================================


class TestSkillValidatorPrivateMethods:
    """Tests for SkillValidator private methods."""

    def test_extract_sections_simple(self) -> None:
        """Test extracting sections from simple content."""
        content = """## Role

Role content here.

## Workflow

1. Step one
2. Step two
"""
        validator = SkillValidator()
        sections = validator._extract_sections(content)

        assert len(sections) == 2
        assert "## Role" in sections
        assert "## Workflow" in sections
        assert "Role content here" in sections["## Role"]

    def test_extract_sections_preserves_content(self) -> None:
        """Test that section content is properly extracted."""
        content = """## Section One

Content for section one.
With multiple lines.

## Section Two

Content for section two.
"""
        validator = SkillValidator()
        sections = validator._extract_sections(content)

        assert "Content for section one" in sections["## Section One"]
        assert "Content for section two" in sections["## Section Two"]

    def test_extract_sections_no_sections(self) -> None:
        """Test extracting sections when none exist."""
        content = "Just some text without headers."
        validator = SkillValidator()
        sections = validator._extract_sections(content)

        assert len(sections) == 0

    def test_extract_sections_h3_headers_ignored(self) -> None:
        """Test that h3 headers don't create sections."""
        content = """## Main Section

Main content.

### Subsection

Subsection content.

## Another Main

More content.
"""
        validator = SkillValidator()
        sections = validator._extract_sections(content)

        # Should only have h2 sections, not h3
        assert len(sections) == 2
        assert "## Main Section" in sections
        assert "## Another Main" in sections
        assert "### Subsection" not in sections


# ============================================================================
# create_validator Factory Function Tests
# ============================================================================


class TestCreateValidator:
    """Tests for create_validator factory function."""

    def test_create_validator_default(self) -> None:
        """Test creating validator with defaults."""
        validator = create_validator()

        assert isinstance(validator, SkillValidator)
        assert "## Workflow" in validator.required_sections

    def test_create_validator_custom_required(self) -> None:
        """Test creating validator with custom required sections."""
        validator = create_validator(
            required_sections=["## Role", "## Workflow", "## Examples"]
        )

        assert len(validator.required_sections) == 3
        assert "## Role" in validator.required_sections
        assert "## Examples" in validator.required_sections

    def test_create_validator_custom_optional(self) -> None:
        """Test creating validator with custom optional sections."""
        validator = create_validator(
            optional_sections=["## Custom", "## Another"]
        )

        assert "## Custom" in validator.optional_sections
        assert "## Another" in validator.optional_sections

    def test_create_validator_both_custom(self) -> None:
        """Test creating validator with both custom sets."""
        validator = create_validator(
            required_sections=["## Must"],
            optional_sections=["## Maybe"],
        )

        assert validator.required_sections == {"## Must"}
        assert validator.optional_sections == {"## Maybe"}

    def test_create_validator_empty_lists(self) -> None:
        """Test creating validator with empty lists uses defaults."""
        validator = create_validator(
            required_sections=[],
            optional_sections=[],
        )

        # Empty lists should result in default behavior
        assert isinstance(validator, SkillValidator)


# ============================================================================
# Integration and Edge Cases
# ============================================================================


class TestSkillValidatorIntegration:
    """Integration tests for realistic validation scenarios."""

    def test_full_validation_valid_skill(self, valid_skill_content: str) -> None:
        """Test complete validation of valid skill."""
        validator = SkillValidator()

        # Validate content
        content_result = validator.validate_content(valid_skill_content)
        assert content_result.is_valid is True

        # Validate structure
        structure_result = validator.validate_structure(valid_skill_content)
        assert structure_result.is_valid is True

    def test_full_validation_invalid_skill(
        self,
        missing_required_section_content: str,
    ) -> None:
        """Test complete validation of invalid skill."""
        validator = SkillValidator()

        content_result = validator.validate_content(missing_required_section_content)
        assert content_result.is_valid is False
        assert content_result.has_errors()

    def test_validation_with_multiple_issues(self) -> None:
        """Test validation with multiple issues at once."""
        content = """## InvalidWorkflow

- Wrong format
- Still wrong

## EmptySection


"""
        validator = SkillValidator()
        result = validator.validate_content(content)

        # Should have errors for missing required section
        assert result.has_errors()

        # Should have warnings for unknown section and empty section
        assert result.has_warnings()

    def test_validation_case_sensitivity(self) -> None:
        """Test that section matching is case-sensitive."""
        content = """## workflow

1. Lowercase workflow section
"""
        validator = SkillValidator()
        result = validator.validate_content(content)

        # "## workflow" (lowercase) != "## Workflow" (proper case)
        # So it should be marked as unknown and missing required
        assert result.has_errors()
        assert "## Workflow" in result.missing_sections

    def test_validation_with_leading_trailing_spaces(self) -> None:
        """Test validation with extra whitespace."""
        content = """

## Workflow

1. Step one
2. Step two

"""
        validator = SkillValidator()
        result = validator.validate_content(content)

        assert result.is_valid is True

    def test_validation_very_long_workflow(self) -> None:
        """Test validation of workflow with many steps."""
        content = "## Workflow\n\n" + "\n".join(
            f"{i}. Step {i}" for i in range(1, 101)
        )
        validator = SkillValidator()
        result = validator.validate_content(content)

        assert result.is_valid is True

    def test_validation_special_characters_in_content(self) -> None:
        """Test validation with special characters."""
        content = """## Workflow

1. Step with <html> tags
2. Step with {json: "data"}
3. Step with $pecial characters
4. Step with unicode: 你好世界
"""
        validator = SkillValidator()
        result = validator.validate_content(content)

        assert result.is_valid is True

    def test_validation_mixed_header_levels(self) -> None:
        """Test content with mixed header levels."""
        content = """## Workflow

1. Main step

### Substep Details

More details here.

### Another Substep

Even more details.

## Examples

Example content.
"""
        validator = SkillValidator()
        result = validator.validate_content(content)

        assert result.is_valid is True
        assert "## Workflow" in result.present_sections
        assert "## Examples" in result.present_sections
