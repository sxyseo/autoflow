"""
Autoflow Core - Orchestration, Configuration, and State Management

This module provides the core functionality for Autoflow:
- Orchestrator: Coordinates AI agents and task execution
- Config: Configuration loading with JSON5 support
- State: Persistent state management with atomic writes
"""

from autoflow.core.config import (
    Config,
    SystemConfig,
    load_config,
    load_system_config,
    get_state_dir,
    merge_configs,
    config_to_json5,
)

# Core components will be imported here as they are implemented
# from autoflow.core.orchestrator import AutoflowOrchestrator
# from autoflow.core.state import StateManager

__all__ = [
    "Config",
    "SystemConfig",
    "load_config",
    "load_system_config",
    "get_state_dir",
    "merge_configs",
    "config_to_json5",
]
