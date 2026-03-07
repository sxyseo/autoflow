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
from autoflow.core.state import (
    StateManager,
    Task,
    TaskStatus,
    Run,
    RunStatus,
    Spec,
    Memory,
    read_json,
    write_json,
)

# Orchestrator
from autoflow.core.orchestrator import (
    AutoflowOrchestrator,
    OrchestratorStatus,
    OrchestratorStats,
    CyclePhase,
    CycleResult,
    OrchestratorError,
)

# Commands
from autoflow.core.commands import (
    get_workflow_state,
    get_task_history,
    get_strategy_summary,
    sync_agents,
    taskmaster_import,
    taskmaster_export,
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
    # Commands
    "get_workflow_state",
    "get_task_history",
    "get_strategy_summary",
    "sync_agents",
    "taskmaster_import",
    "taskmaster_export",
]
