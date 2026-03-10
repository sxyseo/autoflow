"""
Unit Tests for Autoflow Sanitization Module

Tests the SanitizationConfig class and sanitization functions
for redacting sensitive data from JSON output and logs.

These tests verify that sensitive information (API keys, secrets, passwords,
tokens, etc.) is properly redacted to prevent information disclosure (CWE-200).
"""

from __future__ import annotations

from typing import Any

import pytest

from autoflow.core.sanitization import (
    DEFAULT_REDACTED,
    SanitizationConfig,
    _partial_redact,
    _sanitize_string_value,
    create_sanitize_config,
    sanitize_dict,
    sanitize_json,
    sanitize_value,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_sensitive_data() -> dict[str, Any]:
    """Return sample data with sensitive fields for testing."""
    return {
        "api_key": "sk-1234567890abcdef",
        "name": "test_user",
        "password": "super_secret_123",
        "email": "user@example.com",
        "token": "bearer-token-xyz",
        "model": "gpt-4-32k",
        "id": "user_12345",
    }


@pytest.fixture
def sample_nested_data() -> dict[str, Any]:
    """Return sample nested data with sensitive fields."""
    return {
        "user": {
            "name": "Alice",
            "credentials": {
                "api_key": "secret-key-123",
                "secret": "my-secret-value",
            },
        },
        "config": {
            "model": "claude-3-opus",
            "endpoint": "https://api.example.com",
        },
    }


@pytest.fixture
def sample_list_data() -> dict[str, Any]:
    """Return sample data with lists containing sensitive fields."""
    return {
        "users": [
            {"name": "Alice", "api_key": "key-alice-123"},
            {"name": "Bob", "api_key": "key-bob-456"},
        ],
        "models": ["gpt-4", "claude-3", "gemini-pro"],
    }


# ============================================================================
# SanitizationConfig Tests
# ============================================================================


class TestSanitizationConfig:
    """Tests for SanitizationConfig class."""

    def test_config_defaults(self) -> None:
        """Test SanitizationConfig default values."""
        config = SanitizationConfig()

        assert config.enabled is True
        assert config.redacted_marker == DEFAULT_REDACTED
        assert config.partial_redaction is False
        assert config.partial_chars == 4
        assert config.custom_sensitive_fields == set()
        assert config.excluded_fields == set()
        assert config.recursive is True

    def test_config_custom_values(self) -> None:
        """Test SanitizationConfig with custom values."""
        config = SanitizationConfig(
            enabled=False,
            redacted_marker="[REDACTED]",
            partial_redaction=True,
            partial_chars=2,
            custom_sensitive_fields={"custom_field"},
            excluded_fields={"safe_field"},
            recursive=False,
        )

        assert config.enabled is False
        assert config.redacted_marker == "[REDACTED]"
        assert config.partial_redaction is True
        assert config.partial_chars == 2
        assert config.custom_sensitive_fields == {"custom_field"}
        assert config.excluded_fields == {"safe_field"}
        assert config.recursive is False

    def test_is_sensitive_field_api_key(self) -> None:
        """Test is_sensitive_field matches api_key patterns."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("api_key") is True
        assert config.is_sensitive_field("apiKey") is True
        assert config.is_sensitive_field("API_KEY") is True
        assert config.is_sensitive_field("api-key") is True

    def test_is_sensitive_field_secret(self) -> None:
        """Test is_sensitive_field matches secret patterns."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("secret") is True
        assert config.is_sensitive_field("client_secret") is True
        assert config.is_sensitive_field("SECRET") is True

    def test_is_sensitive_field_password(self) -> None:
        """Test is_sensitive_field matches password patterns."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("password") is True
        assert config.is_sensitive_field("passwd") is True
        assert config.is_sensitive_field("PASSWORD") is True
        assert config.is_sensitive_field("user_password") is True

    def test_is_sensitive_field_token(self) -> None:
        """Test is_sensitive_field matches token patterns."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("token") is True
        assert config.is_sensitive_field("access_token") is True
        assert config.is_sensitive_field("refresh_token") is True
        assert config.is_sensitive_field("session_token") is True
        assert config.is_sensitive_field("csrf_token") is True
        assert config.is_sensitive_field("bearer_token") is True

    def test_is_sensitive_field_auth(self) -> None:
        """Test is_sensitive_field matches auth patterns."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("auth") is True
        assert config.is_sensitive_field("credential") is True
        assert config.is_sensitive_field("private_key") is True

    def test_is_sensitive_field_custom(self) -> None:
        """Test is_sensitive_field with custom sensitive fields."""
        config = SanitizationConfig(custom_sensitive_fields={"my_custom_field"})

        assert config.is_sensitive_field("my_custom_field") is True
        assert config.is_sensitive_field("api_key") is True  # Default still works

    def test_is_sensitive_field_excluded(self) -> None:
        """Test is_sensitive_field with excluded fields."""
        config = SanitizationConfig(excluded_fields={"safe_api_key"})

        assert config.is_sensitive_field("safe_api_key") is False
        assert config.is_sensitive_field("api_key") is True  # Others still sensitive

    def test_is_sensitive_field_non_sensitive(self) -> None:
        """Test is_sensitive_field returns False for non-sensitive fields."""
        config = SanitizationConfig()

        assert config.is_sensitive_field("name") is False
        assert config.is_sensitive_field("id") is False
        assert config.is_sensitive_field("email") is False
        assert config.is_sensitive_field("description") is False

    def test_is_partial_redact_field_model(self) -> None:
        """Test is_partial_redact_field matches model patterns."""
        config = SanitizationConfig()

        assert config.is_partial_redact_field("model") is True
        assert config.is_partial_redact_field("MODEL") is True
        assert config.is_partial_redact_field("model_profile") is True
        assert config.is_partial_redact_field("model-profile") is True

    def test_is_partial_redact_field_agent(self) -> None:
        """Test is_partial_redact_field matches agent patterns."""
        config = SanitizationConfig()

        assert config.is_partial_redact_field("agent_id") is True
        assert config.is_partial_redact_field("agentID") is True
        assert config.is_partial_redact_field("agent-id") is True

    def test_is_partial_redact_field_transport(self) -> None:
        """Test is_partial_redact_field matches transport pattern."""
        config = SanitizationConfig()

        assert config.is_partial_redact_field("transport") is True
        assert config.is_partial_redact_field("TRANSPORT") is True

    def test_is_partial_redact_field_non_partial(self) -> None:
        """Test is_partial_redact_field returns False for non-partial fields."""
        config = SanitizationConfig()

        assert config.is_partial_redact_field("name") is False
        assert config.is_partial_redact_field("id") is False
        assert config.is_partial_redact_field("api_key") is False


# ============================================================================
# Partial Redaction Tests
# ============================================================================


class TestPartialRedaction:
    """Tests for _partial_redact function."""

    def test_partial_redact_long_string(self) -> None:
        """Test _partial_redact with long enough string."""
        result = _partial_redact("sk-1234567890abcdef", 4)

        assert result == "sk-1...cdef"

    def test_partial_redact_short_string(self) -> None:
        """Test _partial_redact with short string."""
        result = _partial_redact("short", 2)

        # "short" has length 5, which is > 2*2=4, so it gets partially redacted
        assert result == "sh...rt"

    def test_partial_redact_exact_length(self) -> None:
        """Test _partial_redact with string exactly 2*chars long."""
        result = _partial_redact("abcdefgh", 4)

        # Length is exactly 2*chars, should still fully redact
        assert result == DEFAULT_REDACTED

    def test_partial_redact_one_more_than_minimum(self) -> None:
        """Test _partial_redact with string one char longer than minimum."""
        result = _partial_redact("abcdefghi", 4)

        assert result == "abcd...fghi"

    def test_partial_redact_custom_chars(self) -> None:
        """Test _partial_redact with custom char count."""
        result = _partial_redact("sk-1234567890abcdef", 2)

        assert result == "sk...ef"

    def test_partial_redact_single_char(self) -> None:
        """Test _partial_redact with single char count."""
        result = _partial_redact("sk-1234567890abcdef", 1)

        assert result == "s...f"


# ============================================================================
# String Value Sanitization Tests
# ============================================================================


class TestSanitizeStringValue:
    """Tests for _sanitize_string_value function."""

    def test_sanitize_string_sensitive_field(self) -> None:
        """Test _sanitize_string_value redacts sensitive fields."""
        config = SanitizationConfig()

        result = _sanitize_string_value("secret-value", "api_key", config)

        assert result == DEFAULT_REDACTED

    def test_sanitize_string_non_sensitive_field(self) -> None:
        """Test _sanitize_string_value keeps non-sensitive fields."""
        config = SanitizationConfig()

        result = _sanitize_string_value("my-name", "name", config)

        assert result == "my-name"

    def test_sanitize_string_disabled(self) -> None:
        """Test _sanitize_string_value with sanitization disabled."""
        config = SanitizationConfig(enabled=False)

        result = _sanitize_string_value("secret-value", "api_key", config)

        assert result == "secret-value"

    def test_sanitize_string_partial_redaction(self) -> None:
        """Test _sanitize_string_value with partial redaction."""
        config = SanitizationConfig(partial_redaction=True, partial_chars=4)

        result = _sanitize_string_value("gpt-4-32k", "model", config)

        assert result == "gpt-...-32k"

    def test_sanitize_string_custom_marker(self) -> None:
        """Test _sanitize_string_value with custom redaction marker."""
        config = SanitizationConfig(redacted_marker="[REDACTED]")

        result = _sanitize_string_value("secret-value", "api_key", config)

        assert result == "[REDACTED]"

    def test_sanitize_string_excluded_field(self) -> None:
        """Test _sanitize_string_value with excluded field."""
        config = SanitizationConfig(excluded_fields={"safe_api_key"})

        result = _sanitize_string_value("secret-value", "safe_api_key", config)

        assert result == "secret-value"  # Not redacted


# ============================================================================
# Dictionary Sanitization Tests
# ============================================================================


class TestSanitizeDict:
    """Tests for sanitize_dict function."""

    def test_sanitize_dict_simple(self, sample_sensitive_data: dict) -> None:
        """Test sanitize_dict with simple dictionary."""
        result = sanitize_dict(sample_sensitive_data)

        assert result["api_key"] == DEFAULT_REDACTED
        assert result["name"] == "test_user"
        assert result["password"] == DEFAULT_REDACTED
        assert result["email"] == "user@example.com"
        assert result["token"] == DEFAULT_REDACTED
        assert result["id"] == "user_12345"

    def test_sanitize_dict_nested(self, sample_nested_data: dict) -> None:
        """Test sanitize_dict with nested dictionary."""
        result = sanitize_dict(sample_nested_data)

        assert result["user"]["name"] == "Alice"
        assert result["user"]["credentials"]["api_key"] == DEFAULT_REDACTED
        assert result["user"]["credentials"]["secret"] == DEFAULT_REDACTED
        assert result["config"]["endpoint"] == "https://api.example.com"

    def test_sanitize_dict_with_lists(self, sample_list_data: dict) -> None:
        """Test sanitize_dict with list values."""
        result = sanitize_dict(sample_list_data)

        # Users' API keys should be redacted
        assert result["users"][0]["name"] == "Alice"
        assert result["users"][0]["api_key"] == DEFAULT_REDACTED
        assert result["users"][1]["name"] == "Bob"
        assert result["users"][1]["api_key"] == DEFAULT_REDACTED

        # String list should be unchanged
        assert result["models"] == ["gpt-4", "claude-3", "gemini-pro"]

    def test_sanitize_dict_disabled(self, sample_sensitive_data: dict) -> None:
        """Test sanitize_dict with sanitization disabled."""
        config = SanitizationConfig(enabled=False)

        result = sanitize_dict(sample_sensitive_data, config)

        # Nothing should be redacted
        assert result["api_key"] == "sk-1234567890abcdef"
        assert result["password"] == "super_secret_123"
        assert result["token"] == "bearer-token-xyz"

    def test_sanitize_dict_custom_config(self) -> None:
        """Test sanitize_dict with custom configuration."""
        data = {"model": "gpt-4-32k", "api_key": "secret"}
        config = SanitizationConfig(
            partial_redaction=True,
            partial_chars=2,
            redacted_marker="[XXX]",
        )

        result = sanitize_dict(data, config)

        assert result["model"] == "gp...2k"
        assert result["api_key"] == "[XXX]"

    def test_sanitize_dict_non_recursive(self, sample_nested_data: dict) -> None:
        """Test sanitize_dict without recursion."""
        config = SanitizationConfig(recursive=False)

        result = sanitize_dict(sample_nested_data, config)

        # Nested dict should be preserved as-is
        assert "credentials" in result["user"]
        # But nested sensitive fields won't be redacted
        assert result["user"]["credentials"]["api_key"] == "secret-key-123"

    def test_sanitize_dict_empty(self) -> None:
        """Test sanitize_dict with empty dictionary."""
        result = sanitize_dict({})

        assert result == {}

    def test_sanitize_dict_non_dict_input(self) -> None:
        """Test sanitize_dict with non-dict input."""
        result = sanitize_dict("not a dict")

        assert result == "not a dict"

    def test_sanitize_dict_preserves_non_sensitive_types(self) -> None:
        """Test sanitize_dict preserves non-string types."""
        data = {
            "number": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
            "list": [1, 2, 3],
        }

        result = sanitize_dict(data)

        assert result["number"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["none"] is None
        assert result["list"] == [1, 2, 3]


# ============================================================================
# Value Sanitization Tests
# ============================================================================


class TestSanitizeValue:
    """Tests for sanitize_value function."""

    def test_sanitize_value_string(self) -> None:
        """Test sanitize_value with string value."""
        result = sanitize_value("secret-value", field_name="api_key")

        assert result == DEFAULT_REDACTED

    def test_sanitize_value_dict(self) -> None:
        """Test sanitize_value with dict value."""
        value = {"api_key": "secret", "name": "test"}

        result = sanitize_value(value, field_name="config")

        assert result["api_key"] == DEFAULT_REDACTED
        assert result["name"] == "test"

    def test_sanitize_value_list(self) -> None:
        """Test sanitize_value with list value."""
        value = [{"api_key": "key1"}, {"api_key": "key2"}]

        result = sanitize_value(value, field_name="users")

        assert result[0]["api_key"] == DEFAULT_REDACTED
        assert result[1]["api_key"] == DEFAULT_REDACTED

    def test_sanitize_value_no_field_name(self) -> None:
        """Test sanitize_value without field name."""
        result = sanitize_value("some-value")

        assert result == "some-value"  # No context to determine sensitivity

    def test_sanitize_value_non_sensitive(self) -> None:
        """Test sanitize_value with non-sensitive field."""
        result = sanitize_value("my-name", field_name="name")

        assert result == "my-name"

    def test_sanitize_value_disabled(self) -> None:
        """Test sanitize_value with sanitization disabled."""
        config = SanitizationConfig(enabled=False)

        result = sanitize_value("secret-value", field_name="api_key", config=config)

        assert result == "secret-value"

    def test_sanitize_value_preserves_types(self) -> None:
        """Test sanitize_value preserves non-string types."""
        assert sanitize_value(42, field_name="count") == 42
        assert sanitize_value(3.14, field_name="pi") == 3.14
        assert sanitize_value(True, field_name="flag") is True
        assert sanitize_value(None, field_name="nothing") is None


# ============================================================================
# JSON Sanitization Tests
# ============================================================================


class TestSanitizeJSON:
    """Tests for sanitize_json function."""

    def test_sanitize_json_valid(self) -> None:
        """Test sanitize_json with valid JSON string."""
        json_str = '{"api_key": "secret123", "name": "test"}'

        result = sanitize_json(json_str)

        # Should be valid JSON
        import json

        parsed = json.loads(result)
        assert parsed["api_key"] == DEFAULT_REDACTED
        assert parsed["name"] == "test"

    def test_sanitize_json_nested(self) -> None:
        """Test sanitize_json with nested JSON."""
        json_str = '{"user": {"name": "Alice", "api_key": "secret"}}'

        result = sanitize_json(json_str)

        import json

        parsed = json.loads(result)
        assert parsed["user"]["name"] == "Alice"
        assert parsed["user"]["api_key"] == DEFAULT_REDACTED

    def test_sanitize_json_invalid(self) -> None:
        """Test sanitize_json raises ValueError for invalid JSON."""
        json_str = '{"api_key": "secret", invalid}'

        with pytest.raises(ValueError, match="Invalid JSON"):
            sanitize_json(json_str)

    def test_sanitize_json_with_config(self) -> None:
        """Test sanitize_json with custom configuration."""
        json_str = '{"model": "gpt-4-32k", "api_key": "secret"}'
        config = SanitizationConfig(
            partial_redaction=True,
            partial_chars=2,
        )

        result = sanitize_json(json_str, config)

        import json

        parsed = json.loads(result)
        assert parsed["model"] == "gp...2k"
        assert parsed["api_key"] == DEFAULT_REDACTED

    def test_sanitize_json_formatted(self) -> None:
        """Test sanitize_json produces formatted output."""
        json_str = '{"api_key": "secret", "name": "test"}'

        result = sanitize_json(json_str)

        # Should be indented
        assert "  " in result or "\n" in result


# ============================================================================
# Configuration Creation Tests
# ============================================================================


class TestCreateSanitizeConfig:
    """Tests for create_sanitize_config function."""

    def test_create_config_defaults(self) -> None:
        """Test create_sanitize_config with defaults."""
        config = create_sanitize_config()

        assert config.enabled is True
        assert config.redacted_marker == DEFAULT_REDACTED
        assert config.partial_redaction is False
        assert config.partial_chars == 4
        assert config.custom_sensitive_fields == set()
        assert config.excluded_fields == set()

    def test_create_config_custom(self) -> None:
        """Test create_sanitize_config with custom values."""
        config = create_sanitize_config(
            enabled=False,
            redacted_marker="[REDACTED]",
            partial_redaction=True,
            partial_chars=2,
            custom_sensitive_fields=["field1", "field2"],
            excluded_fields=["safe_field"],
        )

        assert config.enabled is False
        assert config.redacted_marker == "[REDACTED]"
        assert config.partial_redaction is True
        assert config.partial_chars == 2
        assert config.custom_sensitive_fields == {"field1", "field2"}
        assert config.excluded_fields == {"safe_field"}

    def test_create_config_partial_only(self) -> None:
        """Test create_sanitize_config with partial redaction only."""
        config = create_sanitize_config(
            partial_redaction=True,
            partial_chars=3,
        )

        assert config.partial_redaction is True
        assert config.partial_chars == 3
        assert config.enabled is True  # Default


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and integration scenarios."""

    def test_sanitize_mixed_nested_lists(self) -> None:
        """Test sanitizing deeply nested mixed structures."""
        data = {
            "items": [
                {
                    "name": "item1",
                    "config": {"api_key": "key1"},
                    "tags": ["tag1", "tag2"],
                },
                {
                    "name": "item2",
                    "config": {"secret": "secret2"},
                    "values": [1, 2, 3],
                },
            ],
        }

        result = sanitize_dict(data)

        assert result["items"][0]["config"]["api_key"] == DEFAULT_REDACTED
        assert result["items"][0]["tags"] == ["tag1", "tag2"]
        assert result["items"][1]["config"]["secret"] == DEFAULT_REDACTED
        assert result["items"][1]["values"] == [1, 2, 3]

    def test_sanitize_unicode_values(self) -> None:
        """Test sanitization works with unicode strings."""
        data = {"api_key": "secret-世界-🔑", "name": "用户"}

        result = sanitize_dict(data)

        assert result["api_key"] == DEFAULT_REDACTED
        assert result["name"] == "用户"

    def test_sanitize_empty_strings(self) -> None:
        """Test sanitization handles empty strings."""
        data = {"api_key": "", "name": ""}

        result = sanitize_dict(data)

        assert result["api_key"] == DEFAULT_REDACTED
        assert result["name"] == ""

    def test_sanitize_very_long_values(self) -> None:
        """Test sanitization handles very long values."""
        long_value = "x" * 10000
        data = {"api_key": long_value}

        result = sanitize_dict(data)

        assert result["api_key"] == DEFAULT_REDACTED

    def test_sanitize_with_custom_sensitive_field(self) -> None:
        """Test custom sensitive fields are redacted."""
        data = {"my_custom_field": "sensitive", "normal": "value"}
        config = SanitizationConfig(custom_sensitive_fields={"my_custom_field"})

        result = sanitize_dict(data, config)

        assert result["my_custom_field"] == DEFAULT_REDACTED
        assert result["normal"] == "value"

    def test_sanitize_exclude_overrides_pattern(self) -> None:
        """Test excluded fields override pattern matching."""
        data = {"api_key": "secret", "public_key": "value"}
        config = SanitizationConfig(excluded_fields={"api_key"})

        result = sanitize_dict(data, config)

        assert result["api_key"] == "secret"  # Not redacted
        # Note: public_key doesn't match the pattern by default

    def test_sanitize_preserves_dict_identity(self) -> None:
        """Test that sanitize_dict creates a new dict."""
        data = {"api_key": "secret", "name": "test"}

        result = sanitize_dict(data)

        # Should be a new object
        assert result is not data
        # Original should be unchanged
        assert data["api_key"] == "secret"

    def test_sanitize_with_none_values(self) -> None:
        """Test sanitization handles None values."""
        data = {"api_key": None, "name": "test"}

        result = sanitize_dict(data)

        assert result["api_key"] is None
        assert result["name"] == "test"

    def test_sanitize_boolean_values(self) -> None:
        """Test sanitization preserves boolean values."""
        data = {"enabled": True, "disabled": False}

        result = sanitize_dict(data)

        assert result["enabled"] is True
        assert result["disabled"] is False

    def test_partial_redact_short_value(self) -> None:
        """Test partial redaction with value too short."""
        data = {"model": "x"}  # Too short to partially redact
        config = SanitizationConfig(partial_redaction=True, partial_chars=4)

        result = sanitize_dict(data, config)

        assert result["model"] == DEFAULT_REDACTED

    def test_default_config_is_singleton(self) -> None:
        """Test that default_config is accessible."""
        from autoflow.core.sanitization import default_config

        assert isinstance(default_config, SanitizationConfig)
        assert default_config.enabled is True


# ============================================================================
# Security-Focused Tests
# ============================================================================


class TestSecurityScenarios:
    """Tests for real-world security scenarios."""

    def test_multiple_api_keys(self) -> None:
        """Test multiple API key variants are redacted."""
        data = {
            "api_key": "key1",
            "API_KEY": "key2",
            "ApiKey": "key3",
            "apiKey": "key4",
            "api-key": "key5",
        }

        result = sanitize_dict(data)

        # All variants should be redacted
        for key in result:
            assert result[key] == DEFAULT_REDACTED

    def test_credential_variations(self) -> None:
        """Test various credential fields are redacted."""
        data = {
            "access_token": "token1",
            "refresh_token": "token2",
            "session_key": "key1",
            "csrf_token": "token3",
            "bearer": "bearer1",
            "private_key": "key2",
            "client_secret": "secret1",
        }

        result = sanitize_dict(data)

        for key in result:
            assert result[key] == DEFAULT_REDACTED

    def test_nested_credentials(self) -> None:
        """Test credentials at various nesting levels."""
        data = {
            "level1": {
                "api_key": "key1",
                "level2": {
                    "secret": "secret1",
                    "level3": {
                        "token": "token1",
                    },
                },
            },
        }

        result = sanitize_dict(data)

        assert result["level1"]["api_key"] == DEFAULT_REDACTED
        assert result["level1"]["level2"]["secret"] == DEFAULT_REDACTED
        assert result["level1"]["level2"]["level3"]["token"] == DEFAULT_REDACTED

    def test_log_output_scenario(self) -> None:
        """Test realistic log output scenario."""
        log_data = {
            "timestamp": "2024-01-01T00:00:00Z",
            "event": "api_call",
            "request": {
                "url": "https://api.example.com/endpoint",
                "headers": {
                    "Authorization": "Bearer secret-token",
                    "X-API-Key": "api-key-123",
                },
                "params": {"user": "alice"},
            },
            "response": {
                "status": 200,
                "access_token": "new-token-456",
            },
        }

        result = sanitize_dict(log_data)

        # Sensitive fields should be redacted
        assert result["request"]["headers"]["X-API-Key"] == DEFAULT_REDACTED
        assert result["response"]["access_token"] == DEFAULT_REDACTED
        # Non-sensitive should be preserved
        assert result["request"]["url"] == "https://api.example.com/endpoint"
        assert result["request"]["params"]["user"] == "alice"
        assert result["response"]["status"] == 200
