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
    config_to_json5,
    get_state_dir,
    load_config,
    load_system_config,
    merge_configs,
)

# Orchestrator
from autoflow.core.orchestrator import (
    AutoflowOrchestrator,
    CyclePhase,
    CycleResult,
    OrchestratorError,
    OrchestratorStats,
    OrchestratorStatus,
    TaskResult,
)
from autoflow.core.state import (
    Memory,
    Run,
    RunStatus,
    Spec,
    StateManager,
    Task,
    TaskStatus,
    read_json,
    write_json,
)

__all__ = [
    # Config
    "Config",
    "SystemConfig",
    "load_config",
    "load_system_config",
    "get_state_dir",
    "merge_configs",
    "config_to_json5",
    # State
    "StateManager",
    "Task",
    "TaskStatus",
    "Run",
    "RunStatus",
    "Spec",
    "Memory",
    "read_json",
    "write_json",
    # Orchestrator
    "AutoflowOrchestrator",
    "OrchestratorStatus",
    "OrchestratorStats",
    "CyclePhase",
    "CycleResult",
    "OrchestratorError",
    "TaskResult",
]
