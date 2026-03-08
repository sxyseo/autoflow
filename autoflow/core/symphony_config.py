"""
Symphony Configuration Module

Provides configuration for Symphony multi-agent orchestration framework integration.
Symphony is an optional orchestrator that can coordinate multiple AI agents.

Usage:
    from autoflow.core.symphony_config import SymphonyConfig, load_symphony_config

    config = load_symphony_config()
    print(f"Symphony enabled: {config.enabled}")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import json5

from pydantic import BaseModel, Field, field_validator


# Default configuration paths
DEFAULT_SYMPHONY_CONFIG_PATH = "config/symphony.json5"
ENV_SYMPHONY_CONFIG = "AUTOFLOW_SYMPHONY_CONFIG"


class SymphonyAgentConfig(BaseModel):
    """Configuration for a Symphony agent."""

    command: str = "symphony"
    args: list[str] = Field(default_factory=lambda: ["agent", "run"])
    timeout_seconds: int = 300
    runtime: str = "claude"  # "claude" or "generic"


class SymphonyWorkflowConfig(BaseModel):
    """Configuration for Symphony workflows."""

    workflow_dir: str = ".autoflow/symphony/workflows"
    checkpoint_dir: str = ".autoflow/symphony/checkpoints"
    enabled_workflows: list[str] = Field(default_factory=list)
    auto_resume: bool = True

    @field_validator("workflow_dir", "checkpoint_dir", mode="before")
    @classmethod
    def expand_paths(cls, v: str) -> str:
        """Expand environment variables and user home in paths."""
        return os.path.expandvars(os.path.expanduser(v))


class SymphonyCheckpointConfig(BaseModel):
    """Configuration for Symphony checkpoint integration."""

    enabled: bool = True
    sync_with_review_gates: bool = True
    checkpoint_interval_seconds: int = 60
    max_checkpoints: int = 10


class SymphonyConfig(BaseModel):
    """
    Symphony integration configuration.

    Symphony is an optional multi-agent orchestration framework that can
    coordinate multiple AI agents on complex tasks. This configuration
    controls how Autoflow integrates with Symphony.

    Attributes:
        enabled: Whether Symphony integration is enabled
        api_url: Symphony API endpoint URL
        agent: Default agent configuration
        workflows: Workflow settings
        checkpoints: Checkpoint and state management settings
    """

    enabled: bool = False
    api_url: str = "http://localhost:8080"
    agent: SymphonyAgentConfig = Field(default_factory=SymphonyAgentConfig)
    workflows: SymphonyWorkflowConfig = Field(default_factory=SymphonyWorkflowConfig)
    checkpoints: SymphonyCheckpointConfig = Field(
        default_factory=SymphonyCheckpointConfig
    )


def load_symphony_config(
    path: Optional[str] = None,
    defaults: Optional[dict[str, Any]] = None,
) -> SymphonyConfig:
    """
    Load Symphony configuration from a JSON5 file.

    Configuration is loaded from the following sources in priority order:
    1. Explicitly provided path
    2. AUTOFLOW_SYMPHONY_CONFIG environment variable
    3. config/symphony.json5 (default)

    If the configuration file doesn't exist, returns default configuration
    with Symphony disabled.

    Args:
        path: Optional explicit path to configuration file
        defaults: Optional dictionary of default values to merge

    Returns:
        SymphonyConfig object with loaded or default settings

    Example:
        >>> config = load_symphony_config()
        >>> if config.enabled:
        ...     print(f"Symphony API URL: {config.api_url}")
        ... else:
        ...     print("Symphony is disabled")

        >>> config = load_symphony_config("custom-symphony.json5")
        >>> print(config.agent.timeout_seconds)
    """
    # Resolve configuration path
    if path:
        config_path = Path(path).expanduser().resolve()
    else:
        env_path = os.environ.get(ENV_SYMPHONY_CONFIG)
        if env_path:
            config_path = Path(env_path).expanduser().resolve()
        else:
            config_path = Path(DEFAULT_SYMPHONY_CONFIG_PATH).resolve()

    # Try to load configuration file
    try:
        if not config_path.exists():
            # Return default configuration if file doesn't exist
            config_dict = {}
        else:
            with open(config_path, encoding="utf-8") as f:
                content = f.read()
            config_dict = json5.loads(content)
    except (json5.Json5DecoderError, FileNotFoundError, ValueError) as e:
        # If file exists but is invalid, log warning and use defaults
        # (In production, might want to log this somewhere)
        config_dict = {}

    # Merge with provided defaults
    if defaults:
        config_dict = {**defaults, **config_dict}

    return SymphonyConfig(**config_dict)


def get_symphony_workflow_dir(config: Optional[SymphonyConfig] = None) -> Path:
    """
    Get the Symphony workflow directory path.

    Args:
        config: Optional SymphonyConfig object

    Returns:
        Path to the workflow directory
    """
    if config and config.workflows:
        return Path(config.workflows.workflow_dir).resolve()

    return Path(".autoflow/symphony/workflows").resolve()


def get_symphony_checkpoint_dir(config: Optional[SymphonyConfig] = None) -> Path:
    """
    Get the Symphony checkpoint directory path.

    Args:
        config: Optional SymphonyConfig object

    Returns:
        Path to the checkpoint directory
    """
    if config and config.checkpoints:
        return Path(config.workflows.checkpoint_dir).resolve()

    return Path(".autoflow/symphony/checkpoints").resolve()


# Rebuild models to resolve forward references
SymphonyConfig.model_rebuild()
