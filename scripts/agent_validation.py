"""
Autoflow Agent Validation Module

Provides validation and sanitization for agent configuration to prevent
command injection attacks. Uses allowlist validation and pattern matching
to ensure only safe commands and arguments are executed.

Usage:
    from scripts.agent_validation import AgentSpecValidator, validate_path

    # Validate agent specification
    validator = AgentSpecValidator(
        command="claude",
        args=["--print"],
        model="claude-3-5-sonnet-20241022"
    )
    validator.validate_command()
    validator.validate_args()

    # Validate file paths
    validate_path("/etc/passwd", base_dir="/workspace")  # Raises ValidationError
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# Security: Allowlist of permitted commands
ALLOWED_COMMANDS = frozenset({
    "claude",
    "codex",
    "acp-agent",
})

# Security: Shell metacharacters that indicate command injection attempts
SHELL_METACHARACTERS = frozenset({
    "|",  # Pipe
    "&",  # Background/command separator
    ";",  # Command separator
    "$",  # Variable expansion
    "`",  # Command substitution
    "\n",  # Command separator (newline)
    "\r",  # Command separator (carriage return)
    "(",  # Subshell
    ")",  # Subshell
    "<",  # Redirect
    ">",  # Redirect
    "\\",  # Escape character (could be used to bypass filters)
})

# Security: Flags that could enable command execution
DANGEROUS_FLAGS = frozenset({
    "--exec",
    "--execute",
    "--eval",
    "--evaluate",
    "-e",
    "-c",
    "-x",
    "/bin/sh",
    "/bin/bash",
    "sh -c",
    "bash -c",
    "exec(",
    "eval(",
    "system(",
})


class ValidationError(Exception):
    """Exception raised for validation failures."""

    def __init__(self, message: str, field: str, value: Any = None):
        """
        Initialize validation error.

        Args:
            message: Error description
            field: Field name that failed validation
            value: The invalid value (optional, for security)
        """
        self.field = field
        self.value = value
        super().__init__(message)


class AgentSpecValidator(BaseModel):
    """
    Validator for agent specification fields.

    Provides validation methods for each field in an agent specification
    to prevent command injection attacks.

    Attributes:
        command: The command to execute (e.g., "claude", "codex")
        args: List of command arguments
        runtime_args: Additional runtime arguments
        model: Optional model identifier
        tools: Optional list of tool names
        transport_command: ACP transport command (for ACP protocol)
        transport_args: ACP transport arguments
        resume_args: Resume mode arguments
    """

    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    runtime_args: Optional[list[str]] = None
    model: Optional[str] = None
    tools: Optional[list[str]] = None
    transport_command: Optional[str] = None
    transport_args: Optional[list[str]] = None
    resume_args: Optional[list[str]] = None

    @field_validator("command", "transport_command", mode="before")
    @classmethod
    def validate_command_format(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate command format during Pydantic model construction.

        Args:
            v: Command string to validate

        Returns:
            The validated command

        Raises:
            ValueError: If command format is invalid
        """
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Command cannot be empty")

        # Command must be a simple alphanumeric string with dashes/underscores
        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                f"Command contains invalid characters: {v!r}. "
                "Commands must be alphanumeric with dashes, underscores, or dots only."
            )

        return v

    @field_validator("model", mode="before")
    @classmethod
    def validate_model_format(cls, v: Optional[str]) -> Optional[str]:
        """
        Validate model identifier format.

        Args:
            v: Model string to validate

        Returns:
            The validated model identifier

        Raises:
            ValueError: If model format is invalid
        """
        if v is None:
            return v

        # Model names should be alphanumeric with dashes, underscores, and dots
        # Example: claude-3-5-sonnet-20241022
        if not re.match(r"^[a-zA-Z0-9._-]+$", v):
            raise ValueError(
                f"Model identifier contains invalid characters: {v!r}"
            )

        return v

    @field_validator("tools", mode="before")
    @classmethod
    def validate_tools_format(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """
        Validate tool names format.

        Args:
            v: List of tool names

        Returns:
            The validated tool list

        Raises:
            ValueError: If any tool name is invalid
        """
        if v is None:
            return v

        for tool in v:
            if not isinstance(tool, str):
                raise ValueError(f"Tool name must be string, got {type(tool).__name__}")

            # Tool names should be alphanumeric with dashes and underscores
            if not re.match(r"^[a-zA-Z0-9_-]+$", tool):
                raise ValueError(
                    f"Tool name contains invalid characters: {tool!r}. "
                    "Tool names must be alphanumeric with dashes or underscores only."
                )

        return v

    def validate_command(self) -> bool:
        """
        Validate that command is in the allowlist.

        Returns:
            True if command is valid or None, False if command is not in allowlist

        Raises:
            ValidationError: If command format is invalid
        """
        if self.command is None:
            return True

        if self.command not in ALLOWED_COMMANDS:
            return False

        return True

    def validate_transport_command(self) -> bool:
        """
        Validate that ACP transport command is in the allowlist.

        Returns:
            True if transport command is valid or None, False if not in allowlist

        Raises:
            ValidationError: If transport command format is invalid
        """
        if self.transport_command is None:
            return True

        if self.transport_command not in ALLOWED_COMMANDS:
            return False

        return True

    def _check_shell_metacharacters(self, value: str, field_name: str) -> None:
        """
        Check if a string contains shell metacharacters.

        Args:
            value: String to check
            field_name: Name of the field being validated

        Raises:
            ValidationError: If shell metacharacters are detected
        """
        # Check for shell metacharacters
        found = []
        for char in SHELL_METACHARACTERS:
            if char in value:
                found.append(repr(char))

        if found:
            raise ValidationError(
                f"{field_name} contains shell metacharacters: {', '.join(found)}. "
                "This could indicate a command injection attempt.",
                field=field_name,
            )

    def _check_dangerous_flags(self, value: str, field_name: str) -> None:
        """
        Check if a string contains dangerous command execution flags.

        Args:
            value: String to check
            field_name: Name of the field being validated

        Raises:
            ValidationError: If dangerous flags are detected
        """
        value_lower = value.lower()
        found = []

        for flag in DANGEROUS_FLAGS:
            if flag.lower() in value_lower:
                found.append(flag)

        if found:
            raise ValidationError(
                f"{field_name} contains potentially dangerous flags: {', '.join(found)}. "
                "These flags could enable arbitrary command execution.",
                field=field_name,
            )

    def _validate_args_list(self, args: list[str], field_name: str) -> None:
        """
        Validate a list of arguments.

        Args:
            args: List of argument strings
            field_name: Name of the field being validated

        Raises:
            ValidationError: If any argument is invalid
        """
        for arg in args:
            # Check for shell metacharacters
            self._check_shell_metacharacters(arg, field_name)

            # Check for dangerous flags
            self._check_dangerous_flags(arg, field_name)

    def validate_args(self) -> None:
        """
        Validate command arguments.

        Raises:
            ValidationError: If any argument contains shell metacharacters or dangerous flags
        """
        self._validate_args_list(self.args, "args")

    def validate_runtime_args(self) -> None:
        """
        Validate runtime arguments.

        Raises:
            ValidationError: If any argument contains shell metacharacters or dangerous flags
        """
        if self.runtime_args:
            self._validate_args_list(self.runtime_args, "runtime_args")

    def validate_transport_args(self) -> None:
        """
        Validate ACP transport arguments.

        Raises:
            ValidationError: If any argument contains shell metacharacters or dangerous flags
        """
        if self.transport_args:
            self._validate_args_list(self.transport_args, "transport_args")

    def validate_resume_args(self) -> None:
        """
        Validate resume mode arguments.

        Raises:
            ValidationError: If any argument contains shell metacharacters or dangerous flags
        """
        if self.resume_args:
            self._validate_args_list(self.resume_args, "resume_args")

    def validate_all(self) -> bool:
        """
        Validate all fields in the agent specification.

        This is a convenience method that runs all validation checks.

        Returns:
            True if all validations pass, False otherwise

        Raises:
            ValidationError: If any validation fails with errors
        """
        results = [
            self.validate_command(),
            self.validate_transport_command(),
        ]

        # These methods raise ValidationError on failure
        self.validate_args()
        self.validate_runtime_args()
        self.validate_transport_args()
        self.validate_resume_args()

        return all(results)


def validate_path(
    path: str,
    base_dir: Optional[str] = None,
    allow_absolute: bool = False,
) -> Path:
    """
    Validate and resolve a file path to prevent directory traversal attacks.

    Args:
        path: Path string to validate
        base_dir: Base directory that the path must be relative to (optional)
        allow_absolute: Whether to allow absolute paths (default: False)

    Returns:
        Resolved Path object

    Raises:
        ValidationError: If path validation fails

    Examples:
        >>> validate_path("prompts/task.md", base_dir="/workspace")
        Path('/workspace/prompts/task.md')

        >>> validate_path("/etc/passwd", base_dir="/workspace")
        ValidationError: Path '/etc/passwd' is outside base directory
    """
    try:
        p = Path(path).expanduser()
    except Exception as e:
        raise ValidationError(
            f"Invalid path: {path!r}",
            field="path",
        ) from e

    # Resolve the path to handle any .. components
    try:
        resolved = p.resolve()
    except Exception as e:
        raise ValidationError(
            f"Cannot resolve path: {path!r}",
            field="path",
        ) from e

    # Check if path is absolute when not allowed
    if p.is_absolute() and not allow_absolute:
        raise ValidationError(
            f"Absolute paths are not allowed: {path!r}",
            field="path",
        )

    # If base_dir is specified, ensure the resolved path is within it
    if base_dir:
        try:
            base = Path(base_dir).resolve()
        except Exception as e:
            raise ValidationError(
                f"Invalid base directory: {base_dir!r}",
                field="path",
            ) from e

        try:
            # Check if resolved path is within base directory
            resolved.relative_to(base)
        except ValueError as e:
            raise ValidationError(
                f"Path '{path}' resolves to '{resolved}' which is outside "
                f"the base directory '{base}'. This could be a directory traversal attempt.",
                field="path",
            ) from e

    return resolved


def validate_agent_spec(
    spec: dict[str, Any],
    validate_all_fields: bool = True,
) -> AgentSpecValidator:
    """
    Validate an agent specification dictionary.

    This is a convenience function that creates an AgentSpecValidator
    from a dictionary and runs validation.

    Args:
        spec: Agent specification dictionary
        validate_all_fields: Whether to validate all fields (default: True)

    Returns:
        Validated AgentSpecValidator instance

    Raises:
        ValidationError: If validation fails
        ValueError: If Pydantic validation fails

    Examples:
        >>> spec = {
        ...     "command": "claude",
        ...     "args": ["--print"],
        ...     "model": "claude-3-5-sonnet-20241022"
        ... }
        >>> validator = validate_agent_spec(spec)
        >>> print(validator.command)
        'claude'
    """
    # Extract relevant fields
    validator_data = {
        "command": spec.get("command"),
        "args": spec.get("args", []),
        "runtime_args": spec.get("runtime_args"),
        "model": spec.get("model"),
        "tools": spec.get("tools"),
    }

    # Extract ACP transport fields if present
    transport = spec.get("transport", {})
    if transport:
        validator_data["transport_command"] = transport.get("command")
        validator_data["transport_args"] = transport.get("args")

    # Extract resume fields if present
    resume = spec.get("resume", {})
    if resume:
        validator_data["resume_args"] = resume.get("args")

    # Create validator (Pydantic will validate formats)
    try:
        validator = AgentSpecValidator(**validator_data)
    except Exception as e:
        raise ValueError(f"Invalid agent specification: {e}") from e

    # Run security validation if requested
    if validate_all_fields:
        validator.validate_all()

    return validator
