"""
Unit Tests for CLI JSON Output Sanitization

Tests the sanitization functionality used by CLI output functions
to ensure sensitive data is properly sanitized before being output to stdout
or written to files.

These tests verify that sensitive information (API keys, secrets, passwords,
tokens, etc.) is redacted to prevent information disclosure (CWE-200).

The print_json() and write_json() functions in scripts/autoflow.py are
thin wrappers around sanitize_dict() and sanitize_value(), so we test
the underlying sanitization functions that they use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autoflow.core.sanitization import (
    DEFAULT_REDACTED,
    sanitize_dict,
    sanitize_value,
    sanitize_json,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_cli_data() -> dict[str, Any]:
    """Return sample CLI output data with sensitive fields."""
    return {
        "task_id": "task-001",
        "title": "Test Task",
        "status": "in_progress",
        "api_key": "sk-1234567890abcdef",
        "agent_config": {
            "model": "gpt-4-32k",
            "api_key": "secret-key-123",
            "secret": "my-secret-value",
        },
        "metadata": {
            "user": "alice",
            "token": "bearer-token-xyz",
        },
    }


@pytest.fixture
def sample_list_data() -> list[dict[str, Any]]:
    """Return sample list data with sensitive fields."""
    return [
        {"id": "task-001", "api_key": "key-001", "name": "Task 1"},
        {"id": "task-002", "api_key": "key-002", "name": "Task 2"},
        {"id": "task-003", "secret": "secret-003", "name": "Task 3"},
    ]


@pytest.fixture
def temp_output_file(tmp_path: Path) -> Path:
    """Create a temporary file path for output testing."""
    return tmp_path / "output.json"


# ============================================================================
# CLI Output Sanitization Tests
# These tests verify the sanitization functions used by print_json/write_json
# ============================================================================


class TestCliOutputSanitization:
    """Tests for CLI JSON output sanitization (used by print_json/write_json)."""

    def test_sanitize_simple_dict(self) -> None:
        """Test sanitization with simple dictionary containing sensitive data."""
        data = {
            "name": "test",
            "api_key": "secret123",
            "status": "active",
        }

        result = sanitize_dict(data)

        # Sensitive field should be redacted
        assert result["api_key"] == DEFAULT_REDACTED
        # Non-sensitive fields preserved
        assert result["name"] == "test"
        assert result["status"] == "active"

    def test_sanitize_nested_dict(self) -> None:
        """Test sanitization with nested dictionary."""
        data = {
            "user": "alice",
            "config": {
                "endpoint": "https://api.example.com",
                "api_key": "secret-key",
                "credentials": {
                    "secret": "my-secret",
                    "token": "my-token",
                },
            },
        }

        result = sanitize_dict(data)

        # Nested sensitive fields should be redacted
        assert result["config"]["api_key"] == DEFAULT_REDACTED
        assert result["config"]["credentials"]["secret"] == DEFAULT_REDACTED
        assert result["config"]["credentials"]["token"] == DEFAULT_REDACTED
        # Non-sensitive nested fields preserved
        assert result["config"]["endpoint"] == "https://api.example.com"

    def test_sanitize_list_of_dicts(self) -> None:
        """Test sanitization with list of dictionaries."""
        data = {
            "users": [
                {"name": "Alice", "api_key": "key-001"},
                {"name": "Bob", "api_key": "key-002"},
            ]
        }

        result = sanitize_dict(data)

        # All API keys should be redacted
        assert result["users"][0]["api_key"] == DEFAULT_REDACTED
        assert result["users"][1]["api_key"] == DEFAULT_REDACTED
        # Names preserved
        assert result["users"][0]["name"] == "Alice"
        assert result["users"][1]["name"] == "Bob"

    def test_sanitize_list_of_strings(self) -> None:
        """Test sanitization with list of strings (non-sensitive)."""
        data = {"items": ["item1", "item2", "item3"]}

        result = sanitize_dict(data)

        # List should be unchanged
        assert result["items"] == ["item1", "item2", "item3"]

    def test_sanitize_various_sensitive_fields(self) -> None:
        """Test sanitization redacts various sensitive field types."""
        data = {
            "api_key": "key1",
            "API_KEY": "key2",
            "secret": "secret1",
            "password": "pass1",
            "token": "token1",
            "auth": "auth1",
            "credential": "cred1",
            "normal_field": "normal_value",
        }

        result = sanitize_dict(data)

        # All sensitive fields should be redacted
        assert result["api_key"] == DEFAULT_REDACTED
        assert result["API_KEY"] == DEFAULT_REDACTED
        assert result["secret"] == DEFAULT_REDACTED
        assert result["password"] == DEFAULT_REDACTED
        assert result["token"] == DEFAULT_REDACTED
        assert result["auth"] == DEFAULT_REDACTED
        assert result["credential"] == DEFAULT_REDACTED
        # Non-sensitive field preserved
        assert result["normal_field"] == "normal_value"

    def test_sanitize_preserves_non_string_types(self) -> None:
        """Test sanitization preserves non-string types."""
        data = {
            "number": 42,
            "float": 3.14,
            "bool": True,
            "none_value": None,
            "list": [1, 2, 3],
            "api_key": "secret",  # This should be redacted
        }

        result = sanitize_dict(data)

        # Types should be preserved
        assert result["number"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["none_value"] is None
        assert result["list"] == [1, 2, 3]
        # Sensitive string redacted
        assert result["api_key"] == DEFAULT_REDACTED

    def test_sanitize_empty_dict(self) -> None:
        """Test sanitization with empty dictionary."""
        data = {}

        result = sanitize_dict(data)

        assert result == {}

    def test_sanitize_unicode(self) -> None:
        """Test sanitization handles unicode characters."""
        data = {
            "name": "用户",
            "api_key": "secret-世界",
            "emoji": "🔑",
        }

        result = sanitize_dict(data)

        # API key should be redacted
        assert result["api_key"] == DEFAULT_REDACTED
        # Unicode characters preserved
        assert result["name"] == "用户"
        assert result["emoji"] == "🔑"

    def test_sanitize_to_json_string(self) -> None:
        """Test that sanitized data can be serialized to JSON."""
        data = {
            "name": "test",
            "api_key": "secret123",
            "config": {"secret": "my-secret"},
        }

        result = sanitize_dict(data)

        # Should be JSON serializable
        json_str = json.dumps(result, indent=2, ensure_ascii=True)
        parsed = json.loads(json_str)

        assert parsed["api_key"] == DEFAULT_REDACTED
        assert parsed["config"]["secret"] == DEFAULT_REDACTED
        assert parsed["name"] == "test"


# ============================================================================
# File Write Sanitization Tests
# These tests verify sanitization for file write operations
# ============================================================================


class TestFileWriteSanitization:
    """Tests for file write sanitization (used by write_json helper)."""

    def test_sanitize_for_file_write_simple(self, tmp_path: Path) -> None:
        """Test sanitization for simple file write."""
        data = {
            "name": "test",
            "api_key": "secret123",
            "status": "active",
        }

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        # Read and parse file
        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Sensitive field should be redacted
        assert parsed["api_key"] == DEFAULT_REDACTED
        # Non-sensitive fields preserved
        assert parsed["name"] == "test"
        assert parsed["status"] == "active"

    def test_sanitize_for_file_write_nested(self, tmp_path: Path) -> None:
        """Test sanitization for nested file write."""
        data = {
            "user": "alice",
            "config": {
                "endpoint": "https://api.example.com",
                "api_key": "secret-key",
                "credentials": {
                    "secret": "my-secret",
                    "token": "my-token",
                },
            },
        }

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        # Read and parse file
        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # Nested sensitive fields should be redacted
        assert parsed["config"]["api_key"] == DEFAULT_REDACTED
        assert parsed["config"]["credentials"]["secret"] == DEFAULT_REDACTED
        assert parsed["config"]["credentials"]["token"] == DEFAULT_REDACTED

    def test_sanitize_for_file_write_list(self, tmp_path: Path) -> None:
        """Test sanitization for list file write."""
        data = {
            "users": [
                {"name": "Alice", "api_key": "key-001"},
                {"name": "Bob", "api_key": "key-002"},
            ]
        }

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        # Read and parse file
        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # All API keys should be redacted
        assert parsed["users"][0]["api_key"] == DEFAULT_REDACTED
        assert parsed["users"][1]["api_key"] == DEFAULT_REDACTED

    def test_sanitize_for_file_write_unicode(self, tmp_path: Path) -> None:
        """Test sanitization handles unicode characters for file write."""
        data = {
            "name": "用户",
            "api_key": "secret-世界",
            "emoji": "🔑",
        }

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        content = output_file.read_text(encoding="utf-8")
        parsed = json.loads(content)

        # API key should be redacted
        assert parsed["api_key"] == DEFAULT_REDACTED
        # Unicode characters preserved
        assert parsed["name"] == "用户"
        assert parsed["emoji"] == "🔑"

    def test_sanitize_for_file_write_formatted(self, tmp_path: Path) -> None:
        """Test sanitized file write produces formatted output."""
        data = {"name": "test", "api_key": "secret"}

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        content = output_file.read_text(encoding="utf-8")

        # Should be indented
        assert "  " in content or "\n" in content

    def test_sanitize_for_file_write_with_newline(self, tmp_path: Path) -> None:
        """Test sanitized file write adds newline at end."""
        data = {"name": "test"}

        result = sanitize_dict(data)

        # Write sanitized data to file
        output_file = tmp_path / "output.json"
        output_file.write_text(
            json.dumps(result, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

        content = output_file.read_text(encoding="utf-8")

        # Should end with newline
        assert content.endswith("\n")


# ============================================================================
# Integration Tests
# ============================================================================


class TestCliSanitizationIntegration:
    """Integration tests for CLI sanitization scenarios."""

    def test_cli_task_output_scenario(self) -> None:
        """Test realistic CLI task output scenario."""
        # Simulate task listing output
        data = {
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Implement feature",
                    "status": "in_progress",
                    "agent_config": {
                        "model": "gpt-4-32k",
                        "api_key": "sk-proj-abc123",
                    },
                },
                {
                    "id": "task-002",
                    "title": "Write tests",
                    "status": "pending",
                    "agent_config": {
                        "model": "claude-3-opus",
                        "api_key": "sk-ant-def456",
                    },
                },
            ],
            "metadata": {
                "total": 2,
                "user_api_key": "user-secret-key",
            },
        }

        result = sanitize_dict(data)

        # All API keys should be redacted
        assert result["tasks"][0]["agent_config"]["api_key"] == DEFAULT_REDACTED
        assert result["tasks"][1]["agent_config"]["api_key"] == DEFAULT_REDACTED
        assert result["metadata"]["user_api_key"] == DEFAULT_REDACTED

        # Non-sensitive data preserved
        assert result["tasks"][0]["title"] == "Implement feature"
        assert result["tasks"][1]["title"] == "Write tests"
        assert result["metadata"]["total"] == 2

    def test_cli_run_output_scenario(self) -> None:
        """Test realistic CLI run output scenario."""
        # Simulate run status output
        data = {
            "run_id": "run-001",
            "task_id": "task-001",
            "status": "running",
            "agent": "claude-code",
            "config": {
                "model": "claude-3-5-sonnet-20241022",
                "api_key": "sk-ant-secret",
                "max_tokens": 200000,
            },
            "credentials": {
                "access_token": "token-xyz",
                "refresh_token": "refresh-abc",
            },
        }

        result = sanitize_dict(data)

        # Sensitive fields should be redacted
        assert result["config"]["api_key"] == DEFAULT_REDACTED
        assert result["credentials"]["access_token"] == DEFAULT_REDACTED
        assert result["credentials"]["refresh_token"] == DEFAULT_REDACTED

        # Non-sensitive data preserved
        assert result["run_id"] == "run-001"
        assert result["status"] == "running"
        assert result["config"]["max_tokens"] == 200000

    def test_cli_error_output_scenario(self) -> None:
        """Test CLI error output with potential sensitive data."""
        # Simulate error output that might contain sensitive data
        data = {
            "error": "Authentication failed",
            "details": {
                "message": "Invalid API key",
                "api_key": "sk-1234567890",  # Should be redacted
                "endpoint": "https://api.example.com/auth",
            },
            "timestamp": "2024-01-01T00:00:00Z",
        }

        result = sanitize_dict(data)

        # API key in error details should be redacted
        assert result["details"]["api_key"] == DEFAULT_REDACTED

        # Error message preserved
        assert result["error"] == "Authentication failed"

    def test_sanitize_and_serialize_roundtrip(self) -> None:
        """Test that sanitized data can be serialized and deserialized."""
        original_data = {
            "name": "test",
            "api_key": "secret123",
            "config": {"secret": "my-secret"},
        }

        # Sanitize
        sanitized = sanitize_dict(original_data)

        # Serialize to JSON
        json_str = json.dumps(sanitized, indent=2, ensure_ascii=True)

        # Deserialize from JSON
        parsed = json.loads(json_str)

        # Sensitive fields should be redacted
        assert parsed["api_key"] == DEFAULT_REDACTED
        assert parsed["config"]["secret"] == DEFAULT_REDACTED
        assert parsed["name"] == "test"

        # Should be valid JSON that can be parsed again
        assert isinstance(parsed, dict)


# ============================================================================
# Edge Cases
# ============================================================================


class TestCliSanitizationEdgeCases:
    """Tests for edge cases in CLI sanitization."""

    def test_sanitize_none_value(self) -> None:
        """Test sanitization with None value."""
        result = sanitize_value(None, field_name="test")
        assert result is None

    def test_sanitize_string_value(self) -> None:
        """Test sanitization with plain string value."""
        result = sanitize_value("test-string", field_name="test")
        assert result == "test-string"

    def test_sanitize_number_value(self) -> None:
        """Test sanitization with number value."""
        result = sanitize_value(42, field_name="count")
        assert result == 42

    def test_sanitize_bool_value(self) -> None:
        """Test sanitization with boolean value."""
        result = sanitize_value(True, field_name="flag")
        assert result is True

    def test_sanitize_empty_list(self) -> None:
        """Test sanitization with empty list."""
        result = sanitize_dict([])
        assert result == []

    def test_sanitize_list_mixed_types(self) -> None:
        """Test sanitization with list of mixed types."""
        data = {"items": [
            {"api_key": "key1"},
            "string-item",
            123,
            True,
            None,
        ]}

        result = sanitize_dict(data)

        # API key should be redacted
        assert result["items"][0]["api_key"] == DEFAULT_REDACTED
        # Other items preserved
        assert result["items"][1] == "string-item"
        assert result["items"][2] == 123
        assert result["items"][3] is True
        assert result["items"][4] is None

    def test_very_long_api_key(self) -> None:
        """Test sanitization handles very long API keys."""
        long_key = "x" * 10000
        data = {"api_key": long_key, "name": "test"}

        result = sanitize_dict(data)

        # Should be redacted, not the long value
        assert result["api_key"] == DEFAULT_REDACTED
        assert len(result["api_key"]) < len(long_key)

    def test_empty_string_api_key(self) -> None:
        """Test sanitization handles empty string API keys."""
        data = {"api_key": "", "name": "test"}

        result = sanitize_dict(data)

        # Empty string for sensitive field should still be redacted
        assert result["api_key"] == DEFAULT_REDACTED

    def test_nested_empty_dicts(self) -> None:
        """Test sanitization handles nested empty dictionaries."""
        data = {
            "config": {},
            "nested": {
                "empty": {},
                "api_key": "secret",
            },
        }

        result = sanitize_dict(data)

        # API key should be redacted
        assert result["nested"]["api_key"] == DEFAULT_REDACTED
        # Empty dicts preserved
        assert result["config"] == {}
        assert result["nested"]["empty"] == {}

    def test_sanitize_json_string_function(self) -> None:
        """Test sanitize_json() function with JSON string."""
        json_str = '{"api_key": "secret123", "name": "test"}'

        result = sanitize_json(json_str)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["api_key"] == DEFAULT_REDACTED
        assert parsed["name"] == "test"

    def test_sanitize_json_string_nested(self) -> None:
        """Test sanitize_json() with nested JSON string."""
        json_str = '{"user": {"name": "Alice", "api_key": "secret"}}'

        result = sanitize_json(json_str)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["user"]["name"] == "Alice"
        assert parsed["user"]["api_key"] == DEFAULT_REDACTED

    def test_sanitize_json_string_invalid(self) -> None:
        """Test sanitize_json() raises ValueError for invalid JSON."""
        json_str = '{"api_key": "secret", invalid}'

        with pytest.raises(ValueError, match="Invalid JSON"):
            sanitize_json(json_str)
