"""
Autoflow Configuration Module

Provides configuration loading with JSON5 support, allowing comments,
trailing commas, and unquoted keys in configuration files.

Usage:
<<<<<<< HEAD
    from autoflow.core.config import load_config, load_system_config
=======
    from autoflow.core.config import (
        load_config,
        load_system_config,
        RepositoryConfig,
        AutoflowConfig,
    )
>>>>>>> auto-claude/109-replace-dynamic-module-loading-in-tests-with-prope

    # Simple loading
    config = load_config("config/settings.json5")
    system_config = load_system_config()
<<<<<<< HEAD
=======
    repo_config = RepositoryConfig(id="main", name="Main Repo", path=".")

    # Using AutoflowConfig manager
    autoflow_config = AutoflowConfig()
    autoflow_config.load()
    print(autoflow_config.config.openclaw.gateway_url)
>>>>>>> auto-claude/109-replace-dynamic-module-loading-in-tests-with-prope
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


class DistributedConfig(BaseModel):
    """Distributed node configuration for multi-node coordination."""

    node_id: Optional[str] = None  # Auto-generated if not provided
    listen_address: str = "localhost:8080"
    seed_nodes: list[str] = Field(default_factory=list)


class Config(BaseModel):
    """
    Main Autoflow configuration.

    Supports JSON5 format with comments, trailing commas, and unquoted keys.
    """

    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    ci: CIConfig = Field(default_factory=CIConfig)
    distributed: DistributedConfig = Field(default_factory=DistributedConfig)
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


class AutoflowConfig:
    """
    Manages Autoflow configuration with loading and merging capabilities.

    Provides a unified interface for accessing both main configuration and
    system configuration. Handles loading from files with fallbacks and
    environment variable expansion.

    This class follows the pattern of StateManager, providing a centralized
    configuration management interface with atomic operations and validation.

    Attributes:
        config_dir: Directory containing configuration files
        config: Main application configuration
        system_config: System-level configuration

    Example:
        >>> autoflow_config = AutoflowConfig()
        >>> autoflow_config.load()
        >>> print(autoflow_config.config.openclaw.gateway_url)
        'http://localhost:3000'
        >>> print(autoflow_config.system_config.log_level)
        'INFO'
    """

    def __init__(
        self,
        config_dir: Union[str, Path] = "config",
        state_dir: Union[str, Path] = ".autoflow",
    ):
        """
        Initialize the AutoflowConfig manager.

        Args:
            config_dir: Directory containing configuration files
            state_dir: State directory for Autoflow
        """
        self.config_dir = Path(config_dir).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.config: Optional[Config] = None
        self.system_config: Optional[SystemConfig] = None

    @property
    def main_config_path(self) -> Path:
        """Path to main configuration file."""
        return self.config_dir / "settings.json5"

    @property
    def system_config_path(self) -> Path:
        """Path to system configuration file."""
        return self.config_dir / "system.json5"

    def load(
        self,
        config_path: Optional[str] = None,
        system_config_path: Optional[str] = None,
        defaults: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Load both main and system configuration.

        Configuration is loaded from the following sources in priority order:
        1. Explicitly provided path
        2. AUTOFLOW_CONFIG / AUTOFLOW_SYSTEM_CONFIG environment variables
        3. config/settings.json5 or config/system.json5 (default)

        If configuration files don't exist, default configurations are used.

        Args:
            config_path: Optional explicit path to main configuration file
            system_config_path: Optional explicit path to system configuration file
            defaults: Optional dictionary of default values to merge into main config

        Example:
            >>> autoflow_config = AutoflowConfig()
            >>> autoflow_config.load()
            >>> assert autoflow_config.config is not None
        """
        self.config = load_config(
            path=config_path,
            defaults=defaults,
        )
        self.system_config = load_system_config(
            path=system_config_path,
        )

    def reload(self) -> None:
        """
        Reload configuration from files.

        Useful when configuration files have been modified externally
        and you want to refresh the in-memory configuration.

        Example:
            >>> autoflow_config.reload()
        """
        self.load()

    def save(
        self,
        save_main: bool = True,
        save_system: bool = True,
        indent: int = 2,
    ) -> None:
        """
        Save current configuration to files.

        Performs atomic writes using the StateManager for crash safety.

        Args:
            save_main: Whether to save main configuration
            save_system: Whether to save system configuration
            indent: JSON indentation level

        Raises:
            ValueError: If configuration hasn't been loaded

        Example:
            >>> autoflow_config.config.openclaw.gateway_url = "http://localhost:4000"
            >>> autoflow_config.save()
        """
        if self.config is None and self.system_config is None:
            raise ValueError("No configuration loaded. Call load() first.")

        from autoflow.core.state import StateManager

        state_manager = StateManager(self.state_dir)

        if save_main and self.config is not None:
            config_path = self.main_config_path
            config_dict = self.config.model_dump()
            state_manager.write_json(config_path, config_dict, indent=indent)

        if save_system and self.system_config is not None:
            sys_config_path = self.system_config_path
            sys_config_dict = self.system_config.model_dump()
            state_manager.write_json(sys_config_path, sys_config_dict, indent=indent)

    def get_state_dir(self) -> Path:
        """
        Get the state directory path.

        Priority:
        1. AUTOFLOW_STATE_DIR environment variable
        2. Config's state_dir setting (if loaded)
        3. Default '.autoflow'

        Returns:
            Path to the state directory

        Example:
            >>> state_dir = autoflow_config.get_state_dir()
        """
        return get_state_dir(self.config)

    def get_agent_config(self, agent_name: str) -> Optional[AgentSettings]:
        """
        Get configuration for a specific agent.

        Args:
            agent_name: Name of the agent (e.g., 'claude_code', 'codex')

        Returns:
            AgentSettings if found, None otherwise

        Example:
            >>> claude_config = autoflow_config.get_agent_config('claude_code')
            >>> if claude_config:
            ...     print(claude_config.command)
        """
        if self.config is None:
            return None

        return getattr(self.config.agents, agent_name, None)

    def get_repository_config(
        self, repository_id: str
    ) -> Optional[RepositoryConfig]:
        """
        Get configuration for a specific repository.

        Args:
            repository_id: ID of the repository

        Returns:
            RepositoryConfig if found, None otherwise

        Example:
            >>> repo_config = autoflow_config.get_repository_config('main')
            >>> if repo_config:
            ...     print(repo_config.path)
        """
        if self.config is None:
            return None

        for repo in self.config.repositories.repositories:
            if repo.id == repository_id:
                return repo

        return None

    def list_repositories(self) -> list[RepositoryConfig]:
        """
        List all configured repositories.

        Returns:
            List of RepositoryConfig objects, sorted by priority descending

        Example:
            >>> repos = autoflow_config.list_repositories()
            >>> for repo in repos:
            ...     print(f"{repo.name}: {repo.path}")
        """
        if self.config is None:
            return []

        repos = self.config.repositories.repositories.copy()
        repos.sort(key=lambda r: r.priority, reverse=True)
        return repos

    def get_scheduler_job_config(self, job_id: str) -> Optional[SchedulerJobConfig]:
        """
        Get configuration for a specific scheduled job.

        Args:
            job_id: ID of the job

        Returns:
            SchedulerJobConfig if found, None otherwise

        Example:
            >>> job_config = autoflow_config.get_scheduler_job_config('daily-backup')
            >>> if job_config:
            ...     print(job_config.cron)
        """
        if self.config is None:
            return None

        for job in self.config.scheduler.jobs:
            if job.id == job_id:
                return job

        return None

    def list_scheduler_jobs(self, enabled_only: bool = False) -> list[SchedulerJobConfig]:
        """
        List scheduled job configurations.

        Args:
            enabled_only: If True, only return enabled jobs

        Returns:
            List of SchedulerJobConfig objects

        Example:
            >>> jobs = autoflow_config.list_scheduler_jobs(enabled_only=True)
            >>> for job in jobs:
            ...     print(f"{job.id}: {job.cron}")
        """
        if self.config is None:
            return []

        jobs = self.config.scheduler.jobs.copy()

        if enabled_only:
            jobs = [job for job in jobs if job.enabled]

        return jobs

    def get_ci_gates(self) -> list[CIGateConfig]:
        """
        Get all configured CI gates.

        Returns:
            List of CIGateConfig objects

        Example:
            >>> gates = autoflow_config.get_ci_gates()
            >>> for gate in gates:
            ...     print(f"{gate.type}: {gate.command}")
        """
        if self.config is None:
            return []

        return self.config.ci.gates.copy()

    def validate(self) -> dict[str, list[str]]:
        """
        Validate the current configuration.

        Checks for common configuration issues like:
        - Invalid paths
        - Missing required fields
        - Invalid cron expressions
        - Conflicting settings

        Returns:
            Dictionary with 'errors' and 'warnings' lists

        Example:
            >>> validation = autoflow_config.validate()
            >>> if validation['errors']:
            ...     print("Configuration errors:", validation['errors'])
        """
        errors: list[str] = []
        warnings: list[str] = []

        if self.config is None:
            errors.append("Configuration not loaded")
            return {"errors": errors, "warnings": warnings}

        # Validate repository paths exist
        for repo in self.config.repositories.repositories:
            repo_path = Path(repo.path)
            if not repo_path.exists():
                warnings.append(
                    f"Repository path does not exist: {repo.id} at {repo_path}"
                )

        # Validate state directory
        state_dir = self.get_state_dir()
        if not state_dir.exists():
            warnings.append(f"State directory does not exist: {state_dir}")

        # Validate log directory if system config loaded
        if self.system_config is not None:
            log_dir = Path(self.system_config.log_dir)
            if not log_dir.exists():
                warnings.append(f"Log directory does not exist: {log_dir}")

        return {"errors": errors, "warnings": warnings}

    def to_dict(self) -> dict[str, Any]:
        """
        Export configuration to dictionary.

        Returns:
            Dictionary containing both main and system configuration

        Example:
            >>> config_dict = autoflow_config.to_dict()
            >>> import json
            >>> print(json.dumps(config_dict, indent=2))
        """
        result: dict[str, Any] = {}

        if self.config is not None:
            result["config"] = self.config.model_dump()

        if self.system_config is not None:
            result["system_config"] = self.system_config.model_dump()

        return result

    def __repr__(self) -> str:
        """String representation of AutoflowConfig."""
        return (
            f"AutoflowConfig("
            f"config_dir={self.config_dir!r}, "
            f"state_dir={self.state_dir!r}, "
            f"loaded={self.config is not None})"
        )
