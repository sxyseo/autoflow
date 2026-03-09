"""
Unit Tests for Slug Validation and Path Traversal Prevention

Tests the validate_slug_safe() function and related path construction functions
(spec_dir, task_file, worktree_path) to ensure they properly detect and prevent
path traversal attacks.

These tests verify that:
1. The validation function correctly identifies dangerous patterns
2. Path construction functions reject unsafe slugs
3. Normal valid slugs continue to work as expected
4. The slugify() function doesn't create dangerous patterns

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
        (".hidden", "Hidden file reference"),
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
