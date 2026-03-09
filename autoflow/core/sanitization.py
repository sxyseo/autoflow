"""
Autoflow Sanitization Module

Provides utilities for sanitizing sensitive data from JSON output and logs.
Redacts API keys, secrets, passwords, tokens, and other sensitive information
to prevent information disclosure (CWE-200).

Usage:
    from autoflow.core.sanitization import sanitize_dict, sanitize_value

    # Sanitize a dictionary
    clean_data = sanitize_dict({"api_key": "secret123", "name": "test"})

    # Sanitize a single value
    clean_value = sanitize_value("my-secret-token", redact_with="***")
"""

from __future__ import annotations

import re
from typing import Any, Optional, Set, Union

from pydantic import BaseModel, Field


# Default redaction marker
DEFAULT_REDACTED = "***REDACTED***"

# Patterns that indicate sensitive field names
SENSITIVE_PATTERNS = [
    "api[_-]?key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "token",
    "auth",
    "credential",
    "private[_-]?key",
    "access[_-]?token",
    "refresh[_-]?token",
    "session[_-]?key",
    "csrf",
    "bearer",
    # Model, tool, and transport configurations - these support partial redaction
    # but are redacted by default for security
    r"\bmodel\b",  # Use word boundaries to avoid matching "models"
    "model[_-]?profile",
    "tool[_-]?profile",
    "memory[_-]?scope",
    "transport",
]

# Compiled regex patterns for matching sensitive field names (case-insensitive)
_SENSITIVE_REGEX = re.compile(
    "|".join(f"(?:{pattern})" for pattern in SENSITIVE_PATTERNS),
    re.IGNORECASE
)

# Fields that should be partially redacted (show first/last few chars)
# Note: These are only used when partial_redaction is enabled in config
# Fields here must also be in SENSITIVE_PATTERNS to be redacted by default
PARTIAL_REDACT_PATTERNS = [
    r"\bmodel\b",  # Use word boundaries to avoid matching "models"
    "model[_-]?profile",
    "agent[_-]?id",
    "transport",
]


class SanitizationConfig(BaseModel):
    """
    Configuration for data sanitization.

    Controls which fields are redacted and how they are redacted.
    """

    enabled: bool = True
    """Whether sanitization is enabled."""

    redacted_marker: str = DEFAULT_REDACTED
    """String to use as replacement for redacted values."""

    partial_redaction: bool = False
    """Whether to partially redact values (show first/last N chars)."""

    partial_chars: int = 4
    """Number of characters to show at start/end when partially redacting."""

    custom_sensitive_fields: Set[str] = Field(default_factory=set)
    """Additional field names that should be treated as sensitive."""

    excluded_fields: Set[str] = Field(default_factory=set)
    """Field names to exclude from sanitization (whitelist)."""

    recursive: bool = True
    """Whether to recursively sanitize nested dictionaries and lists."""

    def is_sensitive_field(self, field_name: str) -> bool:
        """
        Check if a field name should be treated as sensitive.

        Args:
            field_name: The field name to check

        Returns:
            True if the field should be sanitized, False otherwise
        """
        # Check whitelist first
        if field_name in self.excluded_fields:
            return False

        # Check custom sensitive fields
        if field_name in self.custom_sensitive_fields:
            return True

        # Check against sensitive patterns
        return _SENSITIVE_REGEX.search(field_name) is not None

    def is_partial_redact_field(self, field_name: str) -> bool:
        """
        Check if a field should be partially redacted.

        Partial redaction shows first/last N characters instead of
        completely replacing the value.

        Args:
            field_name: The field name to check

        Returns:
            True if the field should be partially redacted
        """
        for pattern in PARTIAL_REDACT_PATTERNS:
            if re.search(f"(?i){pattern}", field_name):
                return True
        return False


def _partial_redact(value: str, chars: int) -> str:
    """
    Partially redact a string value.

    Shows the first and last N characters with asterisks in between.

    Args:
        value: The string value to partially redact
        chars: Number of characters to show at start and end

    Returns:
        Partially redacted string

    Examples:
        >>> _partial_redact("sk-1234567890abcdef", 4)
        'sk-12...cdef'
        >>> _partial_redact("short", 2)
        'sh...rt'
    """
    if len(value) <= chars * 2:
        # Value too short, fully redact
        return DEFAULT_REDACTED

    return f"{value[:chars]}...{value[-chars:]}"


def _sanitize_string_value(
    value: str,
    field_name: str,
    config: SanitizationConfig,
) -> str:
    """
    Sanitize a string value based on field name and configuration.

    Args:
        value: The string value to sanitize
        field_name: The name of the field containing the value
        config: Sanitization configuration

    Returns:
        Sanitized string value
    """
    if not config.enabled:
        return value

    if config.is_partial_redact_field(field_name) and config.partial_redaction:
        return _partial_redact(value, config.partial_chars)

    if config.is_sensitive_field(field_name):
        return config.redacted_marker

    return value


def sanitize_dict(
    data: dict[str, Any],
    config: Optional[SanitizationConfig] = None,
    _context: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Sanitize a dictionary by redacting sensitive field values.

    Recursively processes nested dictionaries and lists, redacting
    values for fields that match sensitive patterns.

    Args:
        data: The dictionary to sanitize
        config: Optional sanitization configuration (uses defaults if not provided)
        _context: Internal tracking of nested keys to prevent infinite recursion

    Returns:
        A new dictionary with sensitive values redacted

    Examples:
        >>> sanitize_dict({"api_key": "secret123", "name": "test"})
        {'api_key': '***REDACTED***', 'name': 'test'}

        >>> sanitize_dict({"user": {"token": "abc", "id": "123"}})
        {'user': {'token': '***REDACTED***', 'id': '123'}}

        >>> config = SanitizationConfig(partial_redaction=True, partial_chars=2)
        >>> sanitize_dict({"model": "gpt-4-32k"}, config)
        {'model': 'gp...2k'}
    """
    if config is None:
        config = SanitizationConfig()

    if not config.enabled or not isinstance(data, dict):
        return data

    # Track recursion context to prevent infinite loops
    if _context is None:
        _context = set()

    result = {}

    for key, value in data.items():
        # Create context for nested tracking
        current_context = _context | {key}

        # Handle nested dictionaries
        if isinstance(value, dict) and config.recursive:
            result[key] = sanitize_dict(value, config, current_context)

        # Handle lists (recursively sanitize items)
        elif isinstance(value, list) and config.recursive:
            result[key] = [
                sanitize_dict(item, config, current_context) if isinstance(item, dict)
                else _sanitize_string_value(item, key, config) if isinstance(item, str)
                else item
                for item in value
            ]

        # Handle strings (check for sensitive fields)
        elif isinstance(value, str):
            result[key] = _sanitize_string_value(value, key, config)

        # Keep other types as-is
        else:
            result[key] = value

    return result


def sanitize_value(
    value: Any,
    field_name: str = "",
    config: Optional[SanitizationConfig] = None,
) -> Any:
    """
    Sanitize a single value based on its field name.

    For dictionaries and lists, performs recursive sanitization.
    For strings, checks if the field name indicates sensitive data.

    Args:
        value: The value to sanitize
        field_name: Optional field name for context
        config: Optional sanitization configuration

    Returns:
        Sanitized value

    Examples:
        >>> sanitize_value("secret-token", field_name="api_key")
        '***REDACTED***'

        >>> sanitize_value({"api_key": "secret"}, field_name="config")
        {'api_key': '***REDACTED***'}
    """
    if config is None:
        config = SanitizationConfig()

    if not config.enabled:
        return value

    # Handle dictionaries
    if isinstance(value, dict):
        return sanitize_dict(value, config)

    # Handle lists
    if isinstance(value, list) and config.recursive:
        return [
            sanitize_value(item, field_name, config)
            for item in value
        ]

    # Handle strings
    if isinstance(value, str) and field_name:
        return _sanitize_string_value(value, field_name, config)

    return value


def sanitize_json(
    json_str: str,
    config: Optional[SanitizationConfig] = None,
) -> str:
    """
    Parse and sanitize a JSON string.

    Parses the JSON string, sanitizes sensitive data, and returns
    the sanitized JSON as a string.

    Args:
        json_str: JSON string to sanitize
        config: Optional sanitization configuration

    Returns:
        Sanitized JSON string

    Raises:
        ValueError: If the input is not valid JSON

    Examples:
        >>> sanitize_json('{"api_key": "secret", "name": "test"}')
        '{"api_key": "***REDACTED***", "name": "test"}'
    """
    import json

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    sanitized = sanitize_dict(data, config)
    return json.dumps(sanitized, indent=2, ensure_ascii=True)


def create_sanitize_config(
    *,
    enabled: bool = True,
    redacted_marker: str = DEFAULT_REDACTED,
    partial_redaction: bool = False,
    partial_chars: int = 4,
    custom_sensitive_fields: Optional[list[str]] = None,
    excluded_fields: Optional[list[str]] = None,
) -> SanitizationConfig:
    """
    Create a SanitizationConfig with the specified settings.

    Convenience function for creating sanitization configuration
    with keyword arguments for better readability.

    Args:
        enabled: Whether sanitization is enabled
        redacted_marker: String to use as replacement for redacted values
        partial_redaction: Whether to partially redact values
        partial_chars: Number of characters to show when partially redacting
        custom_sensitive_fields: Additional field names to treat as sensitive
        excluded_fields: Field names to exclude from sanitization

    Returns:
        SanitizationConfig object with specified settings

    Examples:
        >>> config = create_sanitize_config(
        ...     partial_redaction=True,
        ...     partial_chars=2,
        ...     excluded_fields=["model_name"]
        ... )
        >>> sanitize_dict({"model": "gpt-4"}, config)
        {'model': 'gp...4'}
    """
    return SanitizationConfig(
        enabled=enabled,
        redacted_marker=redacted_marker,
        partial_redaction=partial_redaction,
        partial_chars=partial_chars,
        custom_sensitive_fields=set(custom_sensitive_fields or []),
        excluded_fields=set(excluded_fields or []),
    )


# Default sanitization configuration
default_config = SanitizationConfig()
