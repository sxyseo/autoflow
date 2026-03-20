"""
Unit Tests for Slug Validation and Path Traversal Prevention

Tests the validate_slug_safe() function, AutoflowCLI.validate_slug_safe() method,
and related path construction functions (spec_dir, task_file, worktree_path) to
ensure they properly detect and prevent path traversal attacks.

These tests verify that:
1. The validation function correctly identifies dangerous patterns
2. Path construction functions reject unsafe slugs
3. Normal valid slugs continue to work as expected
4. The slugify() function doesn't create dangerous patterns
5. Both the standalone function and AutoflowCLI method work correctly

This is part of the security hardening for CWE-22 (Path Traversal) prevention.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Add parent directory to path to import from scripts module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.autoflow import (
    slugify,
    spec_dir,
    task_file,
    validate_slug_safe,
    worktree_path,
)

from autoflow.autoflow_cli import AutoflowCLI
from autoflow.core.commands import _spec_files
from autoflow.core.commands import _task_file
from autoflow.core.commands import validate_slug_safe as commands_validate_slug_safe


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def safe_slugs() -> list[str]:
    """Return a list of safe, valid slugs for testing."""
    return [
        "simple-spec",
        "feature-123",
        "my-feature-name",
        "a-b-c",
        "test",
        "feature-with-multiple-dashes",
        "spec-with-numbers-123",
    ]


@pytest.fixture
def dangerous_slugs() -> list[tuple[str, str]]:
    """Return a list of dangerous slugs with descriptions of why they're dangerous.

    Returns:
        List of tuples: (dangerous_slug, description_of_why_its_dangerous)
    """
    return [
        ("..", "Parent directory reference"),
        ("../", "Parent directory with slash"),
        ("../etc", "Parent directory traversal"),
        ("../../etc", "Multiple parent directory traversals"),
        ("../etc/passwd", "Parent directory to sensitive file"),
        ("..-..-etc-passwd", "Encoded parent directory with dashes"),
        ("./hidden", "Current directory reference"),
        ("./file", "Current directory with file"),
        ("/etc/passwd", "Absolute path"),
        ("/absolute/path", "Absolute path to directory"),
        ("C:\\Windows\\System32", "Windows absolute path with backslash"),
        ("C:/Windows/System32", "Windows absolute path with forward slash"),
        ("D:\\path", "Windows drive letter path"),
        ("E:/path", "Windows drive letter path with forward slash"),
        ("path\\with\\backslash", "Path with backslash separator"),
        ("path/with/./slash", "Path with current directory reference"),
        ("../path/./etc", "Mixed traversal patterns"),
        ("test\x00null", "Null byte injection"),
        ("safe\x00but-dangerous", "Null byte in middle of string"),
    ]


# ============================================================================
# validate_slug_safe() Tests
# ============================================================================


class TestValidateSlugSafe:
    """Tests for the validate_slug_safe() function."""

    def test_validate_slug_safe_accepts_simple_slugs(self, safe_slugs: list[str]) -> None:
        """Test that validate_slug_safe() accepts normal, safe slugs."""
        for slug in safe_slugs:
            assert validate_slug_safe(slug) is True, f"Should accept safe slug: {slug}"

    def test_validate_slug_safe_rejects_parent_directory(self) -> None:
        """Test that validate_slug_safe() rejects '..' patterns."""
        assert validate_slug_safe("..") is False
        assert validate_slug_safe("../") is False
        assert validate_slug_safe("../etc") is False
        assert validate_slug_safe("../../etc/passwd") is False

    def test_validate_slug_safe_rejects_current_directory(self) -> None:
        """Test that validate_slug_safe() rejects './' patterns."""
        assert validate_slug_safe("./") is False
        assert validate_slug_safe("./hidden") is False
        assert validate_slug_safe("./file") is False

    def test_validate_slug_safe_rejects_absolute_paths(self) -> None:
        """Test that validate_slug_safe() rejects absolute paths."""
        assert validate_slug_safe("/etc/passwd") is False
        assert validate_slug_safe("/absolute/path") is False
        assert validate_slug_safe("/") is False

    def test_validate_slug_safe_rejects_null_bytes(self) -> None:
        """Test that validate_slug_safe() rejects null bytes."""
        assert validate_slug_safe("test\x00null") is False
        assert validate_slug_safe("\x00") is False

    def test_validate_slug_safe_rejects_backslash(self) -> None:
        """Test that validate_slug_safe() rejects backslash separators."""
        assert validate_slug_safe("path\\with\\backslash") is False
        assert validate_slug_safe("C:\\Windows\\System32") is False

    def test_validate_slug_safe_rejects_drive_letters(self) -> None:
        """Test that validate_slug_safe() rejects Windows drive letters."""
        assert validate_slug_safe("C:") is False
        assert validate_slug_safe("D:path") is False
        assert validate_slug_safe("E:/path") is False

    def test_validate_slug_safe_rejects_encoded_traversal(self) -> None:
        """Test that validate_slug_safe() rejects encoded traversal patterns."""
        # Even when encoded with dashes, '..' should be rejected
        assert validate_slug_safe("..-..-etc") is False
        assert validate_slug_safe("..-..-..-etc-passwd") is False

    def test_validate_slug_safe_empty_string(self) -> None:
        """Test that validate_slug_safe() handles empty string."""
        # Empty string should be safe (though it may fail elsewhere)
        assert validate_slug_safe("") is True

    def test_validate_slug_safe_single_character(self) -> None:
        """Test that validate_slug_safe() handles single character slugs."""
        assert validate_slug_safe("a") is True
        assert validate_slug_safe("-") is True  # Single dash is safe
        assert validate_slug_safe(".") is True  # Single dot is safe (not "..")

    def test_validate_slug_safe_rejects_mixed_separators(self) -> None:
        """Test that validate_slug_safe() rejects mixed separator patterns."""
        # Mixed forward and backward slashes
        assert validate_slug_safe("../..\\etc") is False
        assert validate_slug_safe("..\\../etc") is False
        assert validate_slug_safe("/..\\path") is False
        assert validate_slug_safe("\\../path") is False

    def test_validate_slug_safe_rejects_whitespace_traversal(self) -> None:
        """Test that validate_slug_safe() rejects whitespace-based traversal attempts."""
        # Attempts to use whitespace to bypass detection
        assert validate_slug_safe(".. /etc") is False  # Still contains ".."
        assert validate_slug_safe("../ etc") is False  # Still contains ".."
        assert validate_slug_safe("../\tetc") is False  # Still contains ".."
        assert validate_slug_safe("../\netc") is False  # Still contains ".."
        assert validate_slug_safe("../\retc") is False  # Still contains ".."

    def test_validate_slug_safe_rejects_combined_attacks(self) -> None:
        """Test that validate_slug_safe() rejects combined attack patterns."""
        # Combinations of multiple attack vectors
        assert validate_slug_safe("../.\x00hidden") is False  # Traversal + null byte
        assert validate_slug_safe("..\\../etc") is False  # Mixed separators (contains ..)
        assert validate_slug_safe("./../etc") is False  # Current + parent dir
        assert validate_slug_safe("/../etc") is False  # Absolute + traversal
        assert validate_slug_safe("C:../etc") is False  # Drive + traversal (contains ..)

    def test_validate_slug_safe_handles_repeated_dots(self) -> None:
        """Test that validate_slug_safe() handles repeated dot patterns."""
        # Various combinations of dots
        assert validate_slug_safe("...") is False  # Contains ".."
        assert validate_slug_safe("....") is False  # Contains ".."
        assert validate_slug_safe(".../test") is False  # Contains ".."
        assert validate_slug_safe("....test") is False  # Contains ".."

    def test_validate_slug_safe_handles_edge_cases(self) -> None:
        """Test that validate_slug_safe() handles edge cases correctly."""
        # Edge cases that might appear in real usage
        assert validate_slug_safe("-.") is True  # Dash-dot is safe
        assert validate_slug_safe(".-") is True  # Dot-dash is safe
        assert validate_slug_safe("--") is True  # Double dash is safe
        assert validate_slug_safe("a-b-c") is True  # Multiple dashes is safe
        assert validate_slug_safe("test.spec") is True  # Dot in middle is safe

    def test_validate_slug_safe_case_variations(self) -> None:
        """Test that validate_slug_safe() handles case variations of attacks."""
        # Case variations of dangerous patterns (Windows is case-insensitive)
        assert validate_slug_safe("C:") is False  # Uppercase drive letter
        assert validate_slug_safe("c:") is False  # Lowercase drive letter
        assert validate_slug_safe("D:") is False  # Another drive letter
        assert validate_slug_safe("../ETC/PASSWD") is False  # Uppercase traversal
        assert validate_slug_safe("../Etc/Passwd") is False  # Mixed case traversal

    def test_validate_slug_safe_length_attacks(self) -> None:
        """Test that validate_slug_safe() handles potential length-based attacks."""
        # Very long paths that might cause buffer overflows elsewhere
        long_safe = "a" * 10000
        assert validate_slug_safe(long_safe) is True  # Long but safe

        long_dangerous = "../" * 1000  # Many traversal attempts
        assert validate_slug_safe(long_dangerous) is False

    def test_validate_slug_safe_various_dangerous_combinations(self) -> None:
        """Test various combinations of dangerous patterns."""
        # Additional dangerous patterns not covered in other tests
        assert validate_slug_safe("./test/../etc") is False  # Multiple traversals
        assert validate_slug_safe("test/../hidden") is False  # Traversal in middle
        assert validate_slug_safe("../test/../etc") is False  # Multiple parent refs
        assert validate_slug_safe("/test/../etc") is False  # Absolute + traversal

    def test_validate_slug_safe_slash_variations(self) -> None:
        """Test validate_slug_safe with various slash patterns."""
        # Different slash patterns
        assert validate_slug_safe("/") is False  # Just absolute path
        assert validate_slug_safe("//") is False  # Double slash (still absolute)
        assert validate_slug_safe("\\") is False  # Single backslash
        assert validate_slug_safe("\\\\") is False  # Double backslash


# ============================================================================
# AutoflowCLI.validate_slug_safe() Tests
# ============================================================================


class TestAutoflowCLIValidateSlugSafe:
    """Tests for the AutoflowCLI.validate_slug_safe() method."""

    def test_validate_slug_safe_accepts_simple_slugs(self, safe_slugs: list[str]) -> None:
        """Test that AutoflowCLI.validate_slug_safe() accepts normal, safe slugs."""
        for slug in safe_slugs:
            assert AutoflowCLI.validate_slug_safe(slug) is True, f"Should accept safe slug: {slug}"

    def test_validate_slug_safe_rejects_parent_directory(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects '..' patterns."""
        assert AutoflowCLI.validate_slug_safe("..") is False
        assert AutoflowCLI.validate_slug_safe("../") is False
        assert AutoflowCLI.validate_slug_safe("../etc") is False
        assert AutoflowCLI.validate_slug_safe("../../etc/passwd") is False

    def test_validate_slug_safe_rejects_current_directory(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects './' patterns."""
        assert AutoflowCLI.validate_slug_safe("./") is False
        assert AutoflowCLI.validate_slug_safe("./hidden") is False
        assert AutoflowCLI.validate_slug_safe("./file") is False

    def test_validate_slug_safe_rejects_absolute_paths(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects absolute paths."""
        assert AutoflowCLI.validate_slug_safe("/etc/passwd") is False
        assert AutoflowCLI.validate_slug_safe("/absolute/path") is False
        assert AutoflowCLI.validate_slug_safe("/") is False

    def test_validate_slug_safe_rejects_null_bytes(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects null bytes."""
        assert AutoflowCLI.validate_slug_safe("test\x00null") is False
        assert AutoflowCLI.validate_slug_safe("\x00") is False

    def test_validate_slug_safe_rejects_backslash(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects backslash separators."""
        assert AutoflowCLI.validate_slug_safe("path\\with\\backslash") is False
        assert AutoflowCLI.validate_slug_safe("C:\\Windows\\System32") is False

    def test_validate_slug_safe_rejects_drive_letters(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects Windows drive letters."""
        assert AutoflowCLI.validate_slug_safe("C:") is False
        assert AutoflowCLI.validate_slug_safe("D:path") is False
        assert AutoflowCLI.validate_slug_safe("E:/path") is False

    def test_validate_slug_safe_rejects_encoded_traversal(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects encoded traversal patterns."""
        # Even when encoded with dashes, '..' should be rejected
        assert AutoflowCLI.validate_slug_safe("..-..-etc") is False
        assert AutoflowCLI.validate_slug_safe("..-..-..-etc-passwd") is False

    def test_validate_slug_safe_empty_string(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles empty string."""
        # Empty string should be safe (though it may fail elsewhere)
        assert AutoflowCLI.validate_slug_safe("") is True

    def test_validate_slug_safe_single_character(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles single character slugs."""
        assert AutoflowCLI.validate_slug_safe("a") is True
        assert AutoflowCLI.validate_slug_safe("-") is True  # Single dash is safe
        assert AutoflowCLI.validate_slug_safe(".") is True  # Single dot is safe (not "..")

    def test_validate_slug_safe_rejects_mixed_separators(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects mixed separator patterns."""
        # Mixed forward and backward slashes
        assert AutoflowCLI.validate_slug_safe("../..\\etc") is False
        assert AutoflowCLI.validate_slug_safe("..\\../etc") is False
        assert AutoflowCLI.validate_slug_safe("/..\\path") is False
        assert AutoflowCLI.validate_slug_safe("\\../path") is False

    def test_validate_slug_safe_rejects_whitespace_traversal(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects whitespace-based traversal attempts."""
        # Attempts to use whitespace to bypass detection
        assert AutoflowCLI.validate_slug_safe(".. /etc") is False  # Still contains ".."
        assert AutoflowCLI.validate_slug_safe("../ etc") is False  # Still contains ".."
        assert AutoflowCLI.validate_slug_safe("../\tetc") is False  # Still contains ".."
        assert AutoflowCLI.validate_slug_safe("../\netc") is False  # Still contains ".."
        assert AutoflowCLI.validate_slug_safe("../\retc") is False  # Still contains ".."

    def test_validate_slug_safe_rejects_combined_attacks(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() rejects combined attack patterns."""
        # Combinations of multiple attack vectors
        assert AutoflowCLI.validate_slug_safe("../.\x00hidden") is False  # Traversal + null byte
        assert AutoflowCLI.validate_slug_safe("..\\../etc") is False  # Mixed separators (contains ..)
        assert AutoflowCLI.validate_slug_safe("./../etc") is False  # Current + parent dir
        assert AutoflowCLI.validate_slug_safe("/../etc") is False  # Absolute + traversal
        assert AutoflowCLI.validate_slug_safe("C:../etc") is False  # Drive + traversal (contains ..)

    def test_validate_slug_safe_handles_repeated_dots(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles repeated dot patterns."""
        # Various combinations of dots
        assert AutoflowCLI.validate_slug_safe("...") is False  # Contains ".."
        assert AutoflowCLI.validate_slug_safe("....") is False  # Contains ".."
        assert AutoflowCLI.validate_slug_safe(".../test") is False  # Contains ".."
        assert AutoflowCLI.validate_slug_safe("....test") is False  # Contains ".."

    def test_validate_slug_safe_handles_edge_cases(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles edge cases correctly."""
        # Edge cases that might appear in real usage
        assert AutoflowCLI.validate_slug_safe("-.") is True  # Dash-dot is safe
        assert AutoflowCLI.validate_slug_safe(".-") is True  # Dot-dash is safe
        assert AutoflowCLI.validate_slug_safe("--") is True  # Double dash is safe
        assert AutoflowCLI.validate_slug_safe("a-b-c") is True  # Multiple dashes is safe
        assert AutoflowCLI.validate_slug_safe("test.spec") is True  # Dot in middle is safe

    def test_validate_slug_safe_case_variations(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles case variations of attacks."""
        # Case variations of dangerous patterns (Windows is case-insensitive)
        assert AutoflowCLI.validate_slug_safe("C:") is False  # Uppercase drive letter
        assert AutoflowCLI.validate_slug_safe("c:") is False  # Lowercase drive letter
        assert AutoflowCLI.validate_slug_safe("D:") is False  # Another drive letter
        assert AutoflowCLI.validate_slug_safe("../ETC/PASSWD") is False  # Uppercase traversal
        assert AutoflowCLI.validate_slug_safe("../Etc/Passwd") is False  # Mixed case traversal

    def test_validate_slug_safe_length_attacks(self) -> None:
        """Test that AutoflowCLI.validate_slug_safe() handles potential length-based attacks."""
        # Very long paths that might cause buffer overflows elsewhere
        long_safe = "a" * 10000
        assert AutoflowCLI.validate_slug_safe(long_safe) is True  # Long but safe

        long_dangerous = "../" * 1000  # Many traversal attempts
        assert AutoflowCLI.validate_slug_safe(long_dangerous) is False

    def test_validate_slug_safe_various_dangerous_combinations(self) -> None:
        """Test various combinations of dangerous patterns."""
        # Additional dangerous patterns not covered in other tests
        assert AutoflowCLI.validate_slug_safe("./test/../etc") is False  # Multiple traversals
        assert AutoflowCLI.validate_slug_safe("test/../hidden") is False  # Traversal in middle
        assert AutoflowCLI.validate_slug_safe("../test/../etc") is False  # Multiple parent refs
        assert AutoflowCLI.validate_slug_safe("/test/../etc") is False  # Absolute + traversal

    def test_validate_slug_safe_slash_variations(self) -> None:
        """Test AutoflowCLI.validate_slug_safe with various slash patterns."""
        # Different slash patterns
        assert AutoflowCLI.validate_slug_safe("/") is False  # Just absolute path
        assert AutoflowCLI.validate_slug_safe("//") is False  # Double slash (still absolute)
        assert AutoflowCLI.validate_slug_safe("\\") is False  # Single backslash
        assert AutoflowCLI.validate_slug_safe("\\\\") is False  # Double backslash


# ============================================================================
# commands.validate_slug_safe() Tests
# ============================================================================


class TestCommandsValidateSlugSafe:
    """Tests for the validate_slug_safe() function in autoflow.core.commands."""

    def test_validate_slug_safe_accepts_simple_slugs(self, safe_slugs: list[str]) -> None:
        """Test that commands.validate_slug_safe() accepts normal, safe slugs."""
        for slug in safe_slugs:
            assert commands_validate_slug_safe(slug) is True, f"Should accept safe slug: {slug}"

    def test_validate_slug_safe_rejects_parent_directory(self) -> None:
        """Test that commands.validate_slug_safe() rejects '..' patterns."""
        assert commands_validate_slug_safe("..") is False
        assert commands_validate_slug_safe("../") is False
        assert commands_validate_slug_safe("../etc") is False
        assert commands_validate_slug_safe("../../etc/passwd") is False

    def test_validate_slug_safe_rejects_current_directory(self) -> None:
        """Test that commands.validate_slug_safe() rejects './' patterns."""
        assert commands_validate_slug_safe("./") is False
        assert commands_validate_slug_safe("./hidden") is False
        assert commands_validate_slug_safe("./file") is False

    def test_validate_slug_safe_rejects_absolute_paths(self) -> None:
        """Test that commands.validate_slug_safe() rejects absolute paths."""
        assert commands_validate_slug_safe("/etc/passwd") is False
        assert commands_validate_slug_safe("/absolute/path") is False
        assert commands_validate_slug_safe("/") is False

    def test_validate_slug_safe_rejects_null_bytes(self) -> None:
        """Test that commands.validate_slug_safe() rejects null bytes."""
        assert commands_validate_slug_safe("test\x00null") is False
        assert commands_validate_slug_safe("\x00") is False

    def test_validate_slug_safe_rejects_backslash(self) -> None:
        """Test that commands.validate_slug_safe() rejects backslash separators."""
        assert commands_validate_slug_safe("path\\with\\backslash") is False
        assert commands_validate_slug_safe("C:\\Windows\\System32") is False

    def test_validate_slug_safe_rejects_drive_letters(self) -> None:
        """Test that commands.validate_slug_safe() rejects Windows drive letters."""
        assert commands_validate_slug_safe("C:") is False
        assert commands_validate_slug_safe("D:path") is False
        assert commands_validate_slug_safe("E:/path") is False

    def test_validate_slug_safe_rejects_encoded_traversal(self) -> None:
        """Test that commands.validate_slug_safe() rejects encoded traversal patterns."""
        # Even when encoded with dashes, '..' should be rejected
        assert commands_validate_slug_safe("..-..-etc") is False
        assert commands_validate_slug_safe("..-..-..-etc-passwd") is False

    def test_validate_slug_safe_empty_string(self) -> None:
        """Test that commands.validate_slug_safe() handles empty string."""
        # Empty string should be safe (though it may fail elsewhere)
        assert commands_validate_slug_safe("") is True

    def test_validate_slug_safe_single_character(self) -> None:
        """Test that commands.validate_slug_safe() handles single character slugs."""
        assert commands_validate_slug_safe("a") is True
        assert commands_validate_slug_safe("-") is True  # Single dash is safe
        assert commands_validate_slug_safe(".") is True  # Single dot is safe (not "..")

    def test_validate_slug_safe_rejects_mixed_separators(self) -> None:
        """Test that commands.validate_slug_safe() rejects mixed separator patterns."""
        # Mixed forward and backward slashes
        assert commands_validate_slug_safe("../..\\etc") is False
        assert commands_validate_slug_safe("..\\../etc") is False
        assert commands_validate_slug_safe("/..\\path") is False
        assert commands_validate_slug_safe("\\../path") is False

    def test_validate_slug_safe_rejects_whitespace_traversal(self) -> None:
        """Test that commands.validate_slug_safe() rejects whitespace-based traversal attempts."""
        # Attempts to use whitespace to bypass detection
        assert commands_validate_slug_safe(".. /etc") is False  # Still contains ".."
        assert commands_validate_slug_safe("../ etc") is False  # Still contains ".."
        assert commands_validate_slug_safe("../\tetc") is False  # Still contains ".."
        assert commands_validate_slug_safe("../\netc") is False  # Still contains ".."
        assert commands_validate_slug_safe("../\retc") is False  # Still contains ".."

    def test_validate_slug_safe_rejects_combined_attacks(self) -> None:
        """Test that commands.validate_slug_safe() rejects combined attack patterns."""
        # Combinations of multiple attack vectors
        assert commands_validate_slug_safe("../.\x00hidden") is False  # Traversal + null byte
        assert commands_validate_slug_safe("..\\../etc") is False  # Mixed separators (contains ..)
        assert commands_validate_slug_safe("./../etc") is False  # Current + parent dir
        assert commands_validate_slug_safe("/../etc") is False  # Absolute + traversal
        assert commands_validate_slug_safe("C:../etc") is False  # Drive + traversal (contains ..)

    def test_validate_slug_safe_handles_repeated_dots(self) -> None:
        """Test that commands.validate_slug_safe() handles repeated dot patterns."""
        # Various combinations of dots
        assert commands_validate_slug_safe("...") is False  # Contains ".."
        assert commands_validate_slug_safe("....") is False  # Contains ".."
        assert commands_validate_slug_safe(".../test") is False  # Contains ".."
        assert commands_validate_slug_safe("....test") is False  # Contains ".."

    def test_validate_slug_safe_handles_edge_cases(self) -> None:
        """Test that commands.validate_slug_safe() handles edge cases correctly."""
        # Edge cases that might appear in real usage
        assert commands_validate_slug_safe("-.") is True  # Dash-dot is safe
        assert commands_validate_slug_safe(".-") is True  # Dot-dash is safe
        assert commands_validate_slug_safe("--") is True  # Double dash is safe
        assert commands_validate_slug_safe("a-b-c") is True  # Multiple dashes is safe
        assert commands_validate_slug_safe("test.spec") is True  # Dot in middle is safe

    def test_validate_slug_safe_case_variations(self) -> None:
        """Test that commands.validate_slug_safe() handles case variations of attacks."""
        # Case variations of dangerous patterns (Windows is case-insensitive)
        assert commands_validate_slug_safe("C:") is False  # Uppercase drive letter
        assert commands_validate_slug_safe("c:") is False  # Lowercase drive letter
        assert commands_validate_slug_safe("D:") is False  # Another drive letter
        assert commands_validate_slug_safe("../ETC/PASSWD") is False  # Uppercase traversal
        assert commands_validate_slug_safe("../Etc/Passwd") is False  # Mixed case traversal

    def test_validate_slug_safe_length_attacks(self) -> None:
        """Test that commands.validate_slug_safe() handles potential length-based attacks."""
        # Very long paths that might cause buffer overflows elsewhere
        long_safe = "a" * 10000
        assert commands_validate_slug_safe(long_safe) is True  # Long but safe

        long_dangerous = "../" * 1000  # Many traversal attempts
        assert commands_validate_slug_safe(long_dangerous) is False

    def test_validate_slug_safe_various_dangerous_combinations(self) -> None:
        """Test various combinations of dangerous patterns."""
        # Additional dangerous patterns not covered in other tests
        assert commands_validate_slug_safe("./test/../etc") is False  # Multiple traversals
        assert commands_validate_slug_safe("test/../hidden") is False  # Traversal in middle
        assert commands_validate_slug_safe("../test/../etc") is False  # Multiple parent refs
        assert commands_validate_slug_safe("/test/../etc") is False  # Absolute + traversal

    def test_validate_slug_safe_slash_variations(self) -> None:
        """Test commands.validate_slug_safe with various slash patterns."""
        # Different slash patterns
        assert commands_validate_slug_safe("/") is False  # Just absolute path
        assert commands_validate_slug_safe("//") is False  # Double slash (still absolute)
        assert commands_validate_slug_safe("\\") is False  # Single backslash
        assert commands_validate_slug_safe("\\\\") is False  # Double backslash

    def test_commands_validate_slug_safe_consistent_with_scripts_version(self) -> None:
        """Test that commands.validate_slug_safe behaves identically to scripts.autoflow.validate_slug_safe."""
        # Test a variety of slugs to ensure consistent behavior
        test_slugs = [
            "simple-spec",  # Safe
            "../etc",  # Dangerous
            "./hidden",  # Dangerous
            "/absolute",  # Dangerous
            "test\x00null",  # Dangerous
            "C:\\path",  # Dangerous
            "..-..-etc",  # Dangerous
            "a-b-c",  # Safe
            "",  # Safe (empty)
            ".",  # Safe (single dot)
        ]

        for slug in test_slugs:
            scripts_result = validate_slug_safe(slug)
            commands_result = commands_validate_slug_safe(slug)
            assert scripts_result == commands_result, (
                f"commands.validate_slug_safe() should return same result as "
                f"scripts.autoflow.validate_slug_safe() for slug {slug!r}. "
                f"Expected {scripts_result}, got {commands_result}"
            )


# ============================================================================
# spec_dir() Tests
# ============================================================================


class TestSpecDir:
    """Tests for the spec_dir() function."""

    def test_spec_dir_accepts_safe_slugs(self, safe_slugs: list[str]) -> None:
        """Test that spec_dir() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = spec_dir(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"

    def test_spec_dir_rejects_traversal(self) -> None:
        """Test that spec_dir() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the specs directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                spec_dir(slug), f"Should reject path traversal attempt: {slug}"

    def test_spec_dir_rejects_dangerous_slugs(self, dangerous_slugs: list[tuple[str, str]]) -> None:
        """Test that spec_dir() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                spec_dir(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_spec_dir_path_construction(self) -> None:
        """Test that spec_dir() constructs paths correctly."""
        path = spec_dir("test-spec")
        assert "test-spec" in str(path)
        assert path.is_absolute() or isinstance(path, Path)


# ============================================================================
# task_file() Tests
# ============================================================================


class TestTaskFile:
    """Tests for the task_file() function."""

    def test_task_file_accepts_safe_slugs(self, safe_slugs: list[str]) -> None:
        """Test that task_file() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = task_file(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"
            assert path.suffix == ".json", f"Should have .json extension: {slug}"

    def test_task_file_rejects_traversal(self) -> None:
        """Test that task_file() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the tasks directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                task_file(slug), f"Should reject path traversal attempt: {slug}"

    def test_task_file_rejects_dangerous_slugs(self, dangerous_slugs: list[tuple[str, str]]) -> None:
        """Test that task_file() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                task_file(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_task_file_path_construction(self) -> None:
        """Test that task_file() constructs paths correctly."""
        path = task_file("test-spec")
        assert "test-spec" in str(path)
        assert str(path).endswith(".json")
        assert path.is_absolute() or isinstance(path, Path)


# ============================================================================
# worktree_path() Tests
# ============================================================================


class TestWorktreePath:
    """Tests for the worktree_path() function."""

    def test_worktree_path_accepts_safe_slugs(self, safe_slugs: list[str]) -> None:
        """Test that worktree_path() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = worktree_path(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"

    def test_worktree_path_rejects_traversal(self) -> None:
        """Test that worktree_path() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the worktrees directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                worktree_path(slug), f"Should reject path traversal attempt: {slug}"

    def test_worktree_path_rejects_dangerous_slugs(self, dangerous_slugs: list[tuple[str, str]]) -> None:
        """Test that worktree_path() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                worktree_path(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_worktree_path_path_construction(self) -> None:
        """Test that worktree_path() constructs paths correctly."""
        path = worktree_path("test-spec")
        assert "test-spec" in str(path)
        assert path.is_absolute() or isinstance(path, Path)


# ============================================================================
# slugify() Tests
# ============================================================================


class TestSlugify:
    """Tests for the slugify() function to ensure it doesn't create dangerous patterns."""

    def test_slugify_basic_conversion(self) -> None:
        """Test that slugify() converts basic inputs correctly."""
        assert slugify("Simple Title") == "simple-title"
        assert slugify("Feature Name") == "feature-name"
        assert slugify("test") == "test"

    def test_slugify_handles_special_characters(self) -> None:
        """Test that slugify() handles special characters correctly."""
        assert slugify("Feature/SubFeature") == "feature-subfeature"
        assert slugify("Feature_SubFeature") == "feature-subfeature"
        assert slugify("Feature-SubFeature") == "feature-subfeature"
        assert slugify("Feature.SubFeature") == "feature-subfeature"

    def test_slugify_consecutive_dashes(self) -> None:
        """Test that slugify() collapses consecutive dashes."""
        assert slugify("Feature  /  Sub") == "feature-sub"
        assert slugify("test---multiple---dashes") == "test-multiple-dashes"

    def test_slugify_trailing_dashes(self) -> None:
        """Test that slugify() removes leading and trailing dashes."""
        assert slugify("-test-") == "test"
        assert slugify("--test--") == "test"

    def test_slugify_empty_result(self) -> None:
        """Test that slugify() returns 'spec' for empty or special-only input."""
        assert slugify("") == "spec"
        assert slugify("---") == "spec"

    def test_slugify_creates_safe_slugs(self) -> None:
        """Test that slugify() never creates dangerous patterns."""
        # Even with suspicious input, output should be safe
        suspicious_inputs = [
            "../etc/passwd",
            "../../../etc/passwd",
            "./hidden",
            "/absolute/path",
            "path\\with\\backslash",
            "C:\\Windows\\System32",
        ]

        for input_str in suspicious_inputs:
            slug = slugify(input_str)
            assert validate_slug_safe(slug) is True, (
                f"slugify() should never create dangerous slugs. "
                f"Input: {input_str}, Output: {slug}"
            )

    def test_slugify_does_not_preserve_parent_directory(self) -> None:
        """Test that slugify() doesn't preserve '..' sequences."""
        assert ".." not in slugify("../etc/passwd")
        assert ".." not in slugify("../../test")
        assert ".." not in slugify("test/../hidden")

    def test_slugify_does_not_create_absolute_paths(self) -> None:
        """Test that slugify() doesn't create paths starting with '/'."""
        assert not slugify("/absolute/path").startswith("/")
        assert not slugify("/test").startswith("/")

    def test_slugify_does_not_preserve_backslash(self) -> None:
        """Test that slugify() converts backslashes to dashes."""
        slug = slugify("path\\with\\backslash")
        assert "\\" not in slug
        assert validate_slug_safe(slug) is True

    def test_slugify_edge_cases(self) -> None:
        """Test slugify() edge cases to ensure it doesn't create dangerous patterns.

        This comprehensive test verifies that slugify() properly sanitizes inputs
        that could potentially become dangerous after conversion, ensuring that
        no edge case results in a slug that could be used for path traversal.
        """
        # Test cases where input could become dangerous after slugify
        edge_case_inputs = [
            # Null bytes and control characters
            ("test\x00null", "Null byte in input"),
            ("\x00", "Pure null byte"),
            ("test\x01\x02\x03", "Multiple control characters"),
            ("test\twith\ttabs", "Tab characters"),
            ("test\nwith\nnewlines", "Newline characters"),
            ("test\rwith\rcarriage", "Carriage returns"),

            # Multiple dots that could form ".."
            ("...", "Three dots"),
            ("....", "Four dots"),
            ("test...test", "Dots in middle"),
            ("...test", "Leading dots"),
            ("test...", "Trailing dots"),
            ("...test...", "Dots on both ends"),

            # Mixed separators
            ("path/\\mixed", "Mixed forward and backslash"),
            ("path-/-mixed", "Mixed dash and slash"),
            ("path_/_mixed", "Mixed underscore and slash"),
            ("path.-.mixed", "Mixed dot and dash"),
            ("path_.-mixed", "Mixed underscore, dot, dash"),

            # Whitespace variations
            ("test   spaces", "Multiple spaces"),
            ("test  \t  mixed", "Mixed whitespace"),
            ("  leading", "Leading whitespace"),
            ("trailing  ", "Trailing whitespace"),
            ("  both  ", "Both leading and trailing"),

            # Special characters at edges
            ("-test", "Leading dash"),
            ("test-", "Trailing dash"),
            ("_test", "Leading underscore"),
            ("test_", "Trailing underscore"),
            (".test", "Leading dot"),
            ("test.", "Trailing dot"),
            ("/test", "Leading slash"),
            ("test/", "Trailing slash"),

            # Repeated special characters
            ("---test---", "Multiple dashes"),
            ("___test___", "Multiple underscores"),
            ("...", "Multiple dots"),
            ("///test///", "Multiple slashes"),

            # Case variations that might cause issues
            ("TEST", "All uppercase"),
            ("TeSt", "Mixed case"),
            ("tEST", "Mixed case starting with lower"),

            # Empty and minimal inputs
            ("", "Empty string"),
            ("-", "Single dash"),
            ("_", "Single underscore"),
            (".", "Single dot"),
            (" ", "Single space"),

            # Unicode and special characters
            ("test™", "Trademark symbol"),
            ("test©", "Copyright symbol"),
            ("test®", "Registered symbol"),
            ("test•", "Bullet point"),
            ("test◆", "Diamond"),
            ("test→", "Arrow"),

            # Path-like patterns
            ("test/path/file", "Unix-like path"),
            ("test\\path\\file", "Windows-like path"),
            ("test./path", "Dot-slash pattern"),
            ("test/.path", "Slash-dot pattern"),
            ("test//path", "Double slash"),

            # Potentially dangerous sequences
            ("..test..", "Dots around text"),
            ("test..test", "Dots in middle"),
            ("test-.-test", "Dash-dot-dash pattern"),
            ("test_.-test", "Underscore-dot-dash pattern"),

            # Long sequences
            ("a" * 1000, "Long string of safe characters"),
            ("-" * 100, "Many dashes"),
            ("." * 100, "Many dots"),
            (" " * 100, "Many spaces"),

            # Mixed safe and unsafe
            ("safe/../test", "Safe with traversal"),
            ("safe-./test", "Safe with dot-slash"),
            ("safe-\\test", "Safe with backslash"),
            ("safe C:/test", "Safe with Windows path"),

            # Edge cases with dots and dashes
            ("..-..", "Dash-separated parent refs"),
            (".-.-.", "Alternating dot and dash"),
            ("-.-", "Dash-dot-dash"),
            ("_.-._", "Underscore combinations"),
        ]

        for input_str, description in edge_case_inputs:
            slug = slugify(input_str)

            # Every slugified result must be safe
            assert validate_slug_safe(slug) is True, (
                f"slugify() created unsafe slug for {description!r}. "
                f"Input: {input_str!r}, Output: {slug!r}"
            )

            # Result should not contain dangerous patterns
            assert ".." not in slug, (
                f"slugify() created '..' in {description!r}. "
                f"Input: {input_str!r}, Output: {slug!r}"
            )

            assert "\\" not in slug, (
                f"slugify() preserved backslash in {description!r}. "
                f"Input: {input_str!r}, Output: {slug!r}"
            )

            assert not slug.startswith("/"), (
                f"slugify() created absolute path in {description!r}. "
                f"Input: {input_str!r}, Output: {slug!r}"
            )

            # Result should not be empty (should return "spec" as fallback)
            assert len(slug) > 0, (
                f"slugify() returned empty string for {description!r}. "
                f"Input: {input_str!r}, Output: {slug!r}"
            )


# ============================================================================
# AutoflowCLI.spec_dir() Tests
# ============================================================================


class TestAutoflowCLISpecDir:
    """Tests for the AutoflowCLI.spec_dir() method."""

    @pytest.fixture
    def cli(self, mock_state_dir, mock_config):
        """Create an AutoflowCLI instance for testing."""
        from autoflow.core.config import Config

        # Create a minimal config
        config = mock_config
        config.state_dir = mock_state_dir

        cli = AutoflowCLI(config, state_dir=mock_state_dir)
        return cli

    def test_spec_dir_accepts_safe_slugs(self, cli: AutoflowCLI, safe_slugs: list[str]) -> None:
        """Test that spec_dir() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = cli.spec_dir(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"

    def test_spec_dir_rejects_traversal(self, cli: AutoflowCLI) -> None:
        """Test that spec_dir() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the specs directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.spec_dir(slug), f"Should reject path traversal attempt: {slug}"

    def test_spec_dir_rejects_dangerous_slugs(
        self, cli: AutoflowCLI, dangerous_slugs: list[tuple[str, str]]
    ) -> None:
        """Test that spec_dir() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.spec_dir(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_spec_dir_path_construction(self, cli: AutoflowCLI) -> None:
        """Test that spec_dir() constructs paths correctly."""
        path = cli.spec_dir("test-spec")
        assert "test-spec" in str(path)
        assert path.is_absolute() or isinstance(path, Path)

    def test_spec_dir_under_specs_dir(self, cli: AutoflowCLI) -> None:
        """Test that spec_dir() returns paths under the specs directory."""
        slug = "my-spec"
        path = cli.spec_dir(slug)
        # The path should be under specs_dir
        assert cli.specs_dir in path.parents or path == cli.specs_dir / slug
        assert path == cli.specs_dir / slug


# ============================================================================
# AutoflowCLI.task_file() Tests
# ============================================================================


class TestAutoflowCLITaskFile:
    """Tests for the AutoflowCLI.task_file() method."""

    @pytest.fixture
    def cli(self, mock_state_dir, mock_config):
        """Create an AutoflowCLI instance for testing."""
        from autoflow.core.config import Config

        # Create a minimal config
        config = mock_config
        config.state_dir = mock_state_dir

        cli = AutoflowCLI(config, state_dir=mock_state_dir)
        return cli

    def test_task_file_accepts_safe_slugs(self, cli: AutoflowCLI, safe_slugs: list[str]) -> None:
        """Test that task_file() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = cli.task_file(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"
            assert path.suffix == ".json", f"Should have .json extension: {slug}"

    def test_task_file_rejects_traversal(self, cli: AutoflowCLI) -> None:
        """Test that task_file() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the tasks directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.task_file(slug), f"Should reject path traversal attempt: {slug}"

    def test_task_file_rejects_dangerous_slugs(
        self, cli: AutoflowCLI, dangerous_slugs: list[tuple[str, str]]
    ) -> None:
        """Test that task_file() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.task_file(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_task_file_path_construction(self, cli: AutoflowCLI) -> None:
        """Test that task_file() constructs paths correctly."""
        path = cli.task_file("test-spec")
        assert "test-spec" in str(path)
        assert str(path).endswith(".json")
        assert path.is_absolute() or isinstance(path, Path)

    def test_task_file_in_spec_dir(self, cli: AutoflowCLI) -> None:
        """Test that task_file() returns paths within the spec directory."""
        slug = "my-spec"
        path = cli.task_file(slug)
        # The path should be under the spec directory
        spec_dir_path = cli.spec_dir(slug)
        assert path.parent == spec_dir_path or spec_dir_path in path.parents
        # The filename should be tasks.json
        assert path.name == "tasks.json"


# ============================================================================
# AutoflowCLI.worktree_path() Tests
# ============================================================================


class TestAutoflowCLIWorktreePath:
    """Tests for the AutoflowCLI.worktree_path() method."""

    @pytest.fixture
    def cli(self, mock_state_dir, mock_config):
        """Create an AutoflowCLI instance for testing."""
        from autoflow.core.config import Config

        # Create a minimal config
        config = mock_config
        config.state_dir = mock_state_dir

        cli = AutoflowCLI(config, state_dir=mock_state_dir)
        return cli

    def test_worktree_path_accepts_safe_slugs(self, cli: AutoflowCLI, safe_slugs: list[str]) -> None:
        """Test that worktree_path() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = cli.worktree_path(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"

    def test_worktree_path_rejects_traversal(self, cli: AutoflowCLI) -> None:
        """Test that worktree_path() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the worktrees directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.worktree_path(slug), f"Should reject path traversal attempt: {slug}"

    def test_worktree_path_rejects_dangerous_slugs(
        self, cli: AutoflowCLI, dangerous_slugs: list[tuple[str, str]]
    ) -> None:
        """Test that worktree_path() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                cli.worktree_path(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_worktree_path_path_construction(self, cli: AutoflowCLI) -> None:
        """Test that worktree_path() constructs paths correctly."""
        path = cli.worktree_path("test-spec")
        assert "test-spec" in str(path)
        assert path.is_absolute() or isinstance(path, Path)

    def test_worktree_path_under_worktrees_dir(self, cli: AutoflowCLI) -> None:
        """Test that worktree_path() returns paths under the worktrees directory."""
        slug = "my-spec"
        path = cli.worktree_path(slug)
        # The path should be under worktrees_dir
        assert cli.worktrees_dir in path.parents or path == cli.worktrees_dir / slug
        assert path == cli.worktrees_dir / slug


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_unicode_slugs_are_safe(self) -> None:
        """Test that slugs with unicode characters are handled safely."""
        # After slugify, unicode characters should be converted or removed
        slug = slugify("Hello World")
        assert validate_slug_safe(slug) is True

    def test_very_long_slugs(self) -> None:
        """Test that validation works with very long slugs."""
        long_slug = "a" * 1000
        # Long slug with only safe characters should be safe
        assert validate_slug_safe(long_slug) is True

    def test_mixed_dangerous_patterns(self) -> None:
        """Test slugs with multiple dangerous patterns."""
        # Any dangerous pattern should cause rejection
        assert validate_slug_safe(".././etc") is False
        assert validate_slug_safe("/..\\path") is False

    def test_spec_dir_then_construct_path(self) -> None:
        """Test that spec_dir() can be used to construct file paths."""
        slug = "test-spec"
        dir_path = spec_dir(slug)
        file_path = dir_path / "spec.md"

        assert str(slug) in str(file_path)
        assert "spec.md" in str(file_path)

    def test_task_file_with_json_extension(self) -> None:
        """Test that task_file() always adds .json extension."""
        slug = "my-spec"
        path = task_file(slug)
        assert path.suffix == ".json"

    def test_consistent_validation_across_functions(self) -> None:
        """Test that all three functions use consistent validation."""
        dangerous_slug = "../etc/passwd"

        # All three should reject the same dangerous slug
        with pytest.raises(SystemExit):
            spec_dir(dangerous_slug)

        with pytest.raises(SystemExit):
            task_file(dangerous_slug)

        with pytest.raises(SystemExit):
            worktree_path(dangerous_slug)

    def test_safe_slug_works_with_all_functions(self) -> None:
        """Test that a safe slug works with all three functions."""
        safe_slug = "my-test-spec"

        # All three should accept the same safe slug
        spec_path = spec_dir(safe_slug)
        task_path = task_file(safe_slug)
        worktree = worktree_path(safe_slug)

        # All should return Path objects
        assert isinstance(spec_path, Path)
        assert isinstance(task_path, Path)
        assert isinstance(worktree, Path)

        # All should contain the slug
        assert str(safe_slug) in str(spec_path)
        assert str(safe_slug) in str(task_path)
        assert str(safe_slug) in str(worktree)


# ============================================================================
# commands._spec_files() Tests
# ============================================================================


class TestCommandsSpecFiles:
    """Tests for the commands._spec_files() function."""

    def test_spec_files_accepts_safe_slugs(self, safe_slugs: list[str]) -> None:
        """Test that _spec_files() accepts normal, safe slugs and returns valid paths."""
        for slug in safe_slugs:
            result = _spec_files(slug)
            assert isinstance(result, dict), f"Should return dict for: {slug}"
            assert "dir" in result, f"Should have 'dir' key for: {slug}"
            assert "spec" in result, f"Should have 'spec' key for: {slug}"
            assert "metadata" in result, f"Should have 'metadata' key for: {slug}"
            assert "review_state" in result, f"Should have 'review_state' key for: {slug}"
            assert "qa_fix_request" in result, f"Should have 'qa_fix_request' key for: {slug}"
            assert "qa_fix_request_json" in result, f"Should have 'qa_fix_request_json' key for: {slug}"
            assert "events" in result, f"Should have 'events' key for: {slug}"

            # All values should be Path objects
            for key, path in result.items():
                assert isinstance(path, Path), f"Value for {key} should be Path for: {slug}"

            # All paths should contain the slug
            for key, path in result.items():
                assert str(slug) in str(path), f"Path for {key} should contain slug: {slug}"

    def test_spec_files_rejects_traversal(self) -> None:
        """Test that _spec_files() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the specs directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                _spec_files(slug), f"Should reject path traversal attempt: {slug}"

    def test_spec_files_rejects_dangerous_slugs(
        self, dangerous_slugs: list[tuple[str, str]]
    ) -> None:
        """Test that _spec_files() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                _spec_files(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_spec_files_returns_correct_structure(self) -> None:
        """Test that _spec_files() returns the correct dictionary structure."""
        slug = "test-spec"
        result = _spec_files(slug)

        # Check that all expected keys are present
        expected_keys = {
            "dir",
            "spec",
            "metadata",
            "review_state",
            "qa_fix_request",
            "qa_fix_request_json",
            "events",
        }
        assert set(result.keys()) == expected_keys, f"Should have exactly these keys: {expected_keys}"

    def test_spec_files_dir_path(self) -> None:
        """Test that _spec_files() returns correct directory path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The dir should be a path containing the slug
        assert str(slug) in str(result["dir"])
        assert isinstance(result["dir"], Path)

    def test_spec_files_spec_path(self) -> None:
        """Test that _spec_files() returns correct spec.md path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The spec file should be named spec.md and be in the slug directory
        assert result["spec"].name == "spec.md"
        assert str(slug) in str(result["spec"])
        assert result["spec"].parent == result["dir"]

    def test_spec_files_metadata_path(self) -> None:
        """Test that _spec_files() returns correct metadata.json path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The metadata file should be named metadata.json and be in the slug directory
        assert result["metadata"].name == "metadata.json"
        assert str(slug) in str(result["metadata"])
        assert result["metadata"].parent == result["dir"]

    def test_spec_files_review_state_path(self) -> None:
        """Test that _spec_files() returns correct review_state.json path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The review_state file should be named review_state.json and be in the slug directory
        assert result["review_state"].name == "review_state.json"
        assert str(slug) in str(result["review_state"])
        assert result["review_state"].parent == result["dir"]

    def test_spec_files_qa_fix_request_path(self) -> None:
        """Test that _spec_files() returns correct QA_FIX_REQUEST.md path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The qa_fix_request file should be named QA_FIX_REQUEST.md and be in the slug directory
        assert result["qa_fix_request"].name == "QA_FIX_REQUEST.md"
        assert str(slug) in str(result["qa_fix_request"])
        assert result["qa_fix_request"].parent == result["dir"]

    def test_spec_files_qa_fix_request_json_path(self) -> None:
        """Test that _spec_files() returns correct QA_FIX_REQUEST.json path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The qa_fix_request_json file should be named QA_FIX_REQUEST.json and be in the slug directory
        assert result["qa_fix_request_json"].name == "QA_FIX_REQUEST.json"
        assert str(slug) in str(result["qa_fix_request_json"])
        assert result["qa_fix_request_json"].parent == result["dir"]

    def test_spec_files_events_path(self) -> None:
        """Test that _spec_files() returns correct events.jsonl path."""
        slug = "my-spec"
        result = _spec_files(slug)

        # The events file should be named events.jsonl and be in the slug directory
        assert result["events"].name == "events.jsonl"
        assert str(slug) in str(result["events"])
        assert result["events"].parent == result["dir"]

    def test_spec_files_all_in_same_directory(self) -> None:
        """Test that all files returned by _spec_files() are in the same directory."""
        slug = "test-spec"
        result = _spec_files(slug)

        # All files except "dir" should have the same parent as "dir"
        dir_path = result["dir"]
        for key in ["spec", "metadata", "review_state", "qa_fix_request", "qa_fix_request_json", "events"]:
            assert result[key].parent == dir_path, f"{key} should be in the spec directory"

    def test_spec_files_with_slug_containing_dashes(self) -> None:
        """Test that _spec_files() handles slugs with multiple dashes correctly."""
        slug = "my-test-spec-with-many-dashes"
        result = _spec_files(slug)

        # Should work without errors
        assert isinstance(result, dict)
        assert "dir" in result
        assert str(slug) in str(result["dir"])

    def test_spec_files_with_slug_containing_numbers(self) -> None:
        """Test that _spec_files() handles slugs with numbers correctly."""
        slug = "feature-123-spec-456"
        result = _spec_files(slug)

        # Should work without errors
        assert isinstance(result, dict)
        assert "dir" in result
        assert str(slug) in str(result["dir"])

    def test_spec_files_empty_slug(self) -> None:
        """Test that _spec_files() handles empty string slug.

        Empty string is considered safe by validate_slug_safe(), so _spec_files()
        should accept it, though it may not be a valid spec directory.
        """
        slug = ""
        result = _spec_files(slug)

        # Should return paths with empty string as the slug
        assert isinstance(result, dict)
        assert "dir" in result
        # The directory path should still be valid even with empty slug
        assert isinstance(result["dir"], Path)

    def test_spec_files_consistent_with_validate_slug_safe(self) -> None:
        """Test that _spec_files() uses the same validation as validate_slug_safe()."""
        # Test a slug that validate_slug_safe() rejects
        dangerous_slug = "../etc/passwd"

        # _spec_files() should reject it the same way
        with pytest.raises(SystemExit, match=r"invalid spec slug"):
            _spec_files(dangerous_slug)

    def test_spec_files_all_paths_are_absolute_or_relative(self) -> None:
        """Test that paths returned by _spec_files() are valid Path objects."""
        slug = "test-spec"
        result = _spec_files(slug)

        # All paths should be Path objects (they may be relative or absolute)
        for key, path in result.items():
            assert isinstance(path, Path), f"{key} should be a Path object"


# ============================================================================
# commands._task_file() Tests
# ============================================================================


class TestCommandsTaskFile:
    """Tests for the commands._task_file() function."""

    def test_task_file_accepts_safe_slugs(self, safe_slugs: list[str]) -> None:
        """Test that _task_file() accepts safe slugs and returns valid paths."""
        for slug in safe_slugs:
            path = _task_file(slug)
            assert isinstance(path, Path), f"Should return Path for: {slug}"
            assert str(slug) in str(path), f"Path should contain slug: {slug}"
            assert path.suffix == ".json", f"Should have .json extension: {slug}"

    def test_task_file_rejects_traversal(self) -> None:
        """Test that _task_file() specifically rejects path traversal attempts.

        This is a focused security test for CWE-22 (Path Traversal) prevention,
        verifying that parent directory references cannot escape the tasks directory.
        """
        traversal_attempts = [
            "..",
            "../",
            "../etc",
            "../../etc",
            "../../etc/passwd",
            "../../../",
            "../..",
            ".././etc",
            "./../etc",
            "../test/../etc",
            "..-..-etc",
        ]

        for slug in traversal_attempts:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                _task_file(slug), f"Should reject path traversal attempt: {slug}"

    def test_task_file_rejects_dangerous_slugs(self, dangerous_slugs: list[tuple[str, str]]) -> None:
        """Test that _task_file() raises SystemExit for dangerous slugs."""
        for slug, description in dangerous_slugs:
            with pytest.raises(SystemExit, match=r"invalid spec slug"):
                _task_file(slug), f"Should reject dangerous slug ({description}): {slug}"

    def test_task_file_path_construction(self) -> None:
        """Test that _task_file() constructs paths correctly."""
        path = _task_file("test-spec")
        assert "test-spec" in str(path)
        assert str(path).endswith(".json")
        assert isinstance(path, Path)

    def test_task_file_returns_correct_filename(self) -> None:
        """Test that _task_file() returns correct filename pattern."""
        slug = "my-feature-spec"
        path = _task_file(slug)

        # File should be named {slug}.json
        assert path.name == f"{slug}.json"

    def test_task_file_with_slug_containing_dashes(self) -> None:
        """Test that _task_file() handles slugs with multiple dashes correctly."""
        slug = "my-test-spec-with-many-dashes"
        path = _task_file(slug)

        # Should work without errors
        assert isinstance(path, Path)
        assert str(slug) in str(path)
        assert path.suffix == ".json"

    def test_task_file_with_slug_containing_numbers(self) -> None:
        """Test that _task_file() handles slugs with numbers correctly."""
        slug = "feature-123-spec-456"
        path = _task_file(slug)

        # Should work without errors
        assert isinstance(path, Path)
        assert str(slug) in str(path)
        assert path.suffix == ".json"

    def test_task_file_empty_slug(self) -> None:
        """Test that _task_file() handles empty string slug.

        Empty string is considered safe by validate_slug_safe(), so _task_file()
        should accept it, though it may not be a valid task file.
        """
        slug = ""
        path = _task_file(slug)

        # Should return path with empty string as the slug
        # The filename becomes ".json" which starts with a dot, so suffix is empty
        assert isinstance(path, Path)
        assert path.name == ".json"  # Empty slug results in hidden file starting with dot

    def test_task_file_consistent_with_validate_slug_safe(self) -> None:
        """Test that _task_file() uses the same validation as validate_slug_safe()."""
        # Test a slug that validate_slug_safe() rejects
        dangerous_slug = "../etc/passwd"

        # _task_file() should reject it the same way
        with pytest.raises(SystemExit, match=r"invalid spec slug"):
            _task_file(dangerous_slug)

    def test_task_file_returns_absolute_or_relative_path(self) -> None:
        """Test that _task_file() returns a valid Path object."""
        slug = "test-spec"
        path = _task_file(slug)

        # The path should be a Path object (may be relative or absolute depending on TASKS_DIR)
        assert isinstance(path, Path)
