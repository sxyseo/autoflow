"""
Autoflow Configuration Module

Provides configuration loading with JSON5 support, allowing comments,
trailing commas, and unquoted keys in configuration files.

Usage:
    from autoflow.core.config import load_config, load_system_config

    config = load_config("config/settings.json5")
    system_config = load_system_config()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Union

import json5

from pydantic import BaseModel, Field, field_validator


# Default configuration paths
DEFAULT_CONFIG_PATH = "config/settings.json5"
DEFAULT_SYSTEM_CONFIG_PATH = "config/system.json5"
ENV_CONFIG_PATH = "AUTOFLOW_CONFIG"
ENV_STATE_DIR = "AUTOFLOW_STATE_DIR"


class OpenClawConfig(BaseModel):
    """OpenClaw integration settings."""

    gateway_url: str = "http://localhost:3000"
    config_path: str = "~/.openclaw/config.json5"
    extra_dirs: list[str] = Field(default_factory=lambda: ["./skills"])


class AgentSettings(BaseModel):
    """Configuration for a single agent."""

    command: str
    args: list[str] = Field(default_factory=list)
    resume_mode: str = "reprompt"  # "native" or "reprompt"
    approval_policy: str = "suggest"  # "never", "suggest", "always"
    timeout_seconds: int = 300


class AgentsConfig(BaseModel):
    """Agent configurations."""

    claude_code: AgentSettings = Field(
        default_factory=lambda: AgentSettings(
            command="claude",
            args=["--print"],
            resume_mode="native",
        )
    )
    codex: AgentSettings = Field(
        default_factory=lambda: AgentSettings(
            command="codex",
            args=["exec", "--json"],
            resume_mode="reprompt",
            approval_policy="never",
        )
    )


class SchedulerJobConfig(BaseModel):
    """Configuration for a scheduled job."""

    id: str
    cron: str
    handler: str
    enabled: bool = True


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""

    enabled: bool = True
    jobs: list[SchedulerJobConfig] = Field(default_factory=list)


class CIGateConfig(BaseModel):
    """Configuration for a CI gate."""

    type: str  # "test", "lint", "security"
    command: str
    required: bool = True


class CIConfig(BaseModel):
    """CI gates configuration."""

    gates: list[CIGateConfig] = Field(default_factory=list)
    require_all: bool = True


class SymphonyConfig(BaseModel):
    """Symphony integration settings."""

    enabled: bool = True
    gateway_url: str = "http://localhost:8000"
    api_key: Optional[str] = None
    project_id: str = "default"
    environment: str = "development"
    timeout_seconds: int = 30
    max_retries: int = 3


class Config(BaseModel):
    """
    Main Autoflow configuration.

    Supports JSON5 format with comments, trailing commas, and unquoted keys.
    """

    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    symphony: SymphonyConfig = Field(default_factory=SymphonyConfig)
    state_dir: str = ".autoflow"

    @field_validator("state_dir", mode="before")
    @classmethod
    def expand_state_dir(cls, v: str) -> str:
        """Expand environment variables in state_dir path."""
        return os.path.expandvars(os.path.expanduser(v))


class SystemConfig(BaseModel):
    """
    System-level configuration.

    Contains paths, environment settings, and system-level options.
    """

    project_root: str = "."
    python_path: str = "python3"
    log_level: str = "INFO"
    log_dir: str = ".autoflow/logs"
    max_concurrent_agents: int = 3
    default_timeout_seconds: int = 300
    retry_attempts: int = 3
    retry_delay_seconds: int = 5

    @field_validator("project_root", "log_dir", mode="before")
    @classmethod
    def expand_paths(cls, v: str) -> str:
        """Expand environment variables and user home in paths."""
        return os.path.expandvars(os.path.expanduser(v))


def _resolve_config_path(path: Optional[str], env_var: str, default: str) -> Path:
    """
    Resolve configuration file path with fallbacks.

    Priority:
    1. Explicitly provided path
    2. Environment variable
    3. Default path

    Args:
        path: Explicitly provided path (or None)
        env_var: Environment variable name to check
        default: Default path if none specified

    Returns:
        Resolved Path object
    """
    if path:
        return Path(path).expanduser().resolve()

    env_path = os.environ.get(env_var)
    if env_path:
        return Path(env_path).expanduser().resolve()

    return Path(default).resolve()


def _load_json5_file(file_path: Path) -> dict[str, Any]:
    """
    Load and parse a JSON5 file.

    Args:
        file_path: Path to the JSON5 file

    Returns:
        Parsed configuration dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file contains invalid JSON5
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return json5.loads(content)
    except json5.Json5DecoderError as e:
        raise ValueError(f"Invalid JSON5 in {file_path}: {e}") from e


def load_config(
    path: Optional[str] = None,
    defaults: Optional[dict[str, Any]] = None,
) -> Config:
    """
    Load Autoflow configuration from a JSON5 file.

    Configuration is loaded from the following sources in priority order:
    1. Explicitly provided path
    2. AUTOFLOW_CONFIG environment variable
    3. config/settings.json5 (default)

    If the configuration file doesn't exist, returns default configuration.
    Environment variables in paths are expanded.

    Args:
        path: Optional explicit path to configuration file
        defaults: Optional dictionary of default values to merge

    Returns:
        Config object with loaded or default settings

    Example:
        >>> config = load_config()
        >>> print(config.openclaw.gateway_url)
        'http://localhost:3000'

        >>> config = load_config("my-config.json5")
        >>> print(config.agents.claude_code.command)
        'claude'
    """
    config_path = _resolve_config_path(path, ENV_CONFIG_PATH, DEFAULT_CONFIG_PATH)

    try:
        config_dict = _load_json5_file(config_path)
    except FileNotFoundError:
        # Return default configuration if file doesn't exist
        config_dict = {}

    # Merge with provided defaults
    if defaults:
        config_dict = {**defaults, **config_dict}

    return Config(**config_dict)


def load_system_config(
    path: Optional[str] = None,
) -> SystemConfig:
    """
    Load system-level configuration from a JSON5 file.

    System configuration contains paths, environment settings, and
    system-level options that don't change frequently.

    Configuration is loaded from the following sources in priority order:
    1. Explicitly provided path
    2. AUTOFLOW_SYSTEM_CONFIG environment variable
    3. config/system.json5 (default)

    If the configuration file doesn't exist, returns default configuration.

    Args:
        path: Optional explicit path to system configuration file

    Returns:
        SystemConfig object with loaded or default settings

    Example:
        >>> sys_config = load_system_config()
        >>> print(sys_config.log_level)
        'INFO'
    """
    config_path = _resolve_config_path(
        path, "AUTOFLOW_SYSTEM_CONFIG", DEFAULT_SYSTEM_CONFIG_PATH
    )

    try:
        config_dict = _load_json5_file(config_path)
    except FileNotFoundError:
        # Return default configuration if file doesn't exist
        config_dict = {}

    return SystemConfig(**config_dict)


def get_state_dir(config: Optional[Config] = None) -> Path:
    """
    Get the state directory path.

    Priority:
    1. AUTOFLOW_STATE_DIR environment variable
    2. Config's state_dir setting
    3. Default '.autoflow'

    Args:
        config: Optional Config object to get state_dir from

    Returns:
        Path to the state directory
    """
    env_state_dir = os.environ.get(ENV_STATE_DIR)
    if env_state_dir:
        return Path(env_state_dir).expanduser().resolve()

    if config:
        return Path(config.state_dir).resolve()

    return Path(".autoflow").resolve()


def merge_configs(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """
    Recursively merge two configuration dictionaries.

    Values in override take precedence over base.
    Nested dictionaries are merged recursively.
    Lists are replaced entirely (not concatenated).

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary

    Returns:
        Merged configuration dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def config_to_json5(config: Union[Config, SystemConfig], indent: int = 2) -> str:
    """
    Export configuration to JSON5 format string.

    Note: This produces standard JSON output since Python's json module
    doesn't support JSON5-specific features like comments.

    Args:
        config: Config or SystemConfig object to export
        indent: Number of spaces for indentation

    Returns:
        JSON5-formatted string
    """
    return json.dumps(config.model_dump(), indent=indent)
